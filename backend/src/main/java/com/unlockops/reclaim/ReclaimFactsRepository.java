package com.unlockops.reclaim;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.common.workflow.WorkflowStore;
import java.time.OffsetDateTime;
import java.util.*;
import org.springframework.stereotype.Repository;
import static com.unlockops.common.workflow.WorkflowStore.*;

/** Shared read boundary for frozen scans and live execution checks. Facts retain their source shape. */
@Repository
public class ReclaimFactsRepository {
    public record PolicyContext(JsonNode policy, List<JsonNode> rules) {}
    private final WorkflowStore db;
    public ReclaimFactsRepository(WorkflowStore db) { this.db=db; }
    public Optional<PolicyContext> policy(UUID company) {
        var policies=db.rows("SELECT to_jsonb(p) FROM policy_revisions p WHERE company_id=? ORDER BY revision DESC",company);
        if(policies.isEmpty()) return Optional.empty();
        var policy=policies.getFirst();
        if(!hash(str(policy,"content")).equals(str(policy,"source_hash")) || policies.stream().anyMatch(x->!uuid(x,"policy_id").equals(uuid(policy,"policy_id")))) return Optional.empty();
        var rules=db.rows("""
            SELECT to_jsonb(x) FROM (SELECT DISTINCT ON (rule_id) * FROM reclaim_rules WHERE company_id=? ORDER BY rule_id,revision DESC) x
            """,company);
        if(rules.size()!=2 || rules.stream().map(x->str(x,"code")).distinct().count()!=2 || rules.stream().anyMatch(x->
            !uuid(x,"policy_id").equals(uuid(policy,"policy_id")) || x.path("policy_revision").intValue()!=policy.path("revision").intValue())) return Optional.empty();
        // One SQL statement freezes all changing facts in one MVCC snapshot.
        return Optional.of(new PolicyContext(policy,rules));
    }
    private static final String FACTS = """
            SELECT jsonb_build_object('assignment_id',a.id,'company_id',a.company_id,'user_id',a.user_id,
              'department_id',u.department_id,'employee_name',u.name,'resource_name',r.name,'platform',r.platform,'entitlement_id',a.entitlement_id,
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
        """;
    public List<JsonNode> scope(UUID scope,PolicyContext context,OffsetDateTime time) {
        return db.rows(FACTS+"""
            JOIN reclaim_scopes s ON s.id=?
            WHERE a.company_id=s.company_id AND u.department_id=s.department_id AND a.status='ACTIVE' AND e.kind='SEAT'
              AND a.granted_at<=? AND s.platforms @> jsonb_build_array(r.platform)
              AND (s.selection_mode='DEPARTMENT' OR EXISTS(SELECT 1 FROM reclaim_scope_assignments sa WHERE sa.scope_id=s.id AND sa.assignment_id=a.id))
            ORDER BY a.id
            """,time.toLocalDate(),time.toLocalDate(),time,time,time.toLocalDate(),time.toLocalDate(),uuid(context.policy(),"policy_id"),context.policy().path("revision").intValue(),scope,time);
    }
    public Optional<JsonNode> assignment(UUID assignment,PolicyContext context,OffsetDateTime time) {
        var rows=db.rows(FACTS+"""
            WHERE a.id=? AND a.status='ACTIVE' AND e.kind='SEAT' AND a.granted_at<=?
            """,time.toLocalDate(),time.toLocalDate(),time,time,time.toLocalDate(),time.toLocalDate(),uuid(context.policy(),"policy_id"),context.policy().path("revision").intValue(),assignment,time);
        return rows.stream().findFirst();
    }
}
