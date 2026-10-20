package com.unlockops.problem.service;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import com.unlockops.auth.model.AppUser;
import com.unlockops.common.json.Jsons;
import com.unlockops.grant.model.Platform;
import com.unlockops.grant.service.GrantPolicy;
import com.unlockops.messaging.model.*;
import com.unlockops.messaging.service.JobService;
import com.unlockops.problem.dto.ProblemRequests.*;
import com.unlockops.problem.dto.ProblemResponses.*;
import com.unlockops.problem.model.*;
import com.unlockops.problem.repository.*;
import com.unlockops.problem.repository.ProblemRepository.DecisionUpdate;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ProblemService {
    private final ProblemRepository problems;
    private final ProblemEventRepository events;
    private final JobService jobs;
    private final Jsons json;
    private final GrantPolicy policy;
    private final boolean demo;

    public ProblemService(ProblemRepository problems, ProblemEventRepository events, JobService jobs,
                          Jsons json, GrantPolicy policy, @Value("${app.demo-enabled}") boolean demo) {
        this.problems = problems;
        this.events = events;
        this.jobs = jobs;
        this.json = json;
        this.policy = policy;
        this.demo = demo;
    }

    @Transactional
    public Status create(AppUser user, Create request) {
        if (request.simulateJiraFailure() && (!demo || request.platform() != Platform.JIRA))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Jira 데모에서만 실패 시연을 선택할 수 있습니다.");
        UUID id = UUID.randomUUID();
        problems.insert(id, user.id(), policy.reviewer(user.id()), request.platform(), request.contents().strip(), request.simulateJiraFailure());
        jobs.enqueue(required(id, false), JobType.ANALYZE, null);
        return new Status(id, ProblemStatus.RECEIVED);
    }

    public List<? extends View> list(AppUser user, boolean mine) {
        if (mine) return problems.findMine(user.id()).stream().map(problem -> ProblemViews.requester(problem, null)).toList();
        policy.requireApprover(user);
        return problems.findAssigned(user.id(), policy.operations(user)).stream().map(Assigned::from).toList();
    }

    public View detail(AppUser user, UUID id) {
        Problem problem = required(id, false);
        boolean own = user.id().equals(problem.requesterId());
        if (!own) {
            policy.requireApprover(user);
            if (!policy.operations(user) && !user.id().equals(problem.approverId()))
                throw new ResponseStatusException(HttpStatus.FORBIDDEN, "담당 요청만 조회할 수 있습니다.");
        }
        var history = events.findByProblem(id);
        return own ? ProblemViews.requester(problem, ProblemViews.publicEvents(history)) : new Detail(problem, history);
    }

    @Transactional
    public Status decide(AppUser user, UUID id, Decision request) {
        policy.requireApprover(user);
        Problem problem = required(id, true);
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
        ProblemStatus status = request.approved() ? ProblemStatus.EXECUTING : ProblemStatus.REJECTED;
        String key = request.approved() ? id + ":" + request.expectedPlanHash() : null;
        problems.decide(id, new DecisionUpdate(status, reason, user.id(), request.approved() ? request.expectedPlanHash() : null,
            key, request.approved() ? ServerReason.HUMAN_APPROVED : ServerReason.HUMAN_REJECTED,
            request.approved() ? "승인이 기록되어 권한 부여를 진행하고 있습니다." : "담당자가 반려했습니다. " + reason));
        events.append(UUID.randomUUID(), id, EventKind.HUMAN_DECISION, new HumanDecision(request.approved(), user.id(), reason));
        if (request.approved()) jobs.enqueue(problem, JobType.EXECUTE, key);
        return new Status(id, status);
    }

    private Problem required(UUID id, boolean lock) {
        return (lock ? problems.lock(id) : problems.find(id)).orElseThrow(() ->
            new ResponseStatusException(HttpStatus.NOT_FOUND, "요청을 찾을 수 없습니다."));
    }

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    private record HumanDecision(boolean approved, UUID actorId, String reason) {}
}
