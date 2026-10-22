package com.unlockops.problem.service;

import com.unlockops.auth.model.AppUser;
import com.unlockops.grant.model.Platform;
import com.unlockops.grant.service.GrantPolicy;
import com.unlockops.messaging.model.*;
import com.unlockops.messaging.service.JobService;
import com.unlockops.problem.dto.ProblemRequests.*;
import com.unlockops.problem.dto.ProblemResponses.*;
import com.unlockops.problem.model.*;
import com.unlockops.problem.repository.*;
import java.util.List;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ProblemService {
    private final ProblemRepository problems;
    private final ProblemEventRepository events;
    private final JobService jobs;
    private final GrantPolicy policy;
    private final boolean demo;

    public ProblemService(ProblemRepository problems, ProblemEventRepository events, JobService jobs,
                          GrantPolicy policy, @Value("${app.demo-enabled}") boolean demo) {
        this.problems = problems;
        this.events = events;
        this.jobs = jobs;
        this.policy = policy;
        this.demo = demo;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public Status create(AppUser user, Create request, String idempotencyKey) {
        ClientRequestKey key = idempotencyKey == null ? null : new ClientRequestKey(idempotencyKey);
        if (key != null) {
            var previous = problems.findByClientRequestKey(user.id(), key);
            if (previous.isPresent()) return replay(previous.get(), request);
        }
        if (request.simulateJiraFailure() && (!demo || request.platform() != Platform.JIRA))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Jira 데모에서만 실패 시연을 선택할 수 있습니다.");
        UUID id = UUID.randomUUID();
        boolean inserted = problems.insertIfNew(id, user.id(), policy.reviewer(user.id()), request.platform(),
            request.contents().strip(), request.simulateJiraFailure(), key);
        if (!inserted) {
            // A concurrent insert won. A separate SELECT sees its commit under READ_COMMITTED.
            Problem previous = problems.findByClientRequestKey(user.id(), key).orElseThrow(() ->
                new IllegalStateException("Conflicting submission is no longer available"));
            return replay(previous, request);
        }
        jobs.enqueue(required(id), JobType.ANALYZE, null);
        return new Status(id, ProblemStatus.RECEIVED);
    }

    private Status replay(Problem previous, Create request) {
        GrantPolicy.check(previous.platform() == request.platform()
            && previous.contents().equals(request.contents().strip())
            && previous.simulateJiraFailure() == request.simulateJiraFailure(),
            "같은 접수 키로 다른 내용을 제출할 수 없습니다.");
        // Replay the acceptance, not the current workflow status; never enqueue or reset state.
        return new Status(previous.id(), ProblemStatus.RECEIVED);
    }

    public List<? extends View> list(AppUser user, boolean mine) {
        if (mine) return problems.findMine(user.id()).stream().map(problem -> ProblemViews.requester(problem, null)).toList();
        policy.requireApprover(user);
        return problems.findAssigned(user.id(), policy.operations(user)).stream().map(Assigned::from).toList();
    }

    public View detail(AppUser user, UUID id) {
        Problem problem = required(id);
        boolean own = user.id().equals(problem.requesterId());
        if (!own) {
            policy.requireApprover(user);
            if (!policy.operations(user) && !user.id().equals(problem.approverId()))
                throw new ResponseStatusException(HttpStatus.FORBIDDEN, "담당 요청만 조회할 수 있습니다.");
        }
        var history = events.findByProblem(id);
        return own ? ProblemViews.requester(problem, ProblemViews.publicEvents(history)) : new Detail(problem, history);
    }

    private Problem required(UUID id) {
        return problems.find(id).orElseThrow(() ->
            new ResponseStatusException(HttpStatus.NOT_FOUND, "요청을 찾을 수 없습니다."));
    }

}
