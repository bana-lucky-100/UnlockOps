package com.unlockops;

import com.unlockops.access.controller.InternalAccessVerificationController;
import com.unlockops.access.dto.AccessContextResponses.Current;
import com.unlockops.access.repository.AccessContextRepository;
import com.unlockops.access.service.AccessVerificationService;
import com.unlockops.auth.repository.UserRepository;
import com.unlockops.config.*;
import com.unlockops.grant.model.*;
import com.unlockops.grant.repository.GrantRepository;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import static org.mockito.Mockito.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(controllers = InternalAccessVerificationController.class, properties = "app.internal-api-token=verification-test-token")
@Import({SecurityConfig.class, InternalApiSecurityConfig.class, AccessVerificationService.class})
class InternalAccessVerificationApiTest {
    @Autowired MockMvc mvc;
    @MockitoBean UserRepository users;
    @MockitoBean GrantRepository grants;
    @MockitoBean AccessContextRepository facts;
    private final UUID employee = UUID.randomUUID(), id = UUID.randomUUID();
    private final Resource resource = new Resource(id, Platform.GITHUB, "payment-core", AccessScope.TF, null, UUID.randomUUID(), null, null);

    private String body() {
        return "{\"employeeId\":\"" + employee + "\",\"resourceId\":\"" + id + "\",\"platform\":\"GITHUB\",\"requestedRole\":\"Write\"}";
    }

    @Test void tokenAuthenticatedRequestReturnsActualPermissionsWithoutCsrf() throws Exception {
        when(grants.resource(id)).thenReturn(resource);
        when(facts.current(employee, resource)).thenReturn(new Current("Write", "github-team-membership", List.of("write-team"), null));
        mvc.perform(post("/internal/access-verifications").header("Authorization", "Bearer verification-test-token")
            .contentType("application/json").content(body())).andExpect(status().isOk())
            .andExpect(jsonPath("$.ok").value(true)).andExpect(jsonPath("$.verified").value(true))
            .andExpect(jsonPath("$.current.role").value("Write"))
            .andExpect(jsonPath("$.current.source").value("github-team-membership"))
            .andExpect(jsonPath("$.current.teams[0]").value("write-team"))
            .andExpect(jsonPath("$.current.can_browse").doesNotExist());
    }

    @Test void unreflectedPermissionsAreSuccessfulReadsWithVerifiedFalse() throws Exception {
        when(grants.resource(id)).thenReturn(resource);
        when(facts.current(employee, resource)).thenReturn(new Current(null, "github-team-membership", List.of(), null));
        mvc.perform(post("/internal/access-verifications").header("Authorization", "Bearer verification-test-token")
            .contentType("application/json").content(body())).andExpect(status().isOk())
            .andExpect(jsonPath("$.ok").value(true)).andExpect(jsonPath("$.verified").value(false));
    }

    @Test void browserSessionMissingAndWrongTokensCannotVerify() throws Exception {
        mvc.perform(post("/internal/access-verifications").with(user("browser")).with(csrf())
            .contentType("application/json").content(body())).andExpect(status().isUnauthorized());
        mvc.perform(post("/internal/access-verifications").contentType("application/json").content(body()))
            .andExpect(status().isUnauthorized());
        mvc.perform(post("/internal/access-verifications").header("Authorization", "Bearer wrong")
            .contentType("application/json").content(body())).andExpect(status().isUnauthorized());
        verifyNoInteractions(grants, facts);
    }

    @Test void invalidFieldsAndForbiddenRolesFailBeforeLookup() throws Exception {
        for (String input : List.of("{}", body().replace(employee.toString(), "invalid"), body().replace("GITHUB", "OTHER"),
                body().replace("Write", "Owner"), body().replace("Write", "Admin"), body().replace("Write", ""),
                body().replace("\"requestedRole\"", "\"requested_role\"")))
            mvc.perform(post("/internal/access-verifications").header("Authorization", "Bearer verification-test-token")
                .contentType("application/json").content(input)).andExpect(status().isBadRequest());
        verifyNoInteractions(grants, facts);
    }

    @Test void lookupFailureIsNotReturnedAsVerifiedFalse() throws Exception {
        when(grants.resource(id)).thenThrow(new EmptyResultDataAccessException(1));
        mvc.perform(post("/internal/access-verifications").header("Authorization", "Bearer verification-test-token")
            .contentType("application/json").content(body())).andExpect(status().isNotFound());
        doReturn(resource).when(grants).resource(id);
        when(facts.current(employee, resource)).thenThrow(new org.springframework.dao.DataAccessResourceFailureException("private SQL"));
        mvc.perform(post("/internal/access-verifications").header("Authorization", "Bearer verification-test-token")
            .contentType("application/json").content(body())).andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.verified").doesNotExist())
            .andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("private SQL"))));
    }

    @Test void resourceIdAloneCanSupplyThePlatformForExistingMcpVerification() throws Exception {
        when(grants.resource(id)).thenReturn(resource);
        when(facts.current(employee, resource)).thenReturn(new Current("Write", "github-team-membership", List.of("write-team"), null));
        mvc.perform(post("/internal/access-verifications").header("Authorization", "Bearer verification-test-token")
            .contentType("application/json").content(body().replace(",\"platform\":\"GITHUB\"", "")))
            .andExpect(status().isOk()).andExpect(jsonPath("$.verified").value(true));
    }
}
