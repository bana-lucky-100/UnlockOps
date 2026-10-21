package com.unlockops;

import com.unlockops.access.dto.AccessContextResponses.Current;
import com.unlockops.access.dto.AccessVerificationRequests.Verify;
import com.unlockops.access.repository.AccessContextRepository;
import com.unlockops.access.service.AccessVerificationService;
import com.unlockops.grant.model.*;
import com.unlockops.grant.repository.GrantRepository;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class AccessVerificationServiceTest {
    private final AccessContextRepository facts = mock(AccessContextRepository.class);
    private final GrantRepository grants = mock(GrantRepository.class);
    private final AccessVerificationService service = new AccessVerificationService(facts, grants);
    private final UUID employee = UUID.randomUUID(), id = UUID.randomUUID();

    private Resource target(Platform platform, AccessScope scope) {
        return new Resource(id, platform, "example", scope, null, null, null, null);
    }

    @ParameterizedTest
    @CsvSource({
        "GITHUB,GENERAL,Write,Read,true", "GITHUB,GENERAL,Read,Write,false",
        "GITHUB,GENERAL,Write,Write,true", "GITHUB,GENERAL,,Write,false",
        "GITHUB,GENERAL,Developer,Read,false", "GITHUB,GENERAL,Seat,Read,false",
        "GITHUB,SEAT,Seat,Seat,true", "GITHUB,SEAT,Write,Seat,false",
        "GITHUB,GENERAL,Write,Seat,false", "JIRA,GENERAL,Developer,Viewer,true",
        "JIRA,GENERAL,Viewer,Developer,false", "JIRA,GENERAL,Write,Viewer,false",
        "SLACK,GENERAL,Member,Member,true", "SLACK,GENERAL,,Member,false",
        "NOTION,DEPARTMENT,Can edit,Can view,true", "NOTION,DEPARTMENT,Can view,Can edit,false",
        "NOTION,DEPARTMENT,Can edit,Can edit,true", "NOTION,GENERAL,Developer,Can view,false"
    })
    void comparesOnlyRolesInTheSameResourceFamily(Platform platform, AccessScope scope, String held, String requested, boolean expected) {
        var resource = target(platform, scope);
        when(grants.resource(id)).thenReturn(resource);
        when(facts.current(employee, resource)).thenReturn(new Current(held, "mock", null, true));
        var result = service.verify(new Verify(employee, id, platform, requested));
        assertTrue(result.ok());
        assertEquals(expected, result.verified());
        assertEquals(held, result.current().role());
    }

    @Test void jiraMustHaveBrowsePermissionEvenWithTheRequestedRole() {
        var resource = target(Platform.JIRA, AccessScope.GENERAL);
        when(grants.resource(id)).thenReturn(resource);
        when(facts.current(employee, resource)).thenReturn(new Current("Developer", "jira-role-and-scheme", null, false),
            new Current("Developer", "jira-role-and-scheme", null, null));
        assertFalse(service.verify(new Verify(employee, id, Platform.JIRA, "Developer")).verified());
        assertFalse(service.verify(new Verify(employee, id, Platform.JIRA, "Developer")).verified());
    }

    @Test void eachCallUsesNewPermissionFactsIncludingRevocation() {
        var resource = target(Platform.GITHUB, AccessScope.GENERAL);
        when(grants.resource(id)).thenReturn(resource);
        when(facts.current(employee, resource)).thenReturn(new Current(null, "github-team-membership", List.of(), null),
            new Current("Write", "github-team-membership", List.of("write-team"), null),
            new Current(null, "github-team-membership", List.of(), null));
        var request = new Verify(employee, id, Platform.GITHUB, "Write");
        assertFalse(service.verify(request).verified());
        assertTrue(service.verify(request).verified());
        assertFalse(service.verify(request).verified());
        verify(facts, times(3)).current(employee, resource);
    }

    @Test void missingEmployeeOrResourceIs404RatherThanUnverified() {
        when(grants.resource(id)).thenThrow(new EmptyResultDataAccessException(1));
        var request = new Verify(employee, id, Platform.GITHUB, "Write");
        assertEquals(404, assertThrows(ResponseStatusException.class, () -> service.verify(request)).getStatusCode().value());
        doReturn(target(Platform.GITHUB, AccessScope.GENERAL)).when(grants).resource(id);
        when(facts.profile(employee)).thenThrow(new EmptyResultDataAccessException(1));
        assertEquals(404, assertThrows(ResponseStatusException.class, () -> service.verify(request)).getStatusCode().value());
        verify(facts, never()).current(any(), any());
    }

    @Test void platformMismatchStopsBeforeReadingEmployeePermissions() {
        when(grants.resource(id)).thenReturn(target(Platform.GITHUB, AccessScope.GENERAL));
        assertEquals(409, assertThrows(ResponseStatusException.class, () ->
            service.verify(new Verify(employee, id, Platform.JIRA, "Developer"))).getStatusCode().value());
        verifyNoInteractions(facts);
    }
}
