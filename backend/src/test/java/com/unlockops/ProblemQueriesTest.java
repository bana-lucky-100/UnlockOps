package com.unlockops;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.unlockops.approval.repository.ApprovalRepository;
import com.unlockops.approval.service.ApprovalService;
import com.unlockops.auth.model.*;
import com.unlockops.grant.service.GrantPolicy;
import com.unlockops.messaging.service.JobService;
import com.unlockops.problem.repository.*;
import com.unlockops.problem.service.ProblemService;
import java.util.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class ProblemQueriesTest {
    ProblemRepository problems;
    ProblemEventRepository events;
    ApprovalRepository approvals;
    GrantPolicy policy;
    ProblemService service;
    UUID requester = UUID.randomUUID(), approver = UUID.randomUUID(), id = UUID.randomUUID();
    ObjectNode row;

    @BeforeEach void setup() {
        problems = mock(ProblemRepository.class);
        events = mock(ProblemEventRepository.class);
        approvals = mock(ApprovalRepository.class);
        policy = mock(GrantPolicy.class);
        service = new ProblemService(problems, events, mock(JobService.class), policy, true);
        row = ProblemFixtures.row(id, requester, approver);
        when(problems.find(id)).thenAnswer(invocation -> Optional.of(ProblemFixtures.problem(row)));
        when(events.findByProblem(id)).thenReturn(List.of());
    }

    AppUser actor(UUID user, UserRole role) { return new AppUser(user, "actor", "hash", role); }
    JsonNode detail(AppUser user) { return ProblemFixtures.MAPPER.valueToTree(service.detail(user, id)); }

    @Test void requesterReadsOwnRequestWithoutApproverPrivileges() {
        var result = detail(actor(requester, UserRole.REQUESTER));
        assertEquals(id.toString(), result.path("id").asText());
        assertFalse(result.has("evidence"));
        assertFalse(result.has("plan_hash"));
        assertTrue(result.path("events").isEmpty());
        verify(policy, never()).requireApprover(any());
    }

    @Test void anotherApproverCannotReadAnUnassignedRequest() {
        var error = assertThrows(ResponseStatusException.class, () -> detail(actor(UUID.randomUUID(), UserRole.APPROVER)));
        assertEquals(403, error.getStatusCode().value());
    }

    @Test void assignedApproverRetainsEvidenceAndPlanHash() {
        var result = detail(actor(approver, UserRole.APPROVER));
        assertEquals("private-source", result.path("evidence").get(0).asText());
        assertEquals("private-hash", result.path("plan_hash").asText());
    }

    @Test void mineAlwaysFiltersUsingTheAuthenticatedUser() {
        when(problems.findMine(requester)).thenReturn(List.of(ProblemFixtures.problem(row)));
        var result = service.list(actor(requester, UserRole.REQUESTER), true);
        assertEquals(1, result.size());
        assertFalse(ProblemFixtures.MAPPER.valueToTree(result.getFirst()).has("plan_hash"));
        verify(problems).findMine(requester);
        verify(policy, never()).requireApprover(any());
    }

    @Test void requesterCannotReadOthersEvenWhenTheyKnowTheId() {
        var user = actor(UUID.randomUUID(), UserRole.REQUESTER);
        doThrow(new ResponseStatusException(HttpStatus.FORBIDDEN)).when(policy).requireApprover(user);
        var error = assertThrows(ResponseStatusException.class, () -> detail(user));
        assertEquals(403, error.getStatusCode().value());
        verifyNoInteractions(events);
    }

    @Test void summaryRequiresApproverBeforeReadingDepartmentData() {
        var user = actor(requester, UserRole.REQUESTER);
        doThrow(new ResponseStatusException(HttpStatus.FORBIDDEN)).when(policy).requireApprover(user);
        assertThrows(ResponseStatusException.class, () -> new ApprovalService(approvals, policy).summary(user));
        verifyNoInteractions(approvals);
    }
}
