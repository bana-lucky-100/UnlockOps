package com.unlockops.messaging.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.common.json.Jsons;
import com.unlockops.grant.model.GrantPlan;
import com.unlockops.grant.repository.GrantRepository;
import com.unlockops.grant.service.GrantPolicy;
import com.unlockops.messaging.dto.*;
import com.unlockops.messaging.model.*;
import com.unlockops.messaging.repository.InboxRepository;
import com.unlockops.problem.model.*;
import com.unlockops.problem.repository.*;
import com.unlockops.problem.repository.ProblemRepository.*;
import java.util.Set;
import java.util.UUID;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import static com.unlockops.messaging.service.InvalidAgentMessageException.Reason.*;

@Service
public class AgentResultService {
    private static final Set<ProblemStatus> ANALYSIS_RESULTS = Set.of(ProblemStatus.WAITING_APPROVAL,
        ProblemStatus.REJECTED, ProblemStatus.MANUAL_REVIEW, ProblemStatus.DONE);
    private static final Set<ProblemStatus> EXECUTION_RESULTS = Set.of(ProblemStatus.DONE, ProblemStatus.FAILED);
    private final InboxRepository inbox;
    private final ProblemRepository problems;
    private final ProblemEventRepository events;
    private final GrantRepository grants;
    private final GrantPolicy policy;
    private final Jsons json;

    public AgentResultService(InboxRepository inbox, ProblemRepository problems, ProblemEventRepository events,
                              GrantRepository grants, GrantPolicy policy, Jsons json) {
        this.inbox = inbox;
        this.problems = problems;
        this.events = events;
        this.grants = grants;
        this.policy = policy;
        this.json = json;
    }

    @Transactional
    public void apply(AgentEvent event, JsonNode rawEnvelope) {
        if (!inbox.recordIfNew(event.eventId())) return;
        var found = problems.lock(event.problemId());
        if (found.isEmpty()) return;
        Problem problem = found.get();
        events.append(event.eventId(), problem.id(), event.kind(), rawEnvelope);
        boolean execution = event.jobType() == JobType.EXECUTE;
        boolean active = execution ? problem.status() == ProblemStatus.EXECUTING :
            problem.status() == ProblemStatus.RECEIVED || problem.status() == ProblemStatus.DIAGNOSING;
        if (!active) return; // Audit late events without overwriting approval/terminal state.
        if (event.kind() == EventKind.PROGRESS) {
            if (!execution && problem.status() == ProblemStatus.RECEIVED) problems.markDiagnosing(problem.id());
            return;
        }
        if (event.kind() == EventKind.FAILED) {
            problems.markFailed(problem.id(), event.errorCode() == null ? ServerReason.WORKER_ERROR.name() : event.errorCode(),
                "처리가 완료되지 않았습니다. 담당자가 실행 기록을 확인해야 합니다.");
            return;
        }
        if (event.kind() != EventKind.ANALYZED && event.kind() != EventKind.EXECUTED)
            throw new InvalidAgentMessageException(UNKNOWN_RESULT_KIND);
        AgentResult result;
        try { result = AgentResult.parse(event.result(), json); }
        catch (IllegalArgumentException e) { throw new InvalidAgentMessageException(INVALID_RESULT, e); }
        if (!(execution ? EXECUTION_RESULTS : ANALYSIS_RESULTS).contains(result.status()))
            throw new InvalidAgentMessageException(ILLEGAL_RESULT_STATE);
        if (result.status() == ProblemStatus.DONE) {
            if (execution && result.resultType() != ResultType.ACCESS_VERIFIED)
                throw new InvalidAgentMessageException(UNVERIFIED_COMPLETION);
            if (execution && !grants.hasReceipt(problem.id(), problem.idempotencyKey()))
                throw new InvalidAgentMessageException(MISSING_RECEIPT);
        }
        if (execution) {
            // Execution never replaces the approved plan, designated approver, or human decision.
            problems.applyExecution(problem.id(), executionUpdate(result));
        } else {
            problems.applyAnalysis(problem.id(), analysisUpdate(problem, result));
        }
    }

    private ExecutionUpdate executionUpdate(AgentResult result) {
        return new ExecutionUpdate(result.status(), result.diagnosis(), result.proposal(), result.reasonCode(),
            result.verificationOk(), result.agentMode(), result.resultType());
    }

    private AnalysisUpdate analysisUpdate(Problem problem, AgentResult result) {
        UUID approver = problem.approverId();
        if (result.status() != ProblemStatus.WAITING_APPROVAL)
            return new AnalysisUpdate(executionUpdate(result), approver, null, null, result.evidence(), null, null);
        try {
            GrantPlan plan = json.plan(result.plan());
            approver = policy.validatePlan(problem, plan);
            GrantPolicy.check(result.evidence() != null && result.evidence().isArray() && !result.evidence().isEmpty(), "근거가 없는 계획입니다.");
            return new AnalysisUpdate(executionUpdate(result), approver, plan.resourceId(), plan.requestedRole(),
                result.evidence(), plan, json.planHash(plan));
        } catch (IllegalArgumentException | ResponseStatusException | EmptyResultDataAccessException e) {
            if (e instanceof ResponseStatusException response && !response.getStatusCode().is4xxClientError()) throw response;
            // DB failures/defects must escape for rollback. Invalid plans retain an already validated approver.
            ExecutionUpdate fallback = new ExecutionUpdate(ProblemStatus.MANUAL_REVIEW, result.diagnosis(),
                "실행 계획이 서버 검증을 통과하지 못했습니다. 담당자 검토가 필요합니다.",
                ServerReason.SERVER_PLAN_VALIDATION.name(), result.verificationOk(), result.agentMode(), null);
            return new AnalysisUpdate(fallback, approver, null, null, result.evidence(), null, null);
        }
    }
}
