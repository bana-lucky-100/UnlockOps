package com.unlockops;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.unlockops.grant.service.GrantPolicy;
import com.unlockops.messaging.dto.AgentEvent;
import com.unlockops.messaging.repository.InboxRepository;
import com.unlockops.messaging.service.AgentResultService;
import com.unlockops.grant.repository.GrantRepository;
import com.unlockops.problem.model.ProblemStatus;
import com.unlockops.problem.repository.ProblemEventRepository;
import com.unlockops.problem.repository.ProblemRepository;
import java.sql.SQLException;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.dao.CannotAcquireLockException;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class AgentResultRecoveryTest {
    final UUID problemId = UUID.randomUUID(), requester = UUID.randomUUID(), approver = UUID.randomUUID();
    final InboxRepository inbox = mock(InboxRepository.class);
    final ProblemRepository problems = mock(ProblemRepository.class);
    final GrantPolicy policy = mock(GrantPolicy.class);
    final AgentResultService service = new AgentResultService(inbox, problems, mock(ProblemEventRepository.class),
        mock(GrantRepository.class), policy, ProblemFixtures.JSON);
    ObjectNode envelope;

    @BeforeEach void setup() {
        ObjectNode row = ProblemFixtures.row(problemId, requester, approver).put("status", "DIAGNOSING");
        when(inbox.recordIfNew(any())).thenReturn(true);
        when(problems.lock(problemId)).thenReturn(Optional.of(ProblemFixtures.problem(row)));
        when(policy.validatePlan(any(), any())).thenReturn(approver);
        envelope = ProblemFixtures.MAPPER.createObjectNode().put("event_id", UUID.randomUUID().toString())
            .put("problem_id", problemId.toString()).put("job_type", "ANALYZE").put("kind", "ANALYZED");
        ObjectNode result = envelope.putObject("result").put("status", "WAITING_APPROVAL")
            .put("reasonCode", "ELIGIBLE").put("proposal", "승인 검토가 필요합니다.");
        result.set("plan", row.get("plan"));
        result.putArray("evidence").addObject().put("source", "test-policy");
    }

    void apply() { service.apply(ProblemFixtures.JSON.read(envelope, AgentEvent.class), envelope); }

    @Test void databaseFailureDuringPlanValidationEscapesForTransactionRollbackAndRetry() {
        var failure = new CannotAcquireLockException("temporary database contention");
        when(policy.validatePlan(any(), any())).thenThrow(failure);
        assertSame(failure, assertThrows(CannotAcquireLockException.class, this::apply));
        verify(problems, never()).applyAnalysis(any(), any());
    }

    @Test void unexpectedFailureIsNotAcknowledgedAsManualReview() {
        var failure = new IllegalStateException("unexpected defect");
        when(policy.validatePlan(any(), any())).thenThrow(failure);
        assertSame(failure, assertThrows(IllegalStateException.class, this::apply));
        verify(problems, never()).applyAnalysis(any(), any());
    }

    @Test void expectedPolicyRejectionStillBecomesManualReview() {
        when(policy.validatePlan(any(), any())).thenThrow(new ResponseStatusException(HttpStatus.CONFLICT));
        apply();
        verify(problems).applyAnalysis(eq(problemId), argThat(update ->
            update.result().status() == ProblemStatus.MANUAL_REVIEW && update.plan() == null));
    }

    @Test void databaseSyntaxFailureIsNotAcknowledgedAsManualReview() {
        var failure = new BadSqlGrammarException("lookup", "test", new SQLException("syntax", "42601"));
        when(policy.validatePlan(any(), any())).thenThrow(failure);
        assertSame(failure, assertThrows(BadSqlGrammarException.class, this::apply));
        verify(problems, never()).applyAnalysis(any(), any());
    }

    @Test void unexpectedServerErrorIsNotAcknowledgedAsPolicyRejection() {
        var failure = new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE);
        when(policy.validatePlan(any(), any())).thenThrow(failure);
        assertSame(failure, assertThrows(ResponseStatusException.class, this::apply));
        verify(problems, never()).applyAnalysis(any(), any());
    }

    @Test void resourceThatNoLongerExistsStillBecomesManualReview() {
        when(policy.validatePlan(any(), any())).thenThrow(new EmptyResultDataAccessException(1));
        apply();
        verify(problems).applyAnalysis(eq(problemId), argThat(update ->
            update.result().status() == ProblemStatus.MANUAL_REVIEW && update.plan() == null));
    }

    @Test void malformedPlanStillBecomesManualReview() {
        ((ObjectNode) envelope.path("result").path("plan")).put("unexpected", true);
        apply();
        verify(problems).applyAnalysis(eq(problemId), argThat(update ->
            update.result().status() == ProblemStatus.MANUAL_REVIEW && update.plan() == null));
    }

    @Test void missingEvidencePreservesValidatedApproverAndClearsExecutionPlan() {
        ((ObjectNode) envelope.path("result")).putArray("evidence");
        apply();
        verify(problems).applyAnalysis(eq(problemId), argThat(update ->
            update.result().status() == ProblemStatus.MANUAL_REVIEW && approver.equals(update.approverId())
                && update.plan() == null && update.planHash() == null));
    }
}
