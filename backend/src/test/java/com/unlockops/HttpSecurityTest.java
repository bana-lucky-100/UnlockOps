package com.unlockops;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest({ProblemController.class,ApprovalsController.class})
@Import({SecurityConfig.class,ProblemService.class,GrantRules.class,Jsons.class})
class HttpSecurityTest {
    @Autowired MockMvc mvc;
    @MockitoBean JdbcTemplate jdbc;

    @Test void anonymousCannotReadResults() throws Exception {
        mvc.perform(get("/api/problems")).andExpect(status().isUnauthorized());
    }
    @Test void requesterCannotReadAssignedInboxWithoutMine() throws Exception {
        var principal=new AppUser(UUID.randomUUID(),"requester","hash","REQUESTER");
        mvc.perform(get("/api/problems").with(user(principal))).andExpect(status().isForbidden());
    }
    @Test void requesterCannotReadDepartmentSummary() throws Exception {
        var principal=new AppUser(UUID.randomUUID(),"requester","hash","REQUESTER");
        mvc.perform(get("/api/approvals/summary").with(user(principal))).andExpect(status().isForbidden());
    }
    @Test void sessionAuthenticationDoesNotBypassCsrf() throws Exception {
        var principal=new AppUser(UUID.randomUUID(),"requester","hash","REQUESTER");
        mvc.perform(post("/api/problems").with(user(principal)).contentType("application/json")
            .content("{\"platform\":\"GITHUB\",\"contents\":\"payment-core push가 안 됩니다\"}"))
            .andExpect(status().isForbidden());
    }
}
