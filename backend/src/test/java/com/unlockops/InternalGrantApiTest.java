package com.unlockops;

import com.unlockops.auth.repository.UserRepository;
import com.unlockops.config.*;
import com.unlockops.grant.controller.InternalGrantController;
import com.unlockops.grant.dto.GrantExecutionResponses.Success;
import com.unlockops.grant.model.SaasRole;
import com.unlockops.grant.service.*;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import static org.mockito.Mockito.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(controllers = InternalGrantController.class, properties = "app.internal-api-token=grant-test-token")
@Import({SecurityConfig.class, InternalApiSecurityConfig.class})
class InternalGrantApiTest {
    @Autowired MockMvc mvc;
    @MockitoBean UserRepository users;
    @MockitoBean GrantExecutionService service;
    private final UUID id = UUID.randomUUID();

    @Test void authenticatedServiceGetsAnExecutionReceiptWithoutCsrf() throws Exception {
        when(service.execute(id, "key")).thenReturn(new Success(true, SaasRole.WRITE));
        mvc.perform(post("/internal/problems/" + id + "/grant").header("Authorization", "Bearer grant-test-token")
            .contentType("application/json").content("{\"idempotencyKey\":\"key\"}"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.ok").value(true))
            .andExpect(jsonPath("$.changed").value(true)).andExpect(jsonPath("$.role").value("Write"));
    }

    @Test void browserSessionAndMissingTokenCannotExecute() throws Exception {
        mvc.perform(post("/internal/problems/" + id + "/grant").with(user("browser")).with(csrf())
            .contentType("application/json").content("{\"idempotencyKey\":\"key\"}"))
            .andExpect(status().isUnauthorized());
        verifyNoInteractions(service);
    }

    @Test void missingKeyAndMalformedIdsAreRejected() throws Exception {
        for (String body : new String[]{"{}", "{\"idempotencyKey\":\" \"}", "{\"idempotencyKey\":\"" + "a".repeat(151) + "\"}"})
            mvc.perform(post("/internal/problems/" + id + "/grant").header("Authorization", "Bearer grant-test-token")
                .contentType("application/json").content(body)).andExpect(status().isBadRequest());
        mvc.perform(post("/internal/problems/not-a-uuid/grant").header("Authorization", "Bearer grant-test-token")
            .contentType("application/json").content("{\"idempotencyKey\":\"key\"}"))
            .andExpect(status().isBadRequest());
        verifyNoInteractions(service);
    }

    @Test void policyFailureHasMachineReadableCodeAndIsNotRetryable() throws Exception {
        when(service.execute(id, "key")).thenThrow(GrantExecutionException.precondition("POLICY_EVIDENCE_MISMATCH"));
        mvc.perform(post("/internal/problems/" + id + "/grant").header("Authorization", "Bearer grant-test-token")
            .contentType("application/json").content("{\"idempotencyKey\":\"key\"}"))
            .andExpect(status().isConflict()).andExpect(jsonPath("$.ok").value(false))
            .andExpect(jsonPath("$.error.code").value("PRECONDITION_CHANGED"))
            .andExpect(jsonPath("$.error.reason").value("POLICY_EVIDENCE_MISMATCH"))
            .andExpect(jsonPath("$.error.retryable").value(false));
    }

    @Test void jiraFailureIsRetryableAndDatabaseErrorDoesNotLeakSql() throws Exception {
        when(service.execute(id, "key")).thenThrow(new GrantExecutionException(HttpStatus.SERVICE_UNAVAILABLE,
            "MOCK_JIRA_UNAVAILABLE", "일시 장애", true, null));
        mvc.perform(post("/internal/problems/" + id + "/grant").header("Authorization", "Bearer grant-test-token")
            .contentType("application/json").content("{\"idempotencyKey\":\"key\"}"))
            .andExpect(status().isServiceUnavailable()).andExpect(jsonPath("$.error.retryable").value(true));
        doThrow(new org.springframework.jdbc.CannotGetJdbcConnectionException("private connection"))
            .when(service).execute(id, "key");
        mvc.perform(post("/internal/problems/" + id + "/grant").header("Authorization", "Bearer grant-test-token")
            .contentType("application/json").content("{\"idempotencyKey\":\"key\"}"))
            .andExpect(status().isServiceUnavailable()).andExpect(jsonPath("$.error.code").value("UPSTREAM_UNAVAILABLE"))
            .andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("private connection"))));
    }
}
