package com.unlockops;

import com.unlockops.auth.repository.UserRepository;
import com.unlockops.config.InternalApiSecurityConfig;
import com.unlockops.config.SecurityConfig;
import com.unlockops.grant.model.*;
import com.unlockops.resource.controller.InternalResourceController;
import com.unlockops.resource.model.ResourceCandidate;
import com.unlockops.resource.repository.ResourceRepository;
import com.unlockops.resource.service.ResourceService;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import static org.mockito.Mockito.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(controllers = InternalResourceController.class, properties = "app.internal-api-token=resource-test-token")
@Import({SecurityConfig.class, InternalApiSecurityConfig.class, ResourceService.class})
class InternalResourceApiTest {
    @Autowired MockMvc mvc;
    @MockitoBean UserRepository users;
    @MockitoBean ResourceRepository resources;

    @Test void serviceTokenCanResolveWithoutBrowserSessionOrCsrf() throws Exception {
        UUID id = UUID.randomUUID();
        when(resources.findByPlatform(Platform.GITHUB)).thenReturn(List.of(new ResourceCandidate(
            id, Platform.GITHUB, "payment-core", "결제 저장소", List.of("결제코어"),
            AccessScope.GENERAL, null, null, SecurityGrade.INTERNAL, null)));
        mvc.perform(post("/internal/resources/resolve").header("Authorization", "Bearer resource-test-token")
            .contentType("application/json").content("{\"platform\":\"GITHUB\",\"hint\":\"payment-core push 실패\"}"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.ambiguous").value(false))
            .andExpect(jsonPath("$.matches[0].id").value(id.toString()))
            .andExpect(jsonPath("$.matches[0].external_id").value("payment-core"))
            .andExpect(jsonPath("$.matches[0].access_scope").value("GENERAL"))
            .andExpect(jsonPath("$.matches[0].aliases[0]").value("결제코어"));
    }

    @Test void anonymousWrongTokenAndBrowserLoginCannotAccessInternalApi() throws Exception {
        for (String token : List.of("", "Bearer wrong-token"))
            mvc.perform(post("/internal/resources/resolve").header("Authorization", token)
                .contentType("application/json").content("{\"platform\":\"GITHUB\",\"hint\":\"payment-core\"}"))
                .andExpect(status().isUnauthorized()).andExpect(jsonPath("$.message").exists());
        mvc.perform(post("/internal/resources/resolve").with(user("browser-user")).with(csrf())
            .contentType("application/json").content("{\"platform\":\"GITHUB\",\"hint\":\"payment-core\"}"))
            .andExpect(status().isUnauthorized());
        verifyNoInteractions(resources);
    }

    @Test void invalidInputsAreRejectedBeforeDatabaseLookup() throws Exception {
        for (String body : List.of("{}", "{\"platform\":\"OTHER\",\"hint\":\"x\"}",
                "{\"platform\":\"GITHUB\"}", "{\"platform\":\"GITHUB\",\"hint\":\"" + "x".repeat(5001) + "\"}"))
            mvc.perform(post("/internal/resources/resolve").header("Authorization", "Bearer resource-test-token")
                .contentType("application/json").content(body))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.message").exists());
        verifyNoInteractions(resources);
    }

    @Test void noCandidateIsAValidAmbiguousResult() throws Exception {
        when(resources.findByPlatform(Platform.JIRA)).thenReturn(List.of());
        mvc.perform(post("/internal/resources/resolve").header("Authorization", "Bearer resource-test-token")
            .contentType("application/json").content("{\"platform\":\"JIRA\",\"hint\":\"unknown-project\"}"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.matches").isEmpty())
            .andExpect(jsonPath("$.ambiguous").value(true));
        verify(resources).findByPlatform(Platform.JIRA);
    }

    @Test void serviceTokenDoesNotAuthenticateBrowserApi() throws Exception {
        mvc.perform(get("/api/auth/me").header("Authorization", "Bearer resource-test-token"))
            .andExpect(status().isUnauthorized());
    }
}
