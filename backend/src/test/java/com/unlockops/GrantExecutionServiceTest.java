package com.unlockops;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.unlockops.access.dto.AccessContextResponses.*;
import com.unlockops.access.repository.AccessContextRepository;
import com.unlockops.access.service.AccessCeilingPolicy;
import com.unlockops.access.service.AccessCeilingPolicy.ExecutionRules;
import com.unlockops.auth.model.*;
import com.unlockops.grant.dto.GrantExecutionResponses.Success;
import com.unlockops.grant.model.*;
import com.unlockops.grant.repository.*;
import com.unlockops.grant.service.*;
import com.unlockops.problem.model.Problem;
import com.unlockops.problem.repository.ProblemRepository;
import java.time.OffsetDateTime;
import java.util.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class GrantExecutionServiceTest {
    final ProblemRepository problems = mock(ProblemRepository.class);
    final GrantExecutionRepository executions = mock(GrantExecutionRepository.class);
    final GrantRepository grants = mock(GrantRepository.class);
    final AccessContextRepository facts = mock(AccessContextRepository.class);
    final AccessCeilingPolicy source = mock(AccessCeilingPolicy.class);
    final GrantExecutionService service = new GrantExecutionService(problems, executions, grants, facts, source,
        new GrantExecutionPolicy(), ProblemFixtures.JSON);
    final UUID id = UUID.randomUUID(), requester = UUID.randomUUID(), approver = UUID.randomUUID(), resourceId = UUID.randomUUID();
    final UUID department = UUID.randomUUID();
    final String key = "execution-key";
    ObjectNode row;
    Resource resource;
    Profile profile;

    @BeforeEach void prepare() {
        row = ProblemFixtures.row(id, requester, approver);
        row.put("status", "EXECUTING").put("resource_id", resourceId.toString()).put("requested_role", "Write")
            .put("decision_source", "HUMAN").put("decided_by", approver.toString())
            .put("decided_at", OffsetDateTime.now().toString()).put("idempotency_key", key);
        ((ObjectNode) row.get("plan")).put("resource_id", resourceId.toString());
        row.set("evidence", ProblemFixtures.MAPPER.createArrayNode());
        for (String doc : List.of("A-ACCESS-03", "A-ACCESS-04", "A-ACCESS-07", "POL-03", "POL-04", "POL-02", "POL-06"))
            row.withArray("evidence").addObject().put("doc_id", doc).put("source", doc.startsWith("A-") ?
                "company-a-access-matrix.md" : "policy_corpus.md").put("source_hash", "hash")
                .put("chunk_id", doc + ":1").put("text", "근거 원문");
        configure(Platform.GITHUB, AccessScope.TF, SaasRole.WRITE);
        when(executions.receipt(id, key)).thenReturn(Optional.empty());
        when(executions.approver(approver)).thenReturn(Optional.of(
            new GrantExecutionRepository.Approver(approver, UserRole.APPROVER, JobGrade.MANAGER)));
    }

    void configure(Platform platform, AccessScope scope, SaasRole role) {
        row.put("platform", platform.name()).put("requested_role", role.value());
        ((ObjectNode) row.get("plan")).put("platform", platform.name()).put("requested_role", role.value());
        resource = new Resource(resourceId, platform, "payment-core", scope, department,
            scope == AccessScope.TF ? UUID.randomUUID() : null, SecurityGrade.INTERNAL, null);
        profile = new Profile(requester, "E-001", "직원", department, "개발팀", JobGrade.STAFF, JobFamily.DEV, approver);
        when(grants.resource(resourceId)).thenReturn(resource);
        when(facts.profile(requester)).thenReturn(profile);
        when(facts.membership(requester, resourceId)).thenReturn(new Membership(resource.tfId(), true, approver));
        when(facts.current(requester, resource)).thenReturn(new Current(null, "mock", null, false));
        when(source.executionRules(profile, resource)).thenReturn(new ExecutionRules(role.value(),
            Map.of("company-a-access-matrix.md", "hash", "policy_corpus.md", "hash"), UserRole.APPROVER, JobGrade.MANAGER));
        persist();
    }

    void persist() {
        String hash = ProblemFixtures.JSON.planHash(ProblemFixtures.JSON.plan(row.get("plan")));
        row.put("plan_hash", hash).put("approved_plan_hash", hash);
        when(problems.lock(id)).thenReturn(Optional.of(ProblemFixtures.problem(row)));
    }

    @Test void githubGrantSavesTeamPermissionAndReceiptInOrder() {
        Success result = service.execute(id, key);
        assertEquals(new Success(true, SaasRole.WRITE), result);
        var order = inOrder(problems, executions);
        order.verify(problems).lock(id);
        order.verify(executions).receipt(id, key);
        order.verify(executions).lockEmployeeResource(any());
        order.verify(executions).joinGithubTeam(any());
        order.verify(executions).grant(any());
        order.verify(executions).saveReceipt(id, key, result);
        verify(executions, never()).debitBudget(any());
    }

    @Test void seatLocksAndDebitsBudgetBeforeSavingTheReceipt() {
        configure(Platform.GITHUB, AccessScope.SEAT, SaasRole.SEAT);
        when(executions.lockBudget(department)).thenReturn(Optional.of(new Budget(department, "19.00", "19.00", "USD", null)));
        var result = service.execute(id, key);
        var order = inOrder(executions);
        order.verify(executions).lockBudget(department);
        order.verify(executions).debitBudget(department);
        order.verify(executions).grant(any());
        order.verify(executions).saveReceipt(id, key, result);
        verify(executions, never()).joinGithubTeam(any());
    }

    @Test void savedReceiptIsReplayedAfterTheProblemHasCompleted() {
        row.put("status", "DONE"); persist();
        var previous = new Success(true, SaasRole.WRITE);
        when(executions.receipt(id, key)).thenReturn(Optional.of(previous));
        assertSame(previous, service.execute(id, key));
        verify(executions, never()).lockEmployeeResource(any());
        verify(executions, never()).saveReceipt(any(), any(), any());
    }

    @Test void wrongKeyCannotReadReceiptOrExecute() {
        assertEquals("INVALID_EXECUTION_KEY", assertThrows(GrantExecutionException.class, () -> service.execute(id, "wrong")).code());
        verifyNoInteractions(executions);
    }

    @Test void missingApprovalAndAlteredPlanAreBlocked() {
        row.put("decision_source", "AGENT"); persist();
        assertEquals("APPROVAL_REQUIRED", assertThrows(GrantExecutionException.class, () -> service.execute(id, key)).code());
        row.put("decision_source", "HUMAN"); persist();
        row.put("approved_plan_hash", "tampered");
        when(problems.lock(id)).thenReturn(Optional.of(ProblemFixtures.problem(row)));
        assertEquals("PLAN_CHANGED", assertThrows(GrantExecutionException.class, () -> service.execute(id, key)).code());
        verify(executions, never()).grant(any());
    }

    @Test void changedApproverAndStaleEvidenceBlockAllWrites() {
        when(executions.approver(approver)).thenReturn(Optional.empty());
        assertEquals("APPROVER_CHANGED", assertThrows(GrantExecutionException.class, () -> service.execute(id, key)).code());
        when(executions.approver(approver)).thenReturn(Optional.of(
            new GrantExecutionRepository.Approver(approver, UserRole.APPROVER, JobGrade.MANAGER)));
        ((ObjectNode) row.withArray("evidence").get(0)).put("source_hash", "old"); persist();
        assertEquals("POLICY_EVIDENCE_MISMATCH", assertThrows(GrantExecutionException.class, () -> service.execute(id, key)).reason());
        verify(executions, never()).grant(any());
        verify(executions, never()).saveReceipt(any(), any(), any());
    }

    @Test void alreadyHeldPermissionCreatesOnlyAnUnchangedReceipt() {
        when(facts.current(requester, resource)).thenReturn(new Current("Write", "mock", null, null));
        assertFalse(service.execute(id, key).changed());
        verify(executions, never()).grant(any());
        verify(executions).saveReceipt(id, key, new Success(false, SaasRole.WRITE));
    }

    @Test void duplicateSeatAndInsufficientBudgetNeverDebit() {
        configure(Platform.GITHUB, AccessScope.SEAT, SaasRole.SEAT);
        when(executions.lockBudget(department)).thenReturn(Optional.of(new Budget(department, "10.00", "19.00", "USD", null)));
        assertEquals("BUDGET_INSUFFICIENT", assertThrows(GrantExecutionException.class, () -> service.execute(id, key)).reason());
        when(facts.current(requester, resource)).thenReturn(new Current("Seat", "mock", null, null));
        assertEquals("DUPLICATE_SEAT", assertThrows(GrantExecutionException.class, () -> service.execute(id, key)).reason());
        verify(executions, never()).debitBudget(any());
        verify(executions, never()).saveReceipt(any(), any(), any());
    }

    @Test void jiraFailureIsRetryableWithoutPermissionOrReceipt() {
        configure(Platform.JIRA, AccessScope.TF, SaasRole.DEVELOPER);
        row.put("simulate_jira_failure", true); persist();
        when(executions.canBrowse(resourceId, "Developer")).thenReturn(true);
        var failure = assertThrows(GrantExecutionException.class, () -> service.execute(id, key));
        assertEquals("MOCK_JIRA_UNAVAILABLE", failure.code());
        assertTrue(failure.retryable());
        verify(executions, never()).grant(any());
        verify(executions, never()).saveReceipt(any(), any(), any());
    }

    @Test void receiptStorageFailurePropagatesForTransactionRollback() {
        doThrow(new org.springframework.dao.DataAccessResourceFailureException("storage failure"))
            .when(executions).saveReceipt(any(), any(), any());
        assertThrows(org.springframework.dao.DataAccessException.class, () -> service.execute(id, key));
    }
}
