package com.unlockops.reclaim;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.common.workflow.WorkflowStore;
import com.unlockops.contracts.v2.WorkflowTypes.ReclaimExecutionReceipt;
import java.time.OffsetDateTime;
import java.util.*;
import org.springframework.stereotype.Repository;
import static com.unlockops.common.workflow.WorkflowStore.*;

@Repository
public class ReclaimExecutionRepository {
    public record Target(UUID id, UUID companyId, UUID assignmentId, UUID episodeId, String ruleCode,
                         boolean open, String assignmentStatus, String employeeName, String resourceName, boolean mock) {}
    public record Review(UUID runId, boolean confirmed) {}
    public record Saved(String requestHash, ReclaimExecutionReceipt receipt) {}
    private final WorkflowStore db;
    public ReclaimExecutionRepository(WorkflowStore db) { this.db=db; }

    public Target target(UUID id,boolean lock) {
        var t=db.one("""
            SELECT jsonb_build_object('id',t.id,'company_id',t.company_id,'assignment_id',t.assignment_id,
              'episode_id',t.episode_id,'rule_code',t.rule_code,'open',t.closed_at IS NULL,
              'assignment_status',a.status,'employee_name',u.name,'resource_name',r.name,'mock',c.is_mock)
            FROM reclaim_targets t JOIN access_assignments a ON a.id=t.assignment_id
            JOIN users u ON u.id=a.user_id JOIN resources r ON r.id=a.resource_id JOIN companies c ON c.id=a.company_id
            WHERE t.id=?
            """+(lock?" FOR UPDATE OF a,t":""),id);
        return new Target(uuid(t,"id"),uuid(t,"company_id"),uuid(t,"assignment_id"),uuid(t,"episode_id"),str(t,"rule_code"),
            t.path("open").asBoolean(),str(t,"assignment_status"),str(t,"employee_name"),str(t,"resource_name"),t.path("mock").asBoolean());
    }

    /** Includes snapshot rows without reports, so newer partial/unknown/in-flight evidence cannot be bypassed. */
    public Optional<Review> latestReview(UUID assignment,UUID target) {
        var rows=db.rows("""
            SELECT jsonb_build_object('run_id',r.id,'confirmed',
              r.status='DONE' AND r.scan_complete AND i.candidate_status='PENDING_REVIEW'
              AND NOT i.review_required AND i.target_id=?)
            FROM reclaim_snapshot_items s JOIN reclaim_snapshots snap ON snap.id=s.snapshot_id
            JOIN reclaim_runs r ON r.id=snap.run_id
            LEFT JOIN reclaim_run_items i ON i.run_id=r.id AND i.assignment_id=s.assignment_id
            WHERE s.assignment_id=? ORDER BY snap.as_of DESC,r.created_at DESC,r.id DESC LIMIT 1
            """,target,assignment);
        return rows.stream().findFirst().map(x->new Review(uuid(x,"run_id"),x.path("confirmed").asBoolean()));
    }
    public Optional<ReclaimExecutionReceipt> receipt(UUID assignment) {
        return db.rows("SELECT result FROM reclaim_execution_receipts WHERE assignment_id=?",assignment).stream()
            .findFirst().map(x->db.decode(x,ReclaimExecutionReceipt.class));
    }
    public Optional<Saved> request(UUID company,UUID actor,String key) {
        return db.rows("SELECT to_jsonb(r) FROM reclaim_execution_receipts r WHERE company_id=? AND executed_by=? AND client_request_key=?",company,actor,key)
            .stream().findFirst().map(x->new Saved(str(x,"request_hash"),db.decode(x.path("result"),ReclaimExecutionReceipt.class)));
    }
    public void lockCompany(UUID company) {
        db.mutex("v2-grant:"+company);
        db.mutex("reclaim-company:"+company);
    }
    public boolean providerPresent(UUID assignment) {
        return db.exists("SELECT EXISTS(SELECT 1 FROM mock_entitlement_memberships WHERE assignment_id=?)",assignment);
    }
    public void revoke(UUID assignment,UUID review,OffsetDateTime time) {
        db.jdbc.update("DELETE FROM mock_entitlement_memberships WHERE assignment_id=?",assignment);
        conflict(db.jdbc.update("UPDATE access_assignments SET status='INACTIVE',ended_at=? WHERE id=? AND status='ACTIVE'",time,assignment)==1,"할당 상태가 변경되었습니다.");
        db.jdbc.update("UPDATE reclaim_targets SET candidate_status='RECLAIMED',reclaimed_at=?,closed_at=? WHERE assignment_id=? AND closed_at IS NULL",time,time,assignment);
        // The frozen report stays unchanged; this column records the subsequent human action.
        db.jdbc.update("UPDATE reclaim_run_items SET action_taken='REVOKED' WHERE run_id=? AND assignment_id=?",review,assignment);
    }
    public boolean verified(UUID assignment) {
        return db.exists("""
            SELECT EXISTS(SELECT 1 FROM access_assignments a WHERE a.id=? AND a.status='INACTIVE' AND a.ended_at IS NOT NULL
              AND NOT EXISTS(SELECT 1 FROM mock_entitlement_memberships m WHERE m.assignment_id=a.id)
              AND NOT EXISTS(SELECT 1 FROM reclaim_targets t WHERE t.assignment_id=a.id AND t.closed_at IS NULL))
            """,assignment);
    }
    public void save(UUID company,UUID actor,String key,String hash,ReclaimExecutionReceipt receipt) {
        db.jdbc.update("""
            INSERT INTO reclaim_execution_receipts(id,company_id,assignment_id,target_id,episode_id,review_run_id,
              executed_by,executed_at,reason,client_request_key,request_hash,verification_ok,result)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,true,?::jsonb)
            """,UUID.fromString(receipt.id()),company,UUID.fromString(receipt.assignmentId()),UUID.fromString(receipt.targetId()),
            UUID.fromString(receipt.episodeId()),UUID.fromString(receipt.reviewRunId()),actor,OffsetDateTime.parse(receipt.executedAt()),receipt.reason(),key,hash,db.json.write(receipt));
    }
    public List<ReclaimExecutionReceipt> history(UUID company,UUID actor,int offset) {
        return db.rows("""
            SELECT e.result FROM reclaim_execution_receipts e JOIN access_assignments a ON a.id=e.assignment_id
            JOIN users u ON u.id=a.user_id JOIN resources r ON r.id=a.resource_id
            WHERE e.company_id=? AND EXISTS(SELECT 1 FROM operator_assignments o
              WHERE o.user_id=? AND o.company_id=e.company_id AND o.department_id=u.department_id AND o.platform=r.platform
                AND o.capability IN ('RECLAIM_REVIEWER','IT_HEAD'))
            ORDER BY e.executed_at DESC,e.id DESC LIMIT 51 OFFSET ?
            """,company,actor,offset).stream().map(x->db.decode(x,ReclaimExecutionReceipt.class)).toList();
    }
}
