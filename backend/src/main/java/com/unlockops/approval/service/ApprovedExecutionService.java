package com.unlockops.approval.service;

import com.unlockops.common.json.Jsons;
import com.unlockops.grant.service.GrantPolicy;
import com.unlockops.messaging.model.JobType;
import com.unlockops.messaging.service.JobService;
import com.unlockops.problem.model.ProblemStatus;
import com.unlockops.problem.repository.ProblemRepository;
import java.util.Objects;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/** Re-reads persisted approval, then atomically changes state and enqueues execution. */
@Service
public class ApprovedExecutionService {
    private final ProblemRepository problems;
    private final ApprovalCompletionPolicy approvals;
    private final JobService jobs;
    private final Jsons json;

    public ApprovedExecutionService(ProblemRepository problems, ApprovalCompletionPolicy approvals,
                                    JobService jobs, Jsons json) {
        this.problems = problems;
        this.approvals = approvals;
        this.jobs = jobs;
        this.json = json;
    }

    // Must join the decision transaction: no approval without its outbox, and no outbox without approval.
    @Transactional(propagation = Propagation.MANDATORY)
    public ProblemStatus start(UUID id) {
        var problem = problems.lock(id).orElseThrow(() ->
            new ResponseStatusException(HttpStatus.NOT_FOUND, "요청을 찾을 수 없습니다."));
        if (problem.status() == ProblemStatus.EXECUTING) return ProblemStatus.EXECUTING;
        GrantPolicy.check(problem.status() == ProblemStatus.WAITING_APPROVAL, "승인 대기 상태가 아닙니다.");
        if (!approvals.isComplete(problem)) return ProblemStatus.WAITING_APPROVAL;
        GrantPolicy.check(problem.decidedBy().equals(problem.approverId())
            && !problem.decidedBy().equals(problem.requesterId()), "유효한 지정 승인 기록이 필요합니다.");
        GrantPolicy.check(problem.plan() != null
            && Objects.equals(json.planHash(problem.plan()), problem.planHash())
            && Objects.equals(problem.planHash(), problem.approvedPlanHash()), "승인된 실행 계획이 변경되었습니다.");
        GrantPolicy.check(Objects.equals(problem.idempotencyKey(), id + ":" + problem.approvedPlanHash()),
            "승인된 실행 키가 일치하지 않습니다.");
        GrantPolicy.check(problems.startExecution(id), "이미 처리되었거나 승인 대기 상태가 아닙니다.");
        jobs.enqueue(problem, JobType.EXECUTE, problem.idempotencyKey());
        return ProblemStatus.EXECUTING;
    }
}
