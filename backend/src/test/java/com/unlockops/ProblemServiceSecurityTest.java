package com.unlockops;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.unlockops.auth.model.*;
import com.unlockops.grant.model.GrantPlan;
import com.unlockops.grant.service.GrantPolicy;
import com.unlockops.messaging.model.JobType;
import com.unlockops.messaging.repository.OutboxRepository;
import com.unlockops.messaging.service.JobService;
import com.unlockops.problem.dto.ProblemRequests.Decision;
import com.unlockops.problem.model.*;
import com.unlockops.problem.repository.*;
import com.unlockops.problem.service.ProblemService;
import java.util.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class ProblemServiceSecurityTest {
    ProblemRepository problems;
    ProblemEventRepository events;
    OutboxRepository outbox;
    GrantPolicy policy;
    ProblemService service;
    UUID id = UUID.randomUUID(), requester = UUID.randomUUID(), approver = UUID.randomUUID();
    ObjectNode row;
    String hash;

    @BeforeEach void setup() {
        problems = mock(ProblemRepository.class);
        events = mock(ProblemEventRepository.class);
        outbox = mock(OutboxRepository.class);
        policy = mock(GrantPolicy.class);
        service = new ProblemService(problems, events, new JobService(outbox), ProblemFixtures.JSON, policy, true);
        row = ProblemFixtures.row(id, requester, approver);
        hash = ProblemFixtures.JSON.planHash(ProblemFixtures.problem(row).plan());
        row.put("plan_hash", hash);
        when(problems.lock(id)).thenAnswer(invocation -> Optional.of(ProblemFixtures.problem(row)));
        when(policy.validatePlan(any(Problem.class), any(GrantPlan.class))).thenReturn(approver);
    }

    AppUser actor(UUID user) { return new AppUser(user, "reviewer", "hash", UserRole.APPROVER); }
    void assertNoWrites() {
        verify(problems, never()).decide(any(), any());
        verifyNoInteractions(events, outbox);
    }

    @Test void anotherApproverCannotExecuteDesignatedPlan() {
        var error = assertThrows(ResponseStatusException.class,
            () -> service.decide(actor(UUID.randomUUID()), id, new Decision(true, hash, "")));
        assertEquals(403, error.getStatusCode().value());
        assertNoWrites();
    }

    @Test void requesterCannotApproveTheirOwnPlanEvenIfAssigned() {
        row.put("approver_id", requester.toString());
        assertThrows(ResponseStatusException.class, () -> service.decide(actor(requester), id, new Decision(true, hash, "")));
        assertNoWrites();
    }

    @Test void changedCardCannotBeApproved() {
        assertThrows(ResponseStatusException.class, () -> service.decide(actor(approver), id, new Decision(true, "0".repeat(64), "")));
        verify(policy, never()).validatePlan(any(), any());
        assertNoWrites();
    }

    @Test void duplicateDecisionCannotEnqueueAnotherExecution() {
        row.put("status", "EXECUTING");
        assertThrows(ResponseStatusException.class, () -> service.decide(actor(approver), id, new Decision(true, hash, "")));
        assertNoWrites();
    }

    @Test void rejectionRequiresAReason() {
        assertThrows(ResponseStatusException.class, () -> service.decide(actor(approver), id, new Decision(false, hash, "")));
        assertNoWrites();
    }

    @Test void validApprovalCreatesOneOutboxExecution() {
        var result = service.decide(actor(approver), id, new Decision(true, hash, "업무상 필요 확인"));
        assertEquals(ProblemStatus.EXECUTING, result.status());
        verify(outbox, times(1)).enqueue(argThat(job -> job.jobType() == JobType.EXECUTE &&
            job.problemId().equals(id) && job.planHash().equals(hash) && job.idempotencyKey().equals(id + ":" + hash)));
    }
}
