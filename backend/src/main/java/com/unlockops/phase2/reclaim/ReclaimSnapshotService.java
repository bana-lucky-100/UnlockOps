package com.unlockops.phase2.reclaim;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.contracts.v2.Phase2Types.*;
import com.unlockops.phase2.common.Phase2Store;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import static com.unlockops.phase2.common.Phase2Store.*;

@Service
public class ReclaimSnapshotService {
    private final Phase2Store db;
    public ReclaimSnapshotService(Phase2Store db) {this.db=db;}
    /** Called once inside run-creation transaction. The set and evaluated reports are append-only. */
    public boolean create(UUID run,JsonNode scope,OffsetDateTime time) {
        UUID company=uuid(scope,"company_id");
        var policies=db.rows("SELECT to_jsonb(p) FROM policy_revisions p WHERE company_id=? ORDER BY revision DESC",company);
        if(policies.isEmpty()) return false;
        var policy=policies.getFirst();
        if(!hash(str(policy,"content")).equals(str(policy,"source_hash")) || policies.stream().anyMatch(x->!uuid(x,"policy_id").equals(uuid(policy,"policy_id")))) return false;
        var rules=db.rows("""
            SELECT to_jsonb(x) FROM (SELECT DISTINCT ON (rule_id) * FROM reclaim_rules WHERE company_id=? ORDER BY rule_id,revision DESC) x
            """,company);
        if(rules.size()!=2 || rules.stream().map(x->str(x,"code")).distinct().count()!=2 || rules.stream().anyMatch(x->
            !uuid(x,"policy_id").equals(uuid(policy,"policy_id")) || x.path("policy_revision").intValue()!=policy.path("revision").intValue())) return false;
        // One SQL statement freezes all changing facts in one MVCC snapshot.
        var facts=db.rows("""
            SELECT jsonb_build_object('assignment_id',a.id,'company_id',a.company_id,'user_id',a.user_id,
              'department_id',u.department_id,'platform',r.platform,'entitlement_id',a.entitlement_id,
              'employment_status',u.employment_status,'origin_tf_id',a.origin_tf_id,'granted_at',a.granted_at,
              'tf_ends_on',t.ends_on,'last_used_at',usage.last_used_at,'observation_status',usage.observation_status,
              'observed_at',usage.observed_at,
              'other_active_tf',EXISTS(SELECT 1 FROM tf_members m JOIN tfs other ON other.id=m.tf_id
                WHERE m.user_id=a.user_id AND m.active AND m.tf_id IS DISTINCT FROM a.origin_tf_id
                  AND other.starts_on<=? AND (other.ends_on IS NULL OR other.ends_on>=?)),
              'retention',EXISTS(SELECT 1 FROM retention_exceptions re WHERE re.assignment_id=a.id AND re.valid_from<=? AND re.valid_until>?),
              'price',(SELECT CASE WHEN count(DISTINCT p.pricing_id)=1 THEN (jsonb_agg(to_jsonb(p) ORDER BY p.revision DESC))->0 ELSE NULL END FROM pricing_revisions p WHERE p.entitlement_id=a.entitlement_id
                AND p.entitlement_revision=a.entitlement_revision AND p.effective_from<=?
                AND (p.effective_until IS NULL OR p.effective_until>=?) AND p.policy_id=? AND p.policy_revision=?))
            FROM access_assignments a JOIN entitlements e ON e.id=a.entitlement_id JOIN resources r ON r.id=a.resource_id
            JOIN users u ON u.id=a.user_id LEFT JOIN tfs t ON t.id=a.origin_tf_id LEFT JOIN assignment_usage usage ON usage.assignment_id=a.id
            JOIN reclaim_scopes s ON s.id=?
            WHERE a.company_id=s.company_id AND u.department_id=s.department_id AND a.status='ACTIVE' AND e.kind='SEAT'
              AND a.granted_at<=? AND s.platforms @> jsonb_build_array(r.platform)
              AND (s.selection_mode='DEPARTMENT' OR EXISTS(SELECT 1 FROM reclaim_scope_assignments sa WHERE sa.scope_id=s.id AND sa.assignment_id=a.id))
            ORDER BY a.id
            """,time.toLocalDate(),time.toLocalDate(),time,time,time.toLocalDate(),time.toLocalDate(),uuid(policy,"policy_id"),policy.path("revision").intValue(),uuid(scope,"id"),time);
        UUID snapshot=UUID.randomUUID();
        var context=db.json.tree(db.json.write(Map.of("policy",policy,"rules",rules,"policy_hash",str(policy,"source_hash"))));
        db.jdbc.update("""
            INSERT INTO reclaim_snapshots(id,company_id,run_id,as_of,policy_id,policy_revision,expected_count,context) VALUES(?,?,?,?,?,?,?,?::jsonb)
            """,snapshot,company,run,time,uuid(policy,"policy_id"),policy.path("revision").intValue(),facts.size(),context.toString());
        long ordinal=0;
        for(var f:facts) {
            var candidate=db.checked(ReclaimPolicy.evaluate(f,policy,rules,time),ReclaimCandidate.class);
            var frozen=db.json.tree(db.json.write(Map.of("facts",f,"candidate",candidate)));
            db.jdbc.update("INSERT INTO reclaim_snapshot_items(snapshot_id,company_id,ordinal,assignment_id,facts) VALUES(?,?,?,?,?::jsonb)",snapshot,company,++ordinal,uuid(f,"assignment_id"),frozen.toString());
        }
        db.jdbc.update("UPDATE reclaim_runs SET snapshot_id=?,as_of=? WHERE id=?",snapshot,time,run);return true;
    }
    @Transactional(readOnly=true)
    public Map<String,Object> context(UUID run) {
        var r=db.run(run,false);
        var snapshot=db.one("SELECT to_jsonb(s) FROM reclaim_snapshots s WHERE run_id=?",run);
        return Map.of("schema_version",2,"run_id",run,"job_event_id",r.path("active_job_event_id"),"snapshot_id",snapshot.path("id"),"as_of",snapshot.path("as_of"),"expected_count",snapshot.path("expected_count"),"context",snapshot.path("context"));
    }
    @Transactional(readOnly=true)
    public CandidatePage page(CandidatePageRequest request) {
        UUID run=UUID.fromString(request.runId());
        var s=db.one("SELECT to_jsonb(s) FROM reclaim_snapshots s WHERE run_id=?",run);
        conflict(request.policyHash().equals(s.path("context").path("policy_hash").asText()),"점검 정책 해시가 다릅니다.");
        long after=0;
        if(request.cursor()!=null) {
            try {
                var parts=new String(Base64.getUrlDecoder().decode(request.cursor()),StandardCharsets.UTF_8).split(":");
                if(parts.length!=3 || !parts[0].equals(str(s,"id")) || !parts[1].equals(request.policyHash()))throw new IllegalArgumentException("cursor");
                after=Long.parseLong(parts[2]);
                if(after<0||after>s.path("expected_count").asLong())throw new IllegalArgumentException("cursor");
            } catch(RuntimeException e) {throw new IllegalArgumentException("Invalid snapshot cursor",e);}
        }
        var rows=db.rows("SELECT to_jsonb(i) FROM reclaim_snapshot_items i WHERE snapshot_id=? AND ordinal>? ORDER BY ordinal LIMIT 100",uuid(s,"id"),after);
        var items=rows.stream().map(x->db.decode(x.path("facts").path("candidate"),ReclaimCandidate.class)).toList();
        long last=rows.isEmpty()?after:rows.getLast().path("ordinal").longValue();
        String next=last<s.path("expected_count").asLong()?Base64.getUrlEncoder().withoutPadding().encodeToString((str(s,"id")+":"+request.policyHash()+":"+last).getBytes(StandardCharsets.UTF_8)):null;
        return db.checked(new CandidatePage(run.toString(),str(s,"id"),str(s,"as_of"),s.path("expected_count").intValue(),next,items),CandidatePage.class);
    }
    @Transactional(readOnly=true)
    public List<JsonNode> history(NotificationHistoryRequest request) {
        UUID run=UUID.fromString(request.runId());var r=db.run(run,false);
        var result=new ArrayList<JsonNode>();
        for(String id:request.assignmentIds()) {
            UUID assignment=UUID.fromString(id);
            conflict(db.exists("SELECT EXISTS(SELECT 1 FROM reclaim_snapshot_items WHERE snapshot_id=? AND assignment_id=?)",uuid(r,"snapshot_id"),assignment),"스냅샷 범위 밖의 할당입니다.");
            result.addAll(db.rows("""
                SELECT jsonb_build_object('assignment_id',t.assignment_id,'target_id',t.id,'episode_id',t.episode_id,
                'candidate_status',t.candidate_status,'notified_at',t.notified_at,'notifications',
                  (SELECT coalesce(jsonb_agg(to_jsonb(n)),'[]') FROM reclaim_notifications n WHERE n.target_id=t.id))
                FROM reclaim_targets t WHERE t.assignment_id=? ORDER BY t.opened_at DESC
                """,assignment));
        }
        return result;
    }
}
