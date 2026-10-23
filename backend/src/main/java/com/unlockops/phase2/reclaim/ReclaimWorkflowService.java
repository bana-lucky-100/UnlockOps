package com.unlockops.phase2.reclaim;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.contracts.v2.Phase2Types.*;
import com.unlockops.phase2.common.*;
import com.unlockops.phase2.messaging.Phase2Jobs;
import java.time.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import static com.unlockops.phase2.common.Phase2Store.*;

@Service
public class ReclaimWorkflowService {
    private final Phase2Store db;
    private final Phase2AccessControl acl;
    private final ReclaimSnapshotService snapshots;
    private final Phase2Jobs jobs;
    private final boolean demo;
    public ReclaimWorkflowService(Phase2Store db,Phase2AccessControl acl,ReclaimSnapshotService snapshots,Phase2Jobs jobs,@Value("${app.demo-enabled:false}") boolean demo) {
        this.db=db;this.acl=acl;this.snapshots=snapshots;this.jobs=jobs;this.demo=demo;
    }
    @Transactional
    public ReclaimRunView start(UUID actor,UUID scopeId,String key) {
        forbid(demo);key(key);
        var scope=db.one("SELECT to_jsonb(s) FROM reclaim_scopes s WHERE id=?",scopeId);acl.scope(actor,scope);
        db.mutex("reclaim-company:"+str(scope,"company_id"));
        var prior=db.rows("SELECT to_jsonb(r) FROM reclaim_runs r WHERE company_id=? AND requested_by=? AND client_request_key=?",uuid(scope,"company_id"),actor,key);
        if(!prior.isEmpty()) {conflict(scopeId.equals(uuid(prior.getFirst(),"scope_id")),"동일 요청 키에 다른 범위가 사용되었습니다.");return view(prior.getFirst());}
        conflict(!db.exists("SELECT EXISTS(SELECT 1 FROM reclaim_runs WHERE scope_id=? AND status IN ('RECEIVED','DIAGNOSING','EXECUTING'))",scopeId),"이 범위의 점검이 이미 진행 중입니다. 해당 실행을 조회해 주세요.");
        return create(scope,actor,key,"MANUAL_DEMO",OffsetDateTime.now(ZoneId.of("Asia/Seoul")));
    }
    @Transactional
    public void scheduled(UUID scopeId) {
        var scope=db.one("SELECT to_jsonb(s) FROM reclaim_scopes s WHERE id=?",scopeId);
        if(!scope.path("enabled").asBoolean()) return;
        db.mutex("reclaim-company:"+str(scope,"company_id"));
        var now=OffsetDateTime.now(ZoneId.of("Asia/Seoul"));
        if(db.exists("SELECT EXISTS(SELECT 1 FROM reclaim_runs WHERE scope_id=? AND (status IN ('RECEIVED','DIAGNOSING','EXECUTING') OR (trigger='DAILY_SCHEDULE' AND schedule_date=?)))",scopeId,now.toLocalDate()))return;
        create(scope,null,null,"DAILY_SCHEDULE",now);
    }
    private ReclaimRunView create(JsonNode scope,UUID actor,String key,String trigger,OffsetDateTime now) {
        UUID id=UUID.randomUUID();
        db.jdbc.update("""
            INSERT INTO reclaim_runs(id,company_id,scope_id,trigger,scheduled_for,schedule_date,requested_by,client_request_key,request_hash,status,message)
            VALUES(?,?,?,?,?,?,?,?,?,'RECEIVED','회수 후보 점검이 접수되었습니다.')
            """,id,uuid(scope,"company_id"),uuid(scope,"id"),trigger,now,now.toLocalDate(),actor,key,hash(str(scope,"id")));
        if(!snapshots.create(id,scope,now)) {
            db.jdbc.update("UPDATE reclaim_runs SET status='MANUAL_REVIEW',reason_code='MISSING_SOURCE_EVIDENCE',message='유효한 정책·회수 규칙을 확인할 수 없습니다.' WHERE id=?",id);
        } else jobs.reclaim(id,trigger,str(scope,"scope_key"),now.toString());
        return view(db.run(id,false));
    }
    public ReclaimRunView view(JsonNode r) {
        return db.checked(new ReclaimRunView(2,"RECLAIM_SCAN",Status.valueOf(str(r,"status")),str(r,"reason_code"),str(r,"message"),null,0,List.of(),null,str(r,"id"),str(r,"snapshot_id"),str(r,"as_of"),r.path("scan_complete").asBoolean(),r.path("needs_review_count").asInt(),r.path("new_candidate_count").asInt(),r.path("pending_notification_count").asInt()),ReclaimRunView.class);
    }
    @Transactional(readOnly=true)
    public ReclaimRunView get(UUID actor,UUID id) {
        var r=db.run(id,false);acl.scope(actor,db.one("SELECT to_jsonb(s) FROM reclaim_scopes s WHERE id=?",uuid(r,"scope_id")));return view(r);
    }
    @Transactional(readOnly=true)
    public List<JsonNode> items(UUID actor,UUID id) {
        get(actor,id);
        return db.rows("SELECT report FROM reclaim_run_items WHERE run_id=? ORDER BY assignment_id",id);
    }
    @Transactional(readOnly=true)
    public List<JsonNode> scopes(UUID actor) {
        var user=acl.actor(actor);
        return db.rows("SELECT to_jsonb(s) FROM reclaim_scopes s WHERE company_id=? ORDER BY scope_key",uuid(user,"company_id")).stream().filter(s->acl.canScope(actor,s)).toList();
    }
    @Transactional(readOnly=true)
    public Map<String,Object> overview(UUID actor) {
        var user=acl.actor(actor);
        var all=db.rows("SELECT to_jsonb(r) FROM reclaim_runs r WHERE company_id=? ORDER BY created_at DESC",uuid(user,"company_id"));
        var allowed=new HashSet<UUID>();scopes(actor).forEach(s->allowed.add(uuid(s,"id")));
        var runs=all.stream().filter(r->allowed.contains(uuid(r,"scope_id"))).toList();
        JsonNode last=runs.stream().filter(r->!Set.of("RECEIVED","DIAGNOSING","EXECUTING").contains(str(r,"status"))).findFirst().orElse(null);
        JsonNode active=runs.stream().filter(r->Set.of("RECEIVED","DIAGNOSING","EXECUTING").contains(str(r,"status"))).findFirst().orElse(null);
        var targets=new ArrayList<ReclaimCandidate>();
        for(var t:db.rows("""
            SELECT to_jsonb(t) FROM reclaim_targets t JOIN access_assignments a ON a.id=t.assignment_id
            JOIN users u ON u.id=a.user_id JOIN resources r ON r.id=a.resource_id
            WHERE t.company_id=? AND t.closed_at IS NULL AND EXISTS(SELECT 1 FROM operator_assignments o
              WHERE o.user_id=? AND o.company_id=t.company_id AND o.department_id=u.department_id AND o.platform=r.platform
              AND o.capability IN ('RECLAIM_REVIEWER','IT_HEAD')) ORDER BY t.opened_at DESC
            """,uuid(user,"company_id"),actor)) {
            var reports=db.rows("SELECT i.report FROM reclaim_run_items i JOIN reclaim_runs r ON r.id=i.run_id WHERE i.target_id=? ORDER BY r.created_at DESC LIMIT 1",uuid(t,"id"));
            if(!reports.isEmpty())targets.add(withPersonalRead(db.decode(reports.getFirst(),ReclaimCandidate.class),actor));
        }
        var out=new LinkedHashMap<String,Object>();out.put("last_run",last==null?null:view(last));out.put("active_run",active==null?null:view(active));out.put("targets",targets);
        if(last==null || !"DONE".equals(str(last,"status")))out.put("summary",null);
        else {
            var sums=new TreeMap<String,java.math.BigDecimal>();int unknown=0;
            for(var t:targets) {if("UNKNOWN".equals(t.costImpact().status()))unknown++;else sums.merge(t.costImpact().currency(),new java.math.BigDecimal(t.costImpact().monthlyAmount()),java.math.BigDecimal::add);}
            var money=new TreeMap<String,String>();sums.forEach((c,v)->money.put(c,v.setScale(2).toPlainString()));
            var summary=new LinkedHashMap<String,Object>();summary.put("review_target_count",targets.size());summary.put("new_candidate_count",last.path("new_candidate_count").asInt());
            summary.put("newly_notified_count",db.jdbc.queryForObject("""
                SELECT count(*) FROM reclaim_run_items i JOIN reclaim_notifications n ON n.target_id=i.target_id
                WHERE i.run_id=? AND n.recipient_id=? AND n.delivered_at>= (SELECT created_at FROM reclaim_runs WHERE id=?)
                """,Integer.class,uuid(last,"id"),actor,uuid(last,"id")));
            summary.put("needs_review_count",last.path("needs_review_count").asInt());summary.put("unknown_cost_target_count",unknown);
            summary.put("unread_count",notifications(actor).stream().filter(n->n.path("read_at").isNull()).count());summary.put("monthly_saving_by_currency",money);out.put("summary",summary);
        }
        return out;
    }
    @Transactional(readOnly=true)
    public ReclaimCandidate target(UUID actor,UUID id) {
        var target=db.one("SELECT to_jsonb(t) FROM reclaim_targets t WHERE id=?",id);acl.assignment(actor,uuid(target,"assignment_id"));
        var report=db.one("SELECT i.report FROM reclaim_run_items i JOIN reclaim_runs r ON r.id=i.run_id WHERE i.target_id=? ORDER BY r.created_at DESC LIMIT 1",id);
        return withPersonalRead(db.decode(report,ReclaimCandidate.class),actor);
    }
    private ReclaimCandidate withPersonalRead(ReclaimCandidate c,UUID actor) {
        var notifications=db.rows("SELECT to_jsonb(n) FROM reclaim_notifications n WHERE target_id=? AND recipient_id=? AND channel='IN_APP'",UUID.fromString(c.targetId()),actor);
        String read=notifications.isEmpty()?null:str(notifications.getFirst(),"read_at");
        return new ReclaimCandidate(c.assignmentId(),c.targetId(),c.episodeId(),c.platform(),c.candidateStatus(),c.candidateReasonCode(),c.exclusionReasonCode(),c.skipReasonCode(),c.reviewRequired(),c.notifiedAt(),read,c.actionTaken(),c.generationMode(),c.explanation(),c.policyEvidence(),c.factEvidence(),c.costImpact());
    }
    @Transactional(readOnly=true)
    public List<JsonNode> notifications(UUID actor) {
        acl.actor(actor);
        return db.rows("""
            SELECT to_jsonb(n) FROM reclaim_notifications n JOIN reclaim_targets t ON t.id=n.target_id
              JOIN access_assignments a ON a.id=t.assignment_id JOIN users u ON u.id=a.user_id JOIN resources r ON r.id=a.resource_id
            WHERE n.recipient_id=? AND n.delivery_status='DELIVERED' AND EXISTS(SELECT 1 FROM operator_assignments o
              WHERE o.user_id=? AND o.company_id=t.company_id AND o.department_id=u.department_id AND o.platform=r.platform
                AND o.capability IN ('RECLAIM_REVIEWER','IT_HEAD')) ORDER BY n.delivered_at DESC LIMIT 100
            """,actor,actor);
    }
    @Transactional
    public Map<String,String> read(UUID actor,UUID notification) {
        acl.actor(actor);
        var n=db.one("SELECT to_jsonb(n) FROM reclaim_notifications n WHERE id=? AND recipient_id=? FOR UPDATE",notification,actor);
        var t=db.one("SELECT to_jsonb(t) FROM reclaim_targets t WHERE id=?",uuid(n,"target_id"));acl.assignment(actor,uuid(t,"assignment_id"));
        conflict("DELIVERED".equals(str(n,"delivery_status")),"전달되지 않은 알림입니다.");
        db.jdbc.update("UPDATE reclaim_notifications SET read_at=coalesce(read_at,now()) WHERE id=?",notification);
        return Map.of("read_at",str(db.one("SELECT to_jsonb(n) FROM reclaim_notifications n WHERE id=?",notification),"read_at"));
    }
}
