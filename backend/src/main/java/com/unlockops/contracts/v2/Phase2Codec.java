package com.unlockops.contracts.v2;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import static com.unlockops.contracts.v2.Phase2Types.*;

/** Explicit v2 boundary. Legacy Jsons/AgentResult never silently opt into this codec. */
public final class Phase2Codec {
    private final ObjectMapper mapper = new ObjectMapper().findAndRegisterModules()
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .disable(MapperFeature.ALLOW_COERCION_OF_SCALARS)
        .setSerializationInclusion(JsonInclude.Include.ALWAYS);
    private final Validator validator = Validation.buildDefaultValidatorFactory().getValidator();

    public <T> T read(String raw, Class<T> type) {
        try {
            JsonNode tree = mapper.readTree(raw);
            if (!tree.isObject()) throw new IllegalArgumentException("Expected an object");
            if (Set.of(GrantPlanV2.class, AccessView.class, ReclaimRunView.class, AccessJob.class,
                    ReclaimJob.class, AccessEvent.class, ReclaimEvent.class).contains(type))
                require(tree.path("schema_version").isIntegralNumber() && tree.path("schema_version").intValue()==2,
                    "Explicit schema_version=2 is required");
            validateTimestamps(tree);
            T value = mapper.treeToValue(tree, type);
            var violations = validator.validate(value);
            require(violations.isEmpty(), "Invalid v2 fields: " + violations);
            if (value instanceof ApprovalDecisionInput d && !"APPROVE".equals(d.action()))
                require(d.reason()!=null && !d.reason().isBlank(),"Decision reason required");
            if (value instanceof GrantPlanV2 p) validatePlan(p);
            if (value instanceof AccessView v) validateAccess(v);
            if (value instanceof ReclaimRunView v) validateReclaim(v);
            if (value instanceof AccessJob j) {
                boolean execute = "EXECUTE".equals(j.jobType());
                require(execute == (j.planHash()!=null && j.idempotencyKey()!=null), "Execution identity required");
                if (!execute) require(j.planHash()==null && j.idempotencyKey()==null,"Analysis has no execution identity");
            }
            if (value instanceof AccessEvent e) {
                validateAccess(e.result());
                require(e.problemId().equals(e.result().problemId()),"Problem identity mismatch");
                require(!"ANALYZED".equals(e.eventType()) || "ANALYZE".equals(e.jobType()),"Analysis event mismatch");
                require(!"EXECUTED".equals(e.eventType()) || "EXECUTE".equals(e.jobType()),"Execution event mismatch");
                if ("EXECUTED".equals(e.eventType())) {
                    require(Set.of(Status.DONE,Status.FAILED).contains(e.result().status()),"Execution result must be terminal");
                    if (e.result().status()==Status.DONE) require("ACCESS_VERIFIED".equals(e.result().resultType()),"Execution cannot complete as guidance");
                }
                require(!"ANALYZED".equals(e.eventType()) || !"ACCESS_VERIFIED".equals(e.result().resultType()),"Analysis cannot claim grant completion");
                require(!"FAILED".equals(e.eventType()) || e.result().status()==Status.FAILED,"Failed event mismatch");
            }
            if (value instanceof ReclaimCandidate c) validateCandidate(c);
            if (value instanceof CandidatePage p) for (var c:p.items()) validateCandidate(c);
            if (value instanceof ReclaimEvent e) {
                validateReclaim(e.result());
                require(e.runId().equals(e.result().runId()),"Run identity mismatch");
                require(e.result().status()!=Status.DONE,"Worker cannot finalize delivery");
                var ids=new HashSet<String>();
                for (var c:optional(e.targets())) { validateCandidate(c); require(ids.add(c.assignmentId()),"Duplicate assignment"); }
                if ("RECLAIM_CHECKED".equals(e.eventType()) && e.result().status()==Status.EXECUTING)
                    require(Boolean.TRUE.equals(e.result().scanComplete()) && zero(e.result().needsReviewCount())==optional(e.targets()).stream().filter(c->Boolean.TRUE.equals(c.reviewRequired())).count(),"Incomplete scan or inconsistent review count");
                require(!"FAILED".equals(e.eventType()) || e.result().status()==Status.FAILED,"Failed event mismatch");
            }
            return value;
        } catch (IllegalArgumentException e) { throw e; }
        catch (Exception e) { throw new IllegalArgumentException("Invalid v2 contract",e); }
    }

    private void validatePlan(GrantPlanV2 p) {
        require(p.schemaVersion()!=null && p.schemaVersion()==2,"Plan version required");
        require(!p.approverIds().contains(p.requesterId()),"Self approval forbidden");
        require(new HashSet<>(p.approverIds()).size()==p.approverIds().size(),"Duplicate approvers");
        require(!"NO_ADDITIONAL_COST".equals(p.costBasis()) || "0.00".equals(p.monthlyAmount()),"Invalid zero cost");
    }

    public String canonicalPlan(GrantPlanV2 plan) {
        validatePlan(plan);
        require(validator.validate(plan).isEmpty(),"Invalid plan");
        try {
            JsonNode fields=mapper.valueToTree(plan);
            var sorted=new TreeMap<String,JsonNode>();
            fields.fields().forEachRemaining(e->sorted.put(e.getKey(),e.getValue()));
            return mapper.writeValueAsString(sorted);
        } catch (Exception e) { throw new IllegalArgumentException("Invalid plan",e); }
    }

    public String planHash(GrantPlanV2 plan) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
            .digest(canonicalPlan(plan).getBytes(StandardCharsets.UTF_8))); }
        catch (Exception e) { throw new IllegalArgumentException("Invalid plan",e); }
    }

    private void common(Status status, String reason, Integer current, Integer total, List<ApprovalStep> input) {
        var steps=optional(input);
        String expected=reason==null ? null : REASON_STATUSES.get(reason);
        require(expected==null || expected.equals(status.name()),"Reason/status mismatch");
        require(status==Status.RECEIVED || status==Status.DIAGNOSING || reason!=null,"Reason required");
        require(zero(total)==steps.size(),"Approval count mismatch");
        var actors=new HashSet<String>();
        for (int i=0;i<steps.size();i++) {
            var s=steps.get(i);
            require(s.step()==i+1 && actors.add(s.approverId()),"Invalid approval ordering/actors");
            boolean decided=Set.of(ApprovalStatus.APPROVED,ApprovalStatus.REJECTED,ApprovalStatus.ON_HOLD).contains(s.status());
            require(decided==(s.actedAt()!=null),"Invalid decision timestamp");
            if (s.status()==ApprovalStatus.REJECTED || s.status()==ApprovalStatus.ON_HOLD)
                require(s.reason()!=null && !s.reason().isBlank(),"Decision reason required");
            if (s.status()==ApprovalStatus.PENDING || s.status()==ApprovalStatus.WAITING)
                require(s.reason()==null,"Unprocessed decision has reason");
            if (status==Status.WAITING_APPROVAL) {
                require(current!=null && current>=1 && current<=steps.size(),"Current step required");
                require(s.status()==(s.step()<current ? ApprovalStatus.APPROVED : s.step().equals(current) ? ApprovalStatus.WAITING : ApprovalStatus.PENDING),"Approval step bypass");
            } else require(s.status()!=ApprovalStatus.WAITING,"Unexpected waiting step");
        }
        require(status==Status.WAITING_APPROVAL ? current!=null && !steps.isEmpty() : current==null,"Invalid current step");
    }

    private void validateAccess(AccessView v) {
        common(v.status(),v.reasonCode(),v.currentStep(),v.totalSteps(),v.approvalSteps());
        require((v.status()==Status.DONE)==(v.resultType()!=null),"Completion type mismatch");
        if ("ACCESS_VERIFIED".equals(v.resultType()))
            require(Boolean.TRUE.equals(v.verificationOk()) && "VERIFIED".equals(v.reasonCode()),"Verification required");
        if ("GUIDANCE".equals(v.resultType()))
            require(v.verificationOk()==null && Set.of("RAG_GUIDANCE","ALREADY_HAS_ACCESS").contains(v.reasonCode()),"Invalid guidance completion");
        if (v.status()==Status.EXECUTING || "ACCESS_VERIFIED".equals(v.resultType()))
            require(!optional(v.approvalSteps()).isEmpty() && v.approvalSteps().stream().allMatch(s->s.status()==ApprovalStatus.APPROVED),"All approvals required");
        if (Boolean.TRUE.equals(v.verificationOk())) require("ACCESS_VERIFIED".equals(v.resultType()),"Unexpected verification success");
        require("VERIFICATION_FAILED".equals(v.reasonCode())==Boolean.FALSE.equals(v.verificationOk()),"Mismatch is false; lookup failure is null");
    }

    private void validateReclaim(ReclaimRunView v) {
        common(v.status(),v.reasonCode(),v.currentStep(),v.totalSteps(),v.approvalSteps());
        require(!Set.of(Status.WAITING_APPROVAL,Status.ON_HOLD,Status.REJECTED,Status.MANUAL_REVIEW).contains(v.status()),"Scan has no approval/manual review states");
        require(zero(v.totalSteps())==0 && v.verificationOk()==null,"Scan is not a grant");
        require((v.snapshotId()==null)==(v.asOf()==null),"Snapshot identity mismatch");
        if (Boolean.TRUE.equals(v.scanComplete())) require(v.snapshotId()!=null,"Snapshot required");
        if (v.status()==Status.DONE) {
            require(Boolean.TRUE.equals(v.scanComplete()) && zero(v.pendingNotificationCount())==0,"Unfinished scan");
            require(Set.of("SCAN_COMPLETED","NO_NEW_CANDIDATES").contains(v.reasonCode()),"Invalid scan completion");
            require(!"NO_NEW_CANDIDATES".equals(v.reasonCode()) || (zero(v.newCandidateCount())==0 && zero(v.needsReviewCount())==0),"Candidates/checks reported as none");
        }
        if(v.summary()!=null) require(zero(v.summary().needsReviewCount())==zero(v.needsReviewCount()) && zero(v.summary().newCandidateCount())==zero(v.newCandidateCount()) && zero(v.summary().pendingNotificationCount())==zero(v.pendingNotificationCount()),"Summary differs from scan counts");
    }

    private void validateCandidate(ReclaimCandidate c) {
        boolean review=Boolean.TRUE.equals(c.reviewRequired());
        require(review==(c.candidateStatus()==null),"Unconfirmed row requires review");
        require(review || (!optional(c.policyEvidence()).isEmpty() && !optional(c.factEvidence()).isEmpty()),"Evidence required");
        require((c.targetId()==null)==(c.episodeId()==null),"Episode identity mismatch");
        if (c.candidateStatus()==CandidateStatus.PENDING_REVIEW) require(c.candidateReasonCode()!=null && c.exclusionReasonCode()==null,"Candidate reason required");
        if (c.candidateStatus()==CandidateStatus.RETAINED) require("RETENTION_APPROVED".equals(c.exclusionReasonCode()),"Retention required");
        if (c.candidateStatus()==CandidateStatus.EXCLUDED) require(c.exclusionReasonCode()!=null && Set.of("ACTIVE_OTHER_TF","USAGE_RESUMED").contains(c.exclusionReasonCode()),"Exclusion required");
        if (c.skipReasonCode()!=null) require(c.notifiedAt()!=null && c.episodeId()!=null && c.candidateStatus()==CandidateStatus.PENDING_REVIEW,"Existing delivery required");
        require(c.readAt()==null || c.notifiedAt()!=null,"Reading is not delivery");
        var cost=c.costImpact();
        if ("UNKNOWN".equals(cost.status())) require(cost.monthlyAmount()==null,"Unknown cost is null");
        else require(cost.monthlyAmount()!=null && cost.currency()!=null && cost.basis()!=null,"Cost basis required");
    }
    private static void validateTimestamps(JsonNode node) {
        if (node.isArray()) { node.forEach(Phase2Codec::validateTimestamps); return; }
        if (!node.isObject()) return;
        node.fields().forEachRemaining(e -> {
            if (!e.getValue().isNull() && Set.of("acted_at","as_of","scheduled_for","observed_at","notified_at","read_at").contains(e.getKey()))
                java.time.OffsetDateTime.parse(e.getValue().asText());
            validateTimestamps(e.getValue());
        });
    }
    private static int zero(Integer n) { return n==null ? 0 : n; }
    private static <T> List<T> optional(List<T> v) { return v==null ? List.of() : v; }
    private static void require(boolean condition,String message) { if (!condition) throw new IllegalArgumentException(message); }
}
