package com.unlockops;

import com.unlockops.access.controller.InternalAccessContextController;
import com.unlockops.access.dto.AccessContextResponses.*;
import com.unlockops.access.repository.AccessContextRepository;
import com.unlockops.access.service.*;
import com.unlockops.auth.model.*;
import com.unlockops.auth.repository.UserRepository;
import com.unlockops.config.*;
import com.unlockops.grant.model.*;
import com.unlockops.grant.repository.GrantRepository;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.server.ResponseStatusException;
import static org.mockito.Mockito.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(controllers = InternalAccessContextController.class, properties = "app.internal-api-token=context-test-token")
@Import({SecurityConfig.class, InternalApiSecurityConfig.class, AccessContextService.class})
class InternalAccessContextApiTest {
    @Autowired MockMvc mvc;
    @MockitoBean UserRepository users;
    @MockitoBean GrantRepository grants;
    @MockitoBean AccessContextRepository facts;
    @MockitoBean AccessCeilingPolicy policy;
    private final UUID employee = UUID.randomUUID(), resource = UUID.randomUUID();

    private String body() {
        return "{\"employeeId\":\"" + employee + "\",\"resourceId\":\"" + resource + "\",\"platform\":\"GITHUB\"}";
    }

    @Test void validTokenReturnsAllowlistedFactsInSnakeCaseWithoutCsrf() throws Exception {
        var target = new Resource(resource, Platform.GITHUB, "payment-core", AccessScope.TF, null, UUID.randomUUID(), null, null);
        when(grants.resource(resource)).thenReturn(target);
        when(facts.profile(employee)).thenReturn(new Profile(employee, "E-001", "직원", UUID.randomUUID(),
            "개발팀", JobGrade.STAFF, JobFamily.DEV, null));
        when(facts.membership(employee, resource)).thenReturn(new Membership(target.tfId(), false, UUID.randomUUID()));
        when(facts.current(employee, target)).thenReturn(new Current(null, "github-team-membership", List.of(), null));
        when(policy.ceiling(any(), eq(target))).thenReturn(new AccessCeilingPolicy.Ceiling("Write", Map.of("matrix", "hash")));
        mvc.perform(post("/internal/access-context").header("Authorization", "Bearer context-test-token")
            .contentType("application/json").content(body())).andExpect(status().isOk())
            .andExpect(jsonPath("$.profile.job_grade").value("사원"))
            .andExpect(jsonPath("$.profile.job_family").value("DEV"))
            .andExpect(jsonPath("$.profile.password_hash").doesNotExist())
            .andExpect(jsonPath("$.profile.login_id").doesNotExist())
            .andExpect(jsonPath("$.profile.email").doesNotExist())
            .andExpect(jsonPath("$.membership.member").value(false))
            .andExpect(jsonPath("$.maximum_role").value("Write"))
            .andExpect(jsonPath("$.budget").isEmpty())
            .andExpect(jsonPath("$.current.role").isEmpty())
            .andExpect(jsonPath("$.current.teams").isArray())
            .andExpect(jsonPath("$.current.can_browse").doesNotExist());
    }

    @Test void tokenIsRequiredEvenWithBrowserLogin() throws Exception {
        mvc.perform(post("/internal/access-context").contentType("application/json").content(body()))
            .andExpect(status().isUnauthorized());
        mvc.perform(post("/internal/access-context").with(user("browser-user")).with(csrf())
            .contentType("application/json").content(body())).andExpect(status().isUnauthorized());
        mvc.perform(post("/internal/access-context").header("Authorization", "Bearer wrong")
            .contentType("application/json").content(body())).andExpect(status().isUnauthorized());
        verifyNoInteractions(grants, facts, policy);
    }

    @Test void missingInvalidIdsAndPlatformFailBeforeDatabaseAccess() throws Exception {
        for (String input : List.of("{}", body().replace(employee.toString(), "invalid"),
                body().replace("GITHUB", "OTHER"), body().replace("\"employeeId\"", "\"employee_id\""),
                "{\"employeeId\":\"" + employee + "\",\"platform\":\"GITHUB\"}"))
            mvc.perform(post("/internal/access-context").header("Authorization", "Bearer context-test-token")
                .contentType("application/json").content(input))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.message").exists());
        verifyNoInteractions(grants, facts, policy);
    }

    @Test void unknownResourceReturns404AndInvalidPolicyReturns503() throws Exception {
        when(grants.resource(resource)).thenThrow(new EmptyResultDataAccessException(1));
        mvc.perform(post("/internal/access-context").header("Authorization", "Bearer context-test-token")
            .contentType("application/json").content(body())).andExpect(status().isNotFound());
        doReturn(new Resource(resource, Platform.GITHUB, "example", AccessScope.GENERAL,
            null, null, null, null)).when(grants).resource(resource);
        when(facts.profile(employee)).thenReturn(new Profile(employee, "E-001", "직원", UUID.randomUUID(), "개발팀",
            JobGrade.STAFF, JobFamily.DEV, null));
        when(policy.ceiling(any(), any())).thenThrow(new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "규정 확인 불가"));
        mvc.perform(post("/internal/access-context").header("Authorization", "Bearer context-test-token")
            .contentType("application/json").content(body())).andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.message").value("규정 확인 불가"));
    }

    @Test void employeeOnlyLookupCanExplicitlyRequestBudgetWithoutAResource() throws Exception {
        UUID department = UUID.randomUUID();
        when(facts.profile(employee)).thenReturn(new Profile(employee, "E-001", "직원", department, "개발팀",
            JobGrade.STAFF, JobFamily.DEV, null));
        when(facts.budget(department)).thenReturn(new Budget(department, "150.00", "19.00", "USD", null));
        mvc.perform(post("/internal/access-context").header("Authorization", "Bearer context-test-token")
            .contentType("application/json").content("{\"employeeId\":\"" + employee + "\"}"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.profile.id").value(employee.toString()))
            .andExpect(jsonPath("$.resource_id").isEmpty()).andExpect(jsonPath("$.maximum_role").isEmpty())
            .andExpect(jsonPath("$.budget").isEmpty());
        verify(facts, never()).budget(any());
        mvc.perform(post("/internal/access-context").header("Authorization", "Bearer context-test-token")
            .contentType("application/json").content("{\"employeeId\":\"" + employee + "\",\"includeBudget\":true}"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.budget.unit_monthly_price").value("19.00"));
        verifyNoInteractions(grants, policy);
    }

    @Test void resourceIdCanDetermineThePlatformForExistingMcpTools() throws Exception {
        when(grants.resource(resource)).thenReturn(new Resource(resource, Platform.GITHUB, "example", AccessScope.GENERAL,
            null, null, null, null));
        when(facts.profile(employee)).thenReturn(new Profile(employee, "E-001", "직원", UUID.randomUUID(), "개발팀",
            JobGrade.STAFF, JobFamily.DEV, null));
        when(policy.ceiling(any(), any())).thenReturn(new AccessCeilingPolicy.Ceiling("Read", Map.of()));
        mvc.perform(post("/internal/access-context").header("Authorization", "Bearer context-test-token")
            .contentType("application/json").content(body().replace(",\"platform\":\"GITHUB\"", "")))
            .andExpect(status().isOk()).andExpect(jsonPath("$.maximum_role").value("Read"));
    }

    @Test void policySourceErrorsHaveDistinctCodesInsteadOfLookingLikeNetworkOutages() throws Exception {
        when(grants.resource(resource)).thenReturn(new Resource(resource, Platform.GITHUB, "example", AccessScope.GENERAL,
            null, null, null, null));
        when(facts.profile(employee)).thenReturn(new Profile(employee, "E-001", "직원", UUID.randomUUID(), "개발팀",
            JobGrade.STAFF, JobFamily.DEV, null));
        when(policy.ceiling(any(), any())).thenThrow(new com.unlockops.common.error.PolicySourceUnavailableException());
        mvc.perform(post("/internal/access-context").header("Authorization", "Bearer context-test-token")
            .contentType("application/json").content(body())).andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.code").value("POLICY_SOURCE_UNAVAILABLE"))
            .andExpect(jsonPath("$.retryable").value(false)).andExpect(jsonPath("$.message").exists());
    }
}
