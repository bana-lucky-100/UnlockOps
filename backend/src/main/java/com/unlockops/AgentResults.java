package com.unlockops;

import java.util.*;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
class AgentResults {
    private final JdbcTemplate jdbc;
    private final Jsons json;
    private final GrantRules rules;
    AgentResults(JdbcTemplate jdbc,Jsons json,GrantRules rules) { this.jdbc=jdbc; this.json=json; this.rules=rules; }

    @RabbitListener(queues="unlockops.results")
    @Transactional
    public void consume(Map<String,Object> event) {
        UUID eventId=UUID.fromString(event.get("event_id").toString());
        UUID id=UUID.fromString(event.get("problem_id").toString());
        int inserted=jdbc.update("INSERT INTO inbox_events(event_id) VALUES (?) ON CONFLICT DO NOTHING",eventId);
        if(inserted==0) return;
        var rows=jdbc.queryForList("SELECT * FROM problems WHERE id=? FOR UPDATE",id);
        if(rows.isEmpty()) return;
        var problem=rows.getFirst();
        String kind=event.get("kind").toString();
        jdbc.update("INSERT INTO problem_events(event_id,problem_id,kind,payload) VALUES (?,?,?,?::jsonb)",
            eventId,id,kind,json.write(event));
        String current=problem.get("status").toString();
        boolean execution="EXECUTE".equals(event.get("job_type"));
        boolean active=execution?current.equals("EXECUTING"):Set.of("RECEIVED","DIAGNOSING").contains(current);
        if(!active) return; // Stale/replayed analysis cannot overwrite an approval or terminal result.
        if(kind.equals("PROGRESS")) {
            if(!execution && current.equals("RECEIVED"))
                jdbc.update("UPDATE problems SET status='DIAGNOSING',updated_at=NOW() WHERE id=?",id);
            return;
        }
        if(kind.equals("FAILED")) {
            jdbc.update("UPDATE problems SET status='FAILED',reason_code=?,proposal=?,updated_at=NOW() WHERE id=?",
                event.getOrDefault("error_code","WORKER_ERROR"),"처리가 완료되지 않았습니다. 담당자가 실행 기록을 확인해야 합니다.",id);
            return;
        }
        if(!Set.of("ANALYZED","EXECUTED").contains(kind) || !(event.get("result") instanceof Map<?,?>))
            throw new IllegalArgumentException("Unknown result event");
        @SuppressWarnings("unchecked") var rawResult=(Map<String,Object>)event.get("result");
        var result=normalizeResult(rawResult);
        String status=result.get("status").toString();
        ProblemStatus.valueOf(status);
        Set<String> allowed=execution?Set.of("DONE","FAILED"):
            Set.of("WAITING_APPROVAL","REJECTED","MANUAL_REVIEW","DONE");
        if(!allowed.contains(status)) throw new IllegalArgumentException("Illegal result transition");
        if(status.equals("DONE")) {
            GrantRules.check(Boolean.TRUE.equals(result.get("verification_ok")),"반영 확인 없는 완료 결과입니다.");
            if(execution) {
                Integer receipts=jdbc.queryForObject("SELECT count(*) FROM grant_receipts WHERE problem_id=? AND idempotency_key=?",
                    Integer.class,id,problem.get("idempotency_key"));
                GrantRules.check(receipts!=null && receipts==1,"실행 영수증 없는 완료 결과입니다.");
            }
        }
        UUID approver=(UUID)problem.get("approver_id"),resourceId=null;
        Map<String,Object> plan=null;
        String hash=null,role=null;
        String reason=result.get("reasonCode").toString();
        String proposal=result.get("proposal").toString();
        if(!execution && status.equals("WAITING_APPROVAL")) {
            try {
                @SuppressWarnings("unchecked") var candidate=(Map<String,Object>)result.get("plan");
                plan=candidate;
                approver=rules.validatePlan(problem,plan);
                resourceId=UUID.fromString(plan.get("resource_id").toString());
                role=plan.get("requested_role").toString();
                hash=json.planHash(plan);
                Object sources=result.get("evidence");
                GrantRules.check(sources instanceof List<?> list && !list.isEmpty(),"근거가 없는 계획입니다.");
            } catch(RuntimeException e) {
                status="MANUAL_REVIEW"; reason="SERVER_PLAN_VALIDATION";
                proposal="실행 계획이 서버 검증을 통과하지 못했습니다. 담당자 검토가 필요합니다.";
                plan=null; resourceId=null; role=null; hash=null;
            }
        }
        if(execution) {
            // Approved plan/approver and human decision are immutable on execution results.
            jdbc.update("""
                UPDATE problems SET status=?,diagnosis=?,proposal=?,reason_code=?,verification_ok=?,
                  agent_mode=?,updated_at=NOW() WHERE id=?
                """,status,result.get("diagnosis"),proposal,reason,result.get("verification_ok"),result.get("agent_mode"),id);
        } else {
            jdbc.update("""
                UPDATE problems SET status=?,approver_id=?,diagnosis=?,proposal=?,resource_id=?,requested_role=?,
                  evidence=?::jsonb,reason_code=?,plan=?::jsonb,plan_hash=?,verification_ok=?,agent_mode=?,
                  decision_source='AGENT',updated_at=NOW() WHERE id=?
                """,status,approver,result.get("diagnosis"),proposal,resourceId,role,
                json.write(result.getOrDefault("evidence",List.of())),reason,
                plan==null?null:json.write(plan),hash,result.get("verification_ok"),result.get("agent_mode"),id);
        }
    }

    // Old queued results/checkpoints can be replayed after upgrading the producer.
    static Map<String,Object> normalizeResult(Map<String,Object> raw) {
        var result=new LinkedHashMap<>(raw);
        if("ON_HOLD".equals(result.get("status"))) result.put("status","REJECTED");
        if("INSUFFICIENT_BUDGET".equals(result.get("reasonCode")))
            result.put("reasonCode","BUDGET_INSUFFICIENT");
        return result;
    }
}
