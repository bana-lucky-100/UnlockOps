package com.unlockops.grant.service;

import com.unlockops.access.repository.AccessContextRepository;
import com.unlockops.access.service.AccessCeilingPolicy;
import com.unlockops.access.service.AccessCeilingPolicy.ExecutionRules;
import com.unlockops.common.json.Jsons;
import com.unlockops.grant.dto.GrantExecutionResponses.Success;
import com.unlockops.grant.model.*;
import com.unlockops.grant.repository.*;
import com.unlockops.problem.model.*;
import com.unlockops.problem.repository.ProblemRepository;
import java.util.Objects;
import java.util.UUID;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import static com.unlockops.grant.service.GrantExecutionException.*;

@Service
public class GrantExecutionService {
    private final ProblemRepository problems;
    private final GrantExecutionRepository executions;
    private final GrantRepository grants;
    private final AccessContextRepository facts;
    private final AccessCeilingPolicy source;
    private final GrantExecutionPolicy policy;
    private final Jsons json;

    public GrantExecutionService(ProblemRepository problems, GrantExecutionRepository executions, GrantRepository grants,
                                 AccessContextRepository facts, AccessCeilingPolicy source, GrantExecutionPolicy policy, Jsons json) {
        this.problems = problems; this.executions = executions; this.grants = grants; this.facts = facts;
        this.source = source; this.policy = policy; this.json = json;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public Success execute(UUID problemId, String key) {
        Problem problem;
        try {
            problem = problems.lock(problemId).orElseThrow(() -> new GrantExecutionException(HttpStatus.NOT_FOUND,
                "NOT_FOUND", "대상 요청을 찾을 수 없습니다.", false, null));
        } catch (IllegalArgumentException e) { throw conflict("PLAN_CHANGED"); }
        if (!key.equals(problem.idempotencyKey())) throw conflict("INVALID_EXECUTION_KEY");
        var previous = executions.receipt(problemId, key);
        if (previous.isPresent()) return previous.get();
        if (problem.status() != ProblemStatus.EXECUTING || problem.decisionSource() != DecisionSource.HUMAN
                || problem.decidedAt() == null || problem.approvedPlanHash() == null || problem.decidedBy() == null)
            throw conflict("APPROVAL_REQUIRED");
        GrantPlan plan = problem.plan();
        if (plan == null || plan.requestedRole() == null || plan.resourceId() == null || plan.requesterId() == null
                || !Objects.equals(json.planHash(plan), problem.planHash())
                || !Objects.equals(json.planHash(plan), problem.approvedPlanHash())) throw conflict("PLAN_CHANGED");
        if (!problemId.equals(plan.problemId()) || !problem.requesterId().equals(plan.requesterId()))
            throw conflict("PLAN_IDENTITY_MISMATCH");
        if (problem.platform() != plan.platform() || !Objects.equals(problem.resourceId(), plan.resourceId())
                || problem.requestedRole() != plan.requestedRole()) throw conflict("PLAN_CHANGED");
        executions.lockEmployeeResource(plan);
        try {
            Resource resource = grants.resource(plan.resourceId());
            if (resource.platform() != plan.platform() || !Objects.equals(resource.externalId(), plan.resourceKey()))
                throw conflict("RESOURCE_CHANGED");
            var profile = facts.profile(plan.requesterId());
            var membership = facts.membership(plan.requesterId(), resource.id());
            ExecutionRules rules;
            try { rules = source.executionRules(profile, resource); }
            catch (ResponseStatusException e) {
                throw new GrantExecutionException(HttpStatus.SERVICE_UNAVAILABLE, "POLICY_SOURCE_UNAVAILABLE",
                    "최신 권한 규정을 확인할 수 없습니다.", false, null);
            }
            policy.validateApprover(plan.requesterId(), problem.decidedBy(), problem.approverId(), profile,
                resource, membership, executions.approver(problem.decidedBy()).orElse(null), rules);
            if (plan.platform() == Platform.JIRA && !executions.canBrowse(resource.id(), plan.requestedRole().value()))
                throw precondition("JIRA_SCHEME_MISMATCH");
            var current = facts.current(plan.requesterId(), resource);
            var budget = resource.accessScope() == AccessScope.SEAT ?
                executions.lockBudget(profile.departmentId()).orElse(null) : null;
            policy.validateEvidence(resource, problem.evidence(), rules);
            boolean already = policy.validateEligibility(plan, profile, resource, membership, current, budget, rules);
            if (!already) {
                if (problem.simulateJiraFailure() && plan.platform() == Platform.JIRA)
                    throw new GrantExecutionException(HttpStatus.SERVICE_UNAVAILABLE, "MOCK_JIRA_UNAVAILABLE",
                        "모의 Jira의 일시 장애로 실행하지 못했습니다.", true, null);
                if (resource.accessScope() == AccessScope.SEAT) executions.debitBudget(profile.departmentId());
                if (plan.platform() == Platform.GITHUB && resource.accessScope() != AccessScope.SEAT)
                    executions.joinGithubTeam(plan);
                executions.grant(plan);
            }
            Success result = new Success(!already, plan.requestedRole());
            executions.saveReceipt(problemId, key, result);
            return result;
        } catch (EmptyResultDataAccessException e) { throw precondition("FACTS_UNAVAILABLE"); }
    }
}
