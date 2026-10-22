package com.unlockops;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.unlockops.approval.service.*;
import com.unlockops.messaging.service.JobService;
import com.unlockops.problem.model.ProblemStatus;
import com.unlockops.problem.repository.ProblemRepository;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class ApprovedExecutionServiceTest {
    final UUID id = UUID.randomUUID(), requester = UUID.randomUUID(), approver = UUID.randomUUID();
    final ProblemRepository problems = mock(ProblemRepository.class);
    final JobService jobs = mock(JobService.class);
    final ApprovedExecutionService service = new ApprovedExecutionService(problems, new ApprovalCompletionPolicy(), jobs, ProblemFixtures.JSON);
    ObjectNode row;

    @BeforeEach void setup() {
        row = ProblemFixtures.row(id, requester, approver);
        String hash = ProblemFixtures.JSON.planHash(ProblemFixtures.problem(row).plan());
        row.put("plan_hash", hash).put("approved_plan_hash", hash).put("idempotency_key", id + ":" + hash)
            .put("decision_source", "HUMAN").put("decided_by", approver.toString()).put("decided_at", "2026-10-22T00:00:00Z");
        when(problems.lock(id)).thenAnswer(invocation -> Optional.of(ProblemFixtures.problem(row)));
        when(problems.startExecution(id)).thenReturn(true);
    }

    @Test void missingPersistedApprovalNeverStartsExecution() {
        row.remove("decided_at");
        assertEquals(ProblemStatus.WAITING_APPROVAL, service.start(id));
        verify(problems, never()).startExecution(any());
        verifyNoInteractions(jobs);
    }

    @Test void changedApprovedPlanCannotBeDispatched() {
        row.put("approved_plan_hash", "0".repeat(64));
        assertThrows(ResponseStatusException.class, () -> service.start(id));
        verify(problems, never()).startExecution(any());
        verifyNoInteractions(jobs);
    }

    @Test void repeatedAdmissionDoesNotCreateAnotherExecution() {
        row.put("status", "EXECUTING");
        assertEquals(ProblemStatus.EXECUTING, service.start(id));
        verifyNoInteractions(jobs);
    }

    @Test void failedStateTransitionCannotEnqueueExecution() {
        when(problems.startExecution(id)).thenReturn(false);
        assertThrows(ResponseStatusException.class, () -> service.start(id));
        verifyNoInteractions(jobs);
    }
}
