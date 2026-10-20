package com.unlockops;

import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
class ProblemService {
    private final JdbcTemplate jdbc;
    private final Jsons json;
    private final GrantRules rules;
    private final boolean demo;
    ProblemService(JdbcTemplate jdbc,Jsons json,GrantRules rules,@Value("${app.demo-enabled}") boolean demo) {
        this.jdbc=jdbc; this.json=json; this.rules=rules; this.demo=demo;
    }
    @Transactional public Map<String,Object> create(AppUser user,String platform,String contents,boolean simulateFailure) {
        if (!Set.of("GITHUB","JIRA","SLACK","NOTION").contains(platform))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"플랫폼 한 개를 선택해 주세요.");
        if (simulateFailure && (!demo || !platform.equals("JIRA")))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Jira 데모에서만 실패 시연을 선택할 수 있습니다.");
        UUID id=UUID.randomUUID();
        jdbc.update("""
            INSERT INTO problems(id,requester_id,approver_id,platform,contents,thread_id,simulate_jira_failure)
            VALUES (?,?,?,?,?,?,?)
            """,id,user.id(),rules.reviewer(user.id()),platform,contents.strip(),id.toString(),simulateFailure);
        var row=jdbc.queryForMap("SELECT * FROM problems WHERE id=?",id);
        enqueue(row,"ANALYZE");
        return Map.of("id",id,"status","RECEIVED");
    }
    void enqueue(Map<String,Object> row,String type) {
        UUID eventId=UUID.randomUUID();
        Map<String,Object> job=new LinkedHashMap<>();
        job.put("event_id",eventId.toString()); job.put("job_type",type);
        for(String field:List.of("requester_id","platform","contents")) job.put(field,row.get(field).toString());
        job.put("problem_id",row.get("id").toString());
        job.put("idempotency_key",row.get("idempotency_key")); job.put("plan_hash",row.get("plan_hash"));
        jdbc.update("INSERT INTO outbox(event_id,routing_key,payload) VALUES (?,?,?::jsonb)",
            eventId,type.equals("ANALYZE")?"analysis":"execution",json.write(job));
    }
    private boolean operations(AppUser user) { return user.loginId().equals("song_ops"); }
    List<Map<String,Object>> list(AppUser user) {
        return list(user,false);
    }
    List<Map<String,Object>> list(AppUser user,boolean mine) {
        if(mine) {
            return jdbc.queryForList("""
                SELECT p.id,p.requester_id,p.approver_id,p.platform,p.contents,p.status,p.reason_code,
                       p.diagnosis,p.proposal,p.resource_id,p.requested_role,p.verification_ok,
                       p.decision_reason,p.decided_at,p.created_at,p.updated_at,
                       u.name requester_name,u.employee_no
                FROM problems p JOIN users u ON u.id=p.requester_id
                WHERE p.requester_id=? ORDER BY p.created_at DESC LIMIT 100
                """,user.id()).stream().map(ProblemViews::requester).toList();
        }
        rules.requireApprover(user);
        String filter=operations(user)?"":" WHERE p.approver_id=?";
        Object[] parameters=operations(user)?new Object[]{}:new Object[]{user.id()};
        return jdbc.queryForList("""
            SELECT p.id,p.platform,p.contents,p.status,p.reason_code,p.diagnosis,p.proposal,
                   p.approver_id,p.requested_role,p.plan_hash,p.verification_ok,p.agent_mode,
                   p.created_at,p.updated_at,u.name requester_name,u.employee_no
            FROM problems p JOIN users u ON u.id=p.requester_id
            """+filter+" ORDER BY p.created_at DESC LIMIT 100",parameters);
    }
    Map<String,Object> detail(AppUser user,UUID id) {
        var rows=jdbc.queryForList("""
            SELECT p.*,p.evidence::text evidence_json,p.plan::text plan_json,u.name requester_name,u.employee_no
            FROM problems p JOIN users u ON u.id=p.requester_id WHERE p.id=?
            """,id);
        if(rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"요청을 찾을 수 없습니다.");
        var row=rows.getFirst();
        boolean own=user.id().equals(row.get("requester_id"));
        if(!own) {
            rules.requireApprover(user);
            if(!operations(user)&&!user.id().equals(row.get("approver_id")))
                throw new ResponseStatusException(HttpStatus.FORBIDDEN,"담당 요청만 조회할 수 있습니다.");
        }
        var events=jdbc.queryForList("SELECT kind,payload::text payload,created_at FROM problem_events WHERE problem_id=? ORDER BY id",id);
        events.forEach(e -> e.put("payload",json.any(e.get("payload").toString())));
        if(own) {
            var view=ProblemViews.requester(row);
            view.put("events",ProblemViews.publicEvents(events));
            return view;
        }
        row.put("evidence",json.any(row.remove("evidence_json").toString()));
        Object plan=row.remove("plan_json"); row.put("plan",plan==null?null:json.any(plan.toString()));
        row.put("events",events);
        return row;
    }
    Map<String,Object> approvalSummary(AppUser user) {
        rules.requireApprover(user);
        // All request counters use the same KST creation-week cohort, independent of the 100-row inbox.
        return jdbc.queryForMap("""
            WITH week AS (
                SELECT date_trunc('week',CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul') AS start_local
            )
            SELECT d.name department,
                   (SELECT count(*) FROM users member WHERE member.department_id=d.id) AS "memberCount",
                   count(p.id) AS "weekRequests",
                   count(p.id) FILTER (WHERE p.decision_source='HUMAN' AND p.approved_plan_hash IS NOT NULL
                       AND p.decided_by IS NOT NULL) AS approved,
                   count(p.id) FILTER (WHERE p.status='REJECTED') AS rejected,
                   count(p.id) FILTER (WHERE p.status='FAILED') AS failed
            FROM users actor JOIN departments d ON d.id=actor.department_id
            CROSS JOIN week
            LEFT JOIN users requester ON requester.department_id=d.id
            LEFT JOIN problems p ON p.requester_id=requester.id
                AND p.created_at >= (week.start_local AT TIME ZONE 'Asia/Seoul')
                AND p.created_at < ((week.start_local + INTERVAL '7 days') AT TIME ZONE 'Asia/Seoul')
            WHERE actor.id=? GROUP BY d.id,d.name
            """,user.id());
    }
    @Transactional public Map<String,Object> decide(AppUser user,UUID id,boolean approved,String expectedHash,String reason) {
        rules.requireApprover(user);
        var rows=jdbc.queryForList("SELECT *,plan::text plan_json FROM problems WHERE id=? FOR UPDATE",id);
        if(rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"요청을 찾을 수 없습니다.");
        var row=rows.getFirst();
        GrantRules.check("WAITING_APPROVAL".equals(row.get("status")),"이미 처리되었거나 승인 대기 상태가 아닙니다.");
        if(!user.id().equals(row.get("approver_id")) || user.id().equals(row.get("requester_id")))
            throw new ResponseStatusException(HttpStatus.FORBIDDEN,"지정 승인자만 처리할 수 있고 본인 승인은 불가합니다.");
        GrantRules.check(Objects.equals(expectedHash,row.get("plan_hash")),"승인 카드가 변경되었습니다. 새로고침해 주세요.");
        if(!approved && reason.isBlank()) throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"반려 사유를 입력해 주세요.");
        var plan=json.object(row.get("plan_json").toString());
        if(approved) {
            GrantRules.check(user.id().equals(rules.validatePlan(row,plan)),"승인자가 변경되었습니다.");
            GrantRules.check(json.planHash(plan).equals(expectedHash),"실행 계획이 변경되었습니다.");
        }
        String status=approved?"EXECUTING":"REJECTED";
        String key=approved?id+":"+expectedHash:null;
        jdbc.update("""
            UPDATE problems SET status=?,decision_reason=?,decision_source='HUMAN',decided_by=?,decided_at=NOW(),
              approved_plan_hash=?,idempotency_key=?,reason_code=?,proposal=?,updated_at=NOW() WHERE id=?
            """,status,reason,user.id(),approved?expectedHash:null,key,approved?"HUMAN_APPROVED":"HUMAN_REJECTED",
            approved?"승인이 기록되어 권한 부여를 진행하고 있습니다.":"담당자가 반려했습니다. "+reason,id);
        jdbc.update("INSERT INTO problem_events(event_id,problem_id,kind,payload) VALUES (?,?,?,?::jsonb)",
            UUID.randomUUID(),id,"HUMAN_DECISION",json.write(Map.of("approved",approved,"actor_id",user.id(),"reason",reason)));
        if(approved) {
            row.put("idempotency_key",key);
            enqueue(row,"EXECUTE");
        }
        return Map.of("id",id,"status",status);
    }
}
