package com.unlockops;

import com.unlockops.access.*;
import com.unlockops.auth.model.*;
import com.unlockops.auth.repository.UserRepository;
import com.unlockops.common.workflow.WorkflowStore;
import com.unlockops.config.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import static org.mockito.Mockito.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(value={AccessController.class,InternalAccessController.class},properties="app.internal-api-token=test-internal-token")
@Import({SecurityConfig.class,InternalApiSecurityConfig.class})
class HttpSecurityTest {
    @Autowired MockMvc mvc;
    @MockitoBean UserRepository users;
    @MockitoBean WorkflowStore store;
    @MockitoBean AccessWorkflowService workflow;
    @MockitoBean AccessExecutionService execution;
    private final UUID id=UUID.randomUUID();
    private final AppUser principal=new AppUser(UUID.randomUUID(),"requester","hash",UserRole.REQUESTER);

    @Test void anonymousCannotReadCurrentResults() throws Exception {
        mvc.perform(get("/api/v2/problems")).andExpect(status().isUnauthorized());
        verifyNoInteractions(workflow);
    }
    @Test void sessionAuthenticationDoesNotBypassCsrf() throws Exception {
        mvc.perform(post("/api/v2/problems").with(user(principal)).contentType("application/json")
            .content("{\"schema_version\":2,\"platform\":\"GITHUB\",\"contents\":\"좌석 신청\"}"))
            .andExpect(status().isForbidden());
        verifyNoInteractions(workflow);
    }
    @Test void authenticatedReadUsesCurrentActor() throws Exception {
        when(workflow.list(principal.id())).thenReturn(List.of());
        mvc.perform(get("/api/v2/problems").with(user(principal))).andExpect(status().isOk());
        verify(workflow).list(principal.id());
    }
    @Test void internalApiRequiresServiceTokenEvenWithSession() throws Exception {
        mvc.perform(get("/internal/v2/problems/"+id+"/context").with(user(principal)))
            .andExpect(status().isUnauthorized());
        verifyNoInteractions(workflow);
    }
    @Test void serviceTokenReadsCurrentContext() throws Exception {
        when(workflow.context(id)).thenReturn(Map.of("schema_version",2));
        mvc.perform(get("/internal/v2/problems/"+id+"/context").header("Authorization","Bearer test-internal-token"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.schema_version").value(2));
        verify(workflow).context(id);
    }
}
