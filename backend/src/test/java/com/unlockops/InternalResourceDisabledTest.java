package com.unlockops;

import com.unlockops.auth.repository.UserRepository;
import com.unlockops.config.InternalApiSecurityConfig;
import com.unlockops.config.SecurityConfig;
import com.unlockops.resource.controller.InternalResourceController;
import com.unlockops.resource.service.ResourceService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = InternalResourceController.class, properties = "app.internal-api-token=")
@Import({SecurityConfig.class, InternalApiSecurityConfig.class})
class InternalResourceDisabledTest {
    @Autowired MockMvc mvc;
    @MockitoBean UserRepository users;
    @MockitoBean ResourceService resources;

    @Test void explicitlyEmptyTokenDisablesInternalApiEvenWithBearerHeader() throws Exception {
        mvc.perform(post("/internal/resources/resolve").header("Authorization", "Bearer ")
            .contentType("application/json").content("{\"platform\":\"GITHUB\",\"hint\":\"payment-core\"}"))
            .andExpect(status().isUnauthorized());
        verifyNoInteractions(resources);
    }
}
