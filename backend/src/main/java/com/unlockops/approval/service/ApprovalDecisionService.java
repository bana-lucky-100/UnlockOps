package com.unlockops.approval.service;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import com.unlockops.auth.model.AppUser;
import com.unlockops.common.json.Jsons;
import com.unlockops.grant.service.GrantPolicy;
import com.unlockops.messaging.model.EventKind;
import com.unlockops.problem.dto.ProblemRequests.Decision;
import com.unlockops.problem.dto.ProblemResponses.Status;
import com.unlockops.problem.model.*;
import com.unlockops.problem.repository.*;
import com.unlockops.problem.repository.ProblemRepository.DecisionUpdate;
import java.util.Objects;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/** Owns human decisions. Execution admission is a separate transaction participant. */
@Service
public class ApprovalDecisionService {
    private final ProblemRepository problems;
    private final ProblemEventRepository events;
    private final Jsons json;
    private final GrantPolicy policy;
    private final ApprovedExecutionService execution;

    public ApprovalDecisionService(ProblemRepository problems, ProblemEventRepository events,
                                   Jsons json, GrantPolicy policy, ApprovedExecutionService execution) {
        this.problems = problems;
        this.events = events;
        this.json = json;
        this.policy = policy;
        this.execution = execution;
    }

    @Transactional
    public Status decide(AppUser user, UUID id, Decision request) {
        policy.requireApprover(user);
        Problem problem = problems.lock(id).orElseThrow(() ->
            new ResponseStatusException(HttpStatus.NOT_FOUND, "요청을 찾을 수 없습니다."));
        GrantPolicy.check(problem.status() == ProblemStatus.WAITING_APPROVAL, "이미 처리되었거나 승인 대기 상태가 아닙니다.");
        if (!user.id().equals(problem.approverId()) || user.id().equals(problem.requesterId()))
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "지정 승인자만 처리할 수 있고 본인 승인은 불가합니다.");
        GrantPolicy.check(Objects.equals(request.expectedPlanHash(), problem.planHash()), "승인 카드가 변경되었습니다. 새로고침해 주세요.");
        String reason = request.normalizedReason();
        if (!request.approved() && reason.isBlank())
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "반려 사유를 입력해 주세요.");
        if (request.approved()) {
            GrantPolicy.check(user.id().equals(policy.validatePlan(problem, problem.plan())), "승인자가 변경되었습니다.");
            GrantPolicy.check(json.planHash(problem.plan()).equals(request.expectedPlanHash()), "실행 계획이 변경되었습니다.");
        }
        ProblemStatus status = request.approved() ? ProblemStatus.WAITING_APPROVAL : ProblemStatus.REJECTED;
        String key = request.approved() ? id + ":" + request.expectedPlanHash() : null;
        problems.decide(id, new DecisionUpdate(status, reason, user.id(), request.approved() ? request.expectedPlanHash() : null,
            key, request.approved() ? ServerReason.HUMAN_APPROVED : ServerReason.HUMAN_REJECTED,
            request.approved() ? "승인이 기록되었습니다." : "담당자가 반려했습니다. " + reason));
        events.append(UUID.randomUUID(), id, EventKind.HUMAN_DECISION, new HumanDecision(request.approved(), user.id(), reason));
        if (request.approved()) status = execution.start(id);
        return new Status(id, status);
    }

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    private record HumanDecision(boolean approved, UUID actorId, String reason) {}
}
