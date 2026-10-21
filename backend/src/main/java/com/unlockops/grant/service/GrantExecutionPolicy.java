package com.unlockops.grant.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.access.dto.AccessContextResponses.*;
import com.unlockops.access.service.AccessCeilingPolicy.ExecutionRules;
import com.unlockops.grant.model.*;
import com.unlockops.grant.repository.GrantExecutionRepository.Approver;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.stereotype.Service;
import static com.unlockops.grant.service.GrantExecutionException.*;

@Service
public class GrantExecutionPolicy {
    public void validateApprover(UUID requester, UUID decidedBy, UUID assignedApprover, Profile profile,
                                 Resource resource, Membership membership, Approver actor, ExecutionRules rules) {
        UUID expected = resource.accessScope() == AccessScope.TF ? membership.leaderId() : profile.headId();
        if (expected == null || actor == null || expected.equals(requester) || !expected.equals(decidedBy)
                || !expected.equals(assignedApprover) || !expected.equals(actor.id())
                || actor.role() != rules.approverRole() || !actor.grade().atLeast(rules.minimumGrade()))
            throw conflict("APPROVER_CHANGED");
    }

    public void validateEvidence(Resource resource, JsonNode evidence, ExecutionRules rules) {
        List<String> required = new ArrayList<>(List.of("A-ACCESS-03", "A-ACCESS-04", "A-ACCESS-07",
            switch (resource.platform()) {
                case GITHUB -> "POL-03"; case JIRA -> "POL-04"; case SLACK -> "POL-05"; case NOTION -> "POL-08";
            }));
        if (resource.accessScope() == AccessScope.TF) required.add("POL-02");
        if (resource.accessScope() == AccessScope.SEAT) required.add("POL-06");
        if (evidence == null || !evidence.isArray()) throw precondition("POLICY_EVIDENCE_MISMATCH");
        for (JsonNode chunk : evidence) if (!chunk.isObject()) throw precondition("POLICY_EVIDENCE_MISMATCH");
        for (String doc : required) {
            String source = doc.startsWith("A-ACCESS-") ? "company-a-access-matrix.md" : "policy_corpus.md";
            boolean found = false;
            for (JsonNode chunk : evidence) {
                if (doc.equals(chunk.path("doc_id").asText()) && source.equals(chunk.path("source").asText())
                        && rules.sourceHashes().get(source) != null
                        && rules.sourceHashes().get(source).equals(chunk.path("source_hash").asText())
                        && !chunk.path("chunk_id").asText().isBlank() && !chunk.path("text").asText().isBlank()) {
                    found = true;
                    break;
                }
            }
            if (!found) throw precondition("POLICY_EVIDENCE_MISMATCH");
        }
    }

    /** true는 이미 보유한 권한이므로 변경 없이 영수증만 저장할 수 있음을 뜻한다. */
    public boolean validateEligibility(GrantPlan plan, Profile profile, Resource resource, Membership membership,
                                       Current current, Budget budget, ExecutionRules rules) {
        boolean seat = resource.accessScope() == AccessScope.SEAT;
        if (resource.accessScope() == AccessScope.TF && !membership.member()) throw precondition("NOT_TF_MEMBER");
        if (resource.securityGrade() == SecurityGrade.CONFIDENTIAL &&
                !Objects.equals(profile.departmentId(), resource.designatedDepartmentId()))
            throw precondition("CONFIDENTIAL_DEPARTMENT");
        if (resource.accessScope() == AccessScope.DEPARTMENT &&
                !Objects.equals(profile.departmentId(), resource.ownerDepartmentId())) throw precondition("DEPARTMENT_MISMATCH");
        if (seat) {
            if (current.role() != null && !current.role().isBlank()) throw precondition("DUPLICATE_SEAT");
            if (rules.role().isEmpty()) throw precondition("NON_DEV_SEAT");
            if (budget == null) throw precondition("BUDGET_UNAVAILABLE");
            BigDecimal remaining = new BigDecimal(budget.remainingMonthlyAmount());
            BigDecimal price = new BigDecimal(budget.unitMonthlyPrice());
            if (remaining.signum() < 0 || price.signum() <= 0) throw precondition("INVALID_POLICY_FACTS");
            if (remaining.compareTo(price) < 0) throw precondition("BUDGET_INSUFFICIENT");
        }
        String requested = plan.requestedRole().value();
        if (rules.role().isEmpty() || !family(resource).contains(rules.role())) throw precondition("UNSUPPORTED_ROLE");
        if (!family(resource).contains(requested) || rank(requested) > rank(rules.role()))
            throw precondition("ABOVE_ACCESS_CEILING");
        if (resource.platform() == Platform.JIRA && current.role() != null && Boolean.FALSE.equals(current.canBrowse()))
            throw precondition("JIRA_SCHEME_MISMATCH");
        return !seat && current.role() != null && family(resource).contains(current.role()) && rank(current.role()) >= rank(requested);
    }

    private Set<String> family(Resource resource) {
        if (resource.accessScope() == AccessScope.SEAT) return Set.of("Seat");
        return switch (resource.platform()) {
            case GITHUB -> Set.of("Read", "Write"); case JIRA -> Set.of("Viewer", "Developer");
            case SLACK -> Set.of("Member"); case NOTION -> Set.of("Can view", "Can edit");
        };
    }

    private int rank(String role) {
        return switch (role) {
            case "Read", "Viewer", "Can view", "Member", "Seat" -> 1;
            case "Write", "Developer", "Can edit" -> 2;
            default -> 0;
        };
    }
}
