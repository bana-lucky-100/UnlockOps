package com.unlockops.phase2.reclaim;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.contracts.v2.Phase2Types.*;
import com.unlockops.phase2.common.Phase2Store;
import java.time.OffsetDateTime;
import java.util.*;
import org.springframework.stereotype.Service;
import static com.unlockops.phase2.common.Phase2Store.*;

/** Snapshot validation, episode reuse and in-app delivery commit with the inbox event. */
@Service
public class ReclaimResultService {
    private final Phase2Store db;
    public ReclaimResultService(Phase2Store db) {this.db=db;}
    public void apply(JsonNode run,ReclaimEvent event) {
        if(!Set.of("RECEIVED","DIAGNOSING","EXECUTING").contains(str(run,"status")))return;
        UUID id=uuid(run,"id"),company=uuid(run,"company_id");
        if("PROGRESS".equals(event.eventType())) {
            db.jdbc.update("UPDATE reclaim_runs SET status='DIAGNOSING',message='고정된 조회 범위를 점검하고 있습니다.',updated_at=now() WHERE id=?",id);return;
        }
        if("FAILED".equals(event.eventType()) || event.result().status()==Status.FAILED) {
            savePartial(run,event);
            db.jdbc.update("UPDATE reclaim_runs SET status='FAILED',reason_code='SCAN_FAILED',message='일부만 조회되었거나 전체 점검에 실패했습니다. 부분 결과에는 알림을 보내지 않습니다.',scan_complete=false,needs_review_count=(SELECT count(*) FROM reclaim_run_items WHERE run_id=? AND review_required),updated_at=now() WHERE id=?",id,id);return;
        }
        if(!Boolean.TRUE.equals(event.result().scanComplete())) {
            db.jdbc.update("UPDATE reclaim_runs SET status='FAILED',reason_code='SCAN_FAILED',message='일부만 조회되어 전체 점검을 완료하지 못했습니다.',updated_at=now() WHERE id=?",id);return;
        }
        conflict(event.result().snapshotId()!=null && event.result().snapshotId().equals(str(run,"snapshot_id")) &&
            OffsetDateTime.parse(event.result().asOf()).isEqual(OffsetDateTime.parse(str(run,"as_of"))),"스냅샷 식별자가 다릅니다.");
        var frozen=db.rows("SELECT to_jsonb(i) FROM reclaim_snapshot_items i WHERE snapshot_id=? ORDER BY ordinal",uuid(run,"snapshot_id"));
        var expected=new HashMap<String,JsonNode>();for(var row:frozen)expected.put(str(row,"assignment_id"),row.path("facts"));
        var targets=event.targets()==null?List.<ReclaimCandidate>of():event.targets();
        conflict(targets.size()==expected.size(),"스냅샷 전체 결과가 필요합니다.");
        var seen=new HashSet<String>();
        for(var c:targets) {
            conflict(seen.add(c.assignmentId()) && expected.containsKey(c.assignmentId()),"조회 범위 밖 또는 중복된 할당입니다.");
            var baseline=db.decode(expected.get(c.assignmentId()).path("candidate"),ReclaimCandidate.class);
            // Explanation may be rewritten by the agent; decisions, money and citations may not.
            conflict(c.platform()==baseline.platform() && c.candidateStatus()==baseline.candidateStatus() &&
                Objects.equals(c.candidateReasonCode(),baseline.candidateReasonCode()) && Objects.equals(c.exclusionReasonCode(),baseline.exclusionReasonCode()) &&
                Objects.equals(c.reviewRequired(),baseline.reviewRequired()) && c.costImpact().equals(baseline.costImpact()) &&
                Objects.equals(c.policyEvidence(),baseline.policyEvidence()) && Objects.equals(c.factEvidence(),baseline.factEvidence()),"회수 판정·비용·근거가 고정된 서버 사실과 다릅니다.");
        }
        db.mutex("reclaim-company:"+company);
        int needsReview=0,newCandidates=0,pending=0;
        for(var c:targets) {
            UUID assignment=UUID.fromString(c.assignmentId());
            var facts=expected.get(c.assignmentId()).path("facts");
            JsonNode target=null;boolean created=false;String skip=null;
            if(Boolean.TRUE.equals(c.reviewRequired())) needsReview++;
            else if(c.candidateReasonCode()!=null) {
                var open=db.rows("SELECT to_jsonb(t) FROM reclaim_targets t WHERE assignment_id=? AND rule_code=? AND closed_at IS NULL FOR UPDATE",assignment,c.candidateReasonCode());
                if(!open.isEmpty())target=open.getFirst();
                if(target==null && c.candidateStatus()!=CandidateStatus.PENDING_REVIEW) {
                    var closed=db.rows("SELECT to_jsonb(t) FROM reclaim_targets t WHERE assignment_id=? AND rule_code=? AND candidate_status=? ORDER BY opened_at DESC LIMIT 1",assignment,c.candidateReasonCode(),c.candidateStatus().name());
                    if(!closed.isEmpty())target=closed.getFirst();
                }
                if(target==null) {
                    UUID targetId=UUID.randomUUID();
                    db.jdbc.update("""
                        INSERT INTO reclaim_targets(id,company_id,assignment_id,episode_id,rule_code,candidate_status,exclusion_reason_code,opened_at,closed_at)
                        VALUES(?,?,?,?,?,?,?,now(),CASE WHEN ? THEN NULL ELSE now() END)
                        """,targetId,company,assignment,UUID.randomUUID(),c.candidateReasonCode(),c.candidateStatus().name(),c.exclusionReasonCode(),c.candidateStatus()==CandidateStatus.PENDING_REVIEW);
                    target=db.one("SELECT to_jsonb(t) FROM reclaim_targets t WHERE id=?",targetId);created=c.candidateStatus()==CandidateStatus.PENDING_REVIEW;
                } else if(c.candidateStatus()!=CandidateStatus.PENDING_REVIEW && target.path("closed_at").isNull()) {
                    db.jdbc.update("UPDATE reclaim_targets SET candidate_status=?,exclusion_reason_code=?,closed_at=now() WHERE id=?",c.candidateStatus().name(),c.exclusionReasonCode(),uuid(target,"id"));
                }
                if(c.candidateStatus()==CandidateStatus.PENDING_REVIEW) {
                    if(target.path("notified_at").isNull())newCandidates++;
                    var recipients=db.rows("""
                        SELECT to_jsonb(u) - 'password_hash' FROM operator_assignments o JOIN users u ON u.id=o.user_id
                        WHERE o.company_id=? AND o.department_id=? AND o.platform=? AND o.capability='RECLAIM_REVIEWER'
                          AND u.employment_status='ACTIVE' AND u.role='APPROVER' ORDER BY u.id
                        """,company,uuid(facts,"department_id"),c.platform().name());
                    if(recipients.isEmpty()) {pending++;}
                    else {
                        boolean deliveredBefore=!target.path("notified_at").isNull();
                        for(var recipient:recipients) {
                            // In-app delivery is the durable inbox row itself, not an external side effect.
                            db.jdbc.update("""
                                INSERT INTO reclaim_notifications(id,company_id,target_id,recipient_id,channel,delivery_status,delivered_at,attempts)
                                VALUES(?,?,?,?,'IN_APP','DELIVERED',now(),1)
                                ON CONFLICT(target_id,recipient_id,channel) DO UPDATE SET delivery_status='DELIVERED',
                                  delivered_at=coalesce(reclaim_notifications.delivered_at,excluded.delivered_at),
                                  attempts=reclaim_notifications.attempts+1,last_error_code=NULL
                                  WHERE reclaim_notifications.delivery_status<>'DELIVERED'
                                """,UUID.randomUUID(),company,uuid(target,"id"),uuid(recipient,"id"));
                        }
                        db.jdbc.update("UPDATE reclaim_targets SET notified_at=coalesce(notified_at,now()) WHERE id=?",uuid(target,"id"));
                        if(deliveredBefore)skip="ALREADY_NOTIFIED";
                    }
                }
                target=db.one("SELECT to_jsonb(t) FROM reclaim_targets t WHERE id=?",uuid(target,"id"));
            }
            var report=new ReclaimCandidate(c.assignmentId(),target==null?null:str(target,"id"),target==null?null:str(target,"episode_id"),c.platform(),c.candidateStatus(),c.candidateReasonCode(),c.exclusionReasonCode(),skip,c.reviewRequired(),target==null?null:str(target,"notified_at"),null,"NONE",c.generationMode(),c.explanation(),c.policyEvidence(),c.factEvidence(),c.costImpact());
            db.checked(report,ReclaimCandidate.class);
            db.jdbc.update("""
                INSERT INTO reclaim_run_items(run_id,company_id,assignment_id,target_id,candidate_status,candidate_reason_code,
                  exclusion_reason_code,skip_reason_code,review_required,report,policy_evidence,fact_evidence,generation_mode,cost_status,monthly_amount,currency)
                VALUES(?,?,?,?,?,?,?,?,?,?::jsonb,?::jsonb,?::jsonb,?,?,?,?)
                """,id,company,assignment,target==null?null:uuid(target,"id"),c.candidateStatus()==null?null:c.candidateStatus().name(),c.candidateReasonCode(),c.exclusionReasonCode(),skip,
                c.reviewRequired(),db.json.write(report),db.json.write(c.policyEvidence()),db.json.write(c.factEvidence()),c.generationMode(),c.costImpact().status(),c.costImpact().monthlyAmount()==null?null:new java.math.BigDecimal(c.costImpact().monthlyAmount()),c.costImpact().currency());
        }
        String status=pending>0?"FAILED":"DONE";
        String reason=pending>0?"NOTIFICATION_FAILED":newCandidates>0 || needsReview>0?"SCAN_COMPLETED":"NO_NEW_CANDIDATES";
        db.jdbc.update("""
            UPDATE reclaim_runs SET status=?,reason_code=?,message=?,scan_complete=true,needs_review_count=?,new_candidate_count=?,pending_notification_count=?,updated_at=now() WHERE id=?
            """,status,reason,pending>0?"알림 담당자를 확인할 수 없어 필수 알림을 완료하지 못했습니다. 전달된 알림 이력은 보존됩니다.":"점검 완료: 신규 후보 "+newCandidates+"건 · 추가 확인 "+needsReview+"건. "+(newCandidates==0 && needsReview==0?"신규 회수 후보 없음":"추가 확인 항목에는 알림을 보내지 않습니다."),needsReview,newCandidates,pending,id);
    }
    private void savePartial(JsonNode run,ReclaimEvent event) {
        if(event.targets()==null || event.targets().isEmpty())return;
        conflict(Objects.equals(event.result().snapshotId(),str(run,"snapshot_id")) && event.result().asOf()!=null
            && OffsetDateTime.parse(event.result().asOf()).isEqual(OffsetDateTime.parse(str(run,"as_of"))),"부분 결과의 스냅샷이 다릅니다.");
        var seen=new HashSet<String>();
        for(var supplied:event.targets()) {
            conflict(seen.add(supplied.assignmentId()),"중복된 부분 결과입니다.");
            var row=db.one("SELECT facts FROM reclaim_snapshot_items WHERE snapshot_id=? AND assignment_id=?",uuid(run,"snapshot_id"),UUID.fromString(supplied.assignmentId()));
            // Persist the frozen server decision, never an unverified partial model report.
            var c=db.decode(row.path("candidate"),ReclaimCandidate.class);
            db.jdbc.update("""
                INSERT INTO reclaim_run_items(run_id,company_id,assignment_id,candidate_status,candidate_reason_code,
                  exclusion_reason_code,review_required,report,policy_evidence,fact_evidence,generation_mode,cost_status,monthly_amount,currency)
                VALUES(?,?,?,?,?,?,?,?::jsonb,?::jsonb,?::jsonb,?,?,?,?)
                """,uuid(run,"id"),uuid(run,"company_id"),UUID.fromString(c.assignmentId()),c.candidateStatus()==null?null:c.candidateStatus().name(),c.candidateReasonCode(),c.exclusionReasonCode(),
                c.reviewRequired(),db.json.write(c),db.json.write(c.policyEvidence()),db.json.write(c.factEvidence()),c.generationMode(),c.costImpact().status(),
                c.costImpact().monthlyAmount()==null?null:new java.math.BigDecimal(c.costImpact().monthlyAmount()),c.costImpact().currency());
        }
    }
}
