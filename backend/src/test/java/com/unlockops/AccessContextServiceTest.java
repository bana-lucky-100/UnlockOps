package com.unlockops;

import com.unlockops.access.dto.AccessContextRequests.Lookup;
import com.unlockops.access.dto.AccessContextResponses.*;
import com.unlockops.access.repository.AccessContextRepository;
import com.unlockops.access.service.*;
import com.unlockops.auth.model.*;
import com.unlockops.grant.model.*;
import com.unlockops.grant.repository.GrantRepository;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class AccessContextServiceTest {
    private final AccessContextRepository facts = mock(AccessContextRepository.class);
    private final GrantRepository grants = mock(GrantRepository.class);
    private final AccessCeilingPolicy policy = mock(AccessCeilingPolicy.class);
    private final AccessContextService service = new AccessContextService(facts, grants, policy);
    private final UUID employeeId = UUID.randomUUID(), resourceId = UUID.randomUUID(), departmentId = UUID.randomUUID();
    private final Profile employee = new Profile(employeeId, "E-001", "직원", departmentId, "개발팀",
        JobGrade.STAFF, JobFamily.DEV, null);

    private Resource target(AccessScope scope) {
        return new Resource(resourceId, Platform.GITHUB, "example", scope, departmentId, null, null, null);
    }

    @BeforeEach void facts() {
        when(facts.profile(employeeId)).thenReturn(employee);
        when(policy.ceiling(eq(employee), any())).thenReturn(new AccessCeilingPolicy.Ceiling("Write", Map.of("matrix", "hash")));
    }

    @Test void aggregatesFactsWithoutTreatingTheCeilingAsAnApproval() {
        var target = target(AccessScope.TF);
        var membership = new Membership(UUID.randomUUID(), false, UUID.randomUUID());
        var current = new Current(null, "github-team-membership", java.util.List.of(), null);
        when(grants.resource(resourceId)).thenReturn(target);
        when(facts.membership(employeeId, resourceId)).thenReturn(membership);
        when(facts.current(employeeId, target)).thenReturn(current);
        var result = service.lookup(new Lookup(employeeId, resourceId, Platform.GITHUB));
        assertSame(employee, result.profile());
        assertFalse(result.membership().member());
        assertNull(result.current().role());
        assertEquals("Write", result.maximumRole());
        assertNull(result.budget());
        verify(facts, never()).budget(any());
    }

    @Test void seatIncludesBudgetAndMissingBudgetRemainsUnknown() {
        when(grants.resource(resourceId)).thenReturn(target(AccessScope.SEAT));
        var budget = new Budget(departmentId, "10.00", "19.00", "USD", OffsetDateTime.now());
        when(facts.budget(departmentId)).thenReturn(budget, null);
        assertSame(budget, service.lookup(new Lookup(employeeId, resourceId, Platform.GITHUB)).budget());
        assertNull(service.lookup(new Lookup(employeeId, resourceId, Platform.GITHUB)).budget());
    }

    @Test void platformMismatchIsRejectedBeforeEmployeeLookup() {
        when(grants.resource(resourceId)).thenReturn(target(AccessScope.GENERAL));
        assertEquals(409, assertThrows(ResponseStatusException.class, () ->
            service.lookup(new Lookup(employeeId, resourceId, Platform.JIRA))).getStatusCode().value());
        verify(facts, never()).profile(any());
        verifyNoInteractions(policy);
    }

    @Test void unknownEmployeeOrResourceIsNotAnEmptyPermission() {
        when(grants.resource(resourceId)).thenThrow(new EmptyResultDataAccessException(1));
        assertEquals(404, assertThrows(ResponseStatusException.class, () ->
            service.lookup(new Lookup(employeeId, resourceId, Platform.GITHUB))).getStatusCode().value());
        doReturn(target(AccessScope.GENERAL)).when(grants).resource(resourceId);
        when(facts.profile(employeeId)).thenThrow(new EmptyResultDataAccessException(1));
        assertEquals(404, assertThrows(ResponseStatusException.class, () ->
            service.lookup(new Lookup(employeeId, resourceId, Platform.GITHUB))).getStatusCode().value());
        verify(facts, never()).current(any(), any());
    }
}
