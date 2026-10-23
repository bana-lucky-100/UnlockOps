package com.unlockops.regression;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.scheduling.annotation.ScheduledAnnotationBeanPostProcessor;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Initial delivered notifications must be readable without starting a new scan. */
@SpringBootTest(properties = {"app.demo-enabled=true", "app.demo-password=regression-password"})
@AutoConfigureMockMvc
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ReclaimSeedReportIT {
    private static final String TARGET = "e6b04385-a16d-501a-99ee-809760daf458";
    private static final String ASSIGNMENT = "2c1922f4-234b-5126-8ddc-9a3bdf702237";
    private static final String NOTIFICATION = "cf2e7f19-66cc-57b6-bfc3-60c8bd51a708";
    private static final Path SEED = Path.of("../data/phase2/seed.sql").toAbsolutePath();

    @Container static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:16-alpine");
    @Container static final RabbitMQContainer BROKER = new RabbitMQContainer("rabbitmq:4-management-alpine");

    @DynamicPropertySource
    static void services(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
        registry.add("spring.rabbitmq.host", BROKER::getHost);
        registry.add("spring.rabbitmq.port", BROKER::getAmqpPort);
        registry.add("spring.rabbitmq.username", BROKER::getAdminUsername);
        registry.add("spring.rabbitmq.password", BROKER::getAdminPassword);
        registry.add("app.demo-seed-path", SEED::toString);
    }

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper json;

    @AfterAll
    static void stopPublishing(@Autowired ScheduledAnnotationBeanPostProcessor scheduling) {
        scheduling.destroy();
    }

    private JsonNode body(MvcResult result) throws Exception {
        return json.readTree(result.getResponse().getContentAsString());
    }

    private MockHttpSession login(String loginId) throws Exception {
        return (MockHttpSession) mvc.perform(post("/api/auth/demo-login").with(csrf())
            .contentType("application/json").content(json.writeValueAsString(java.util.Map.of("loginId", loginId))))
            .andExpect(status().isOk()).andReturn().getRequest().getSession(false);
    }

    @Test
    void deliveredSeedNotificationHasReportAndAppearsInOverviewBeforeAnyNewScan() throws Exception {
        var operator = login("p2_a_operator");
        var notifications = body(mvc.perform(get("/api/reclaim/notifications").session(operator))
            .andExpect(status().isOk()).andReturn());
        assertTrue(notifications.findValuesAsText("target_id").contains(TARGET));

        var report = body(mvc.perform(get("/api/reclaim/targets/" + TARGET).session(operator))
            .andExpect(status().isOk()).andReturn());
        assertEquals(TARGET, report.path("target_id").asText());
        assertEquals(ASSIGNMENT, report.path("assignment_id").asText());
        assertEquals("PENDING_REVIEW", report.path("candidate_status").asText());
        assertEquals("19.00", report.path("cost_impact").path("monthly_amount").asText());
        assertEquals("NONE", report.path("action_taken").asText());
        assertFalse(report.path("policy_evidence").isEmpty());
        assertFalse(report.path("fact_evidence").isEmpty());
        assertEquals("1", report.path("policy_evidence").get(0).path("version").asText());

        var overview = body(mvc.perform(get("/api/reclaim/overview").session(operator))
            .andExpect(status().isOk()).andReturn());
        assertTrue(overview.path("targets").findValuesAsText("target_id").contains(TARGET));
        var priorRun = overview.path("last_run");
        assertEquals("DONE", priorRun.path("status").asText());
        mvc.perform(get("/api/reclaim/runs/" + priorRun.path("run_id").asText() + "/items").session(operator))
            .andExpect(status().isOk()).andExpect(jsonPath("$[0].target_id").value(TARGET));

        mvc.perform(get("/api/reclaim/targets/" + TARGET).session(login("p2_b_operator")))
            .andExpect(status().isForbidden());
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM outbox WHERE payload->>'task_type'='RECLAIM_SCAN'", Integer.class));
    }

    @Test
    void reapplyingSeedPreservesReportNotificationAndReadState() throws Exception {
        var operator = login("p2_a_operator");
        mvc.perform(patch("/api/reclaim/notifications/" + NOTIFICATION + "/read").session(operator).with(csrf()))
            .andExpect(status().isOk());
        String notification = jdbc.queryForObject("SELECT to_jsonb(n)::text FROM reclaim_notifications n WHERE id=?::uuid", String.class, NOTIFICATION);
        String report = jdbc.queryForObject("SELECT report::text FROM reclaim_run_items WHERE target_id=?::uuid", String.class, TARGET);
        String assignment = jdbc.queryForObject("SELECT to_jsonb(a)::text FROM access_assignments a WHERE id=?::uuid", String.class, ASSIGNMENT);
        String budget = jdbc.queryForObject("SELECT remaining_monthly_amount::text FROM department_budgets WHERE department_id=(SELECT department_id FROM users WHERE login_id='p2_a_operator')", String.class);
        String script = Files.readString(SEED);
        jdbc.execute((ConnectionCallback<Void>) connection -> {
            try (var statement = connection.createStatement()) {
                statement.execute(script);
                statement.execute(script);
            }
            return null;
        });
        assertEquals(report, jdbc.queryForObject("SELECT report::text FROM reclaim_run_items WHERE target_id=?::uuid", String.class, TARGET));
        assertEquals(notification, jdbc.queryForObject("SELECT to_jsonb(n)::text FROM reclaim_notifications n WHERE id=?::uuid", String.class, NOTIFICATION));
        assertEquals(assignment, jdbc.queryForObject("SELECT to_jsonb(a)::text FROM access_assignments a WHERE id=?::uuid", String.class, ASSIGNMENT));
        assertEquals(budget, jdbc.queryForObject("SELECT remaining_monthly_amount::text FROM department_budgets WHERE department_id=(SELECT department_id FROM users WHERE login_id='p2_a_operator')", String.class));
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM reclaim_run_items WHERE target_id=?::uuid", Integer.class, TARGET));
    }
}
