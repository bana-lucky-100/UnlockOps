package com.unlockops;

import com.unlockops.approval.controller.ApprovalsController;
import com.unlockops.approval.repository.ApprovalRepository;
import com.unlockops.approval.service.ApprovalService;
import com.unlockops.auth.model.*;
import com.unlockops.auth.repository.UserRepository;
import com.unlockops.common.json.Jsons;
import com.unlockops.config.SecurityConfig;
import com.unlockops.grant.repository.GrantRepository;
import com.unlockops.grant.service.GrantPolicy;
import com.unlockops.messaging.service.JobService;
import com.unlockops.problem.controller.ProblemController;
import com.unlockops.problem.repository.*;
import com.unlockops.problem.service.ProblemService;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest({ProblemController.class, ApprovalsController.class})
@Import({SecurityConfig.class, ProblemService.class, ApprovalService.class, GrantPolicy.class, Jsons.class})
class HttpSecurityTest {
    @Autowired MockMvc mvc;
    @MockitoBean UserRepository users;
    @MockitoBean GrantRepository grants;
    @MockitoBean ProblemRepository problems;
    @MockitoBean ProblemEventRepository events;
    @MockitoBean ApprovalRepository approvals;
    @MockitoBean JobService jobs;

    @Test void anonymousCannotReadResults() throws Exception {
        mvc.perform(get("/api/problems")).andExpect(status().isUnauthorized());
    }
    @Test void requesterCannotReadAssignedInboxWithoutMine() throws Exception {
        var principal = new AppUser(UUID.randomUUID(), "requester", "hash", UserRole.REQUESTER);
        mvc.perform(get("/api/problems").with(user(principal))).andExpect(status().isForbidden());
    }
    @Test void requesterCannotReadDepartmentSummary() throws Exception {
        var principal = new AppUser(UUID.randomUUID(), "requester", "hash", UserRole.REQUESTER);
        mvc.perform(get("/api/approvals/summary").with(user(principal))).andExpect(status().isForbidden());
    }
    @Test void sessionAuthenticationDoesNotBypassCsrf() throws Exception {
        var principal = new AppUser(UUID.randomUUID(), "requester", "hash", UserRole.REQUESTER);
        mvc.perform(post("/api/problems").with(user(principal)).contentType("application/json")
            .content("{\"platform\":\"GITHUB\",\"contents\":\"payment-core push가 안 됩니다\"}"))
            .andExpect(status().isForbidden());
    }
}
