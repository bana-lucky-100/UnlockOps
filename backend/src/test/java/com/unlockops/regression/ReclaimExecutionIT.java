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

/** Mock revoke HTTP behavior against disposable PostgreSQL and broker. */
@SpringBootTest(properties = {"app.demo-enabled=true", "app.demo-password=regression-password"})
@AutoConfigureMockMvc
@org.springframework.transaction.annotation.Transactional
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ReclaimExecutionIT {
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
    void scanFreezesCurrentCandidateAndUnknownUsageWithoutChangingAssignments() throws Exception {
        var operator = login("p2_a_operator");
        var scope = jdbc.queryForObject("SELECT id::text FROM reclaim_scopes WHERE scope_key='phase2:A:paid-seats'", String.class);
        jdbc.update("INSERT INTO reclaim_scope_assignments(scope_id,company_id,assignment_id) SELECT ?::uuid,company_id,id FROM access_assignments WHERE id='cde5e7bf-1508-5029-a86d-a9996318ba98'", scope);
        var before = jdbc.queryForObject("SELECT jsonb_agg(to_jsonb(a) ORDER BY id)::text FROM access_assignments a", String.class);
        var run = body(mvc.perform(post("/api/reclaim/runs").session(operator).with(csrf())
            .header("Idempotency-Key", "facts-baseline").contentType("application/json")
            .content(json.writeValueAsString(java.util.Map.of("scope_id", scope))))
            .andExpect(status().isAccepted()).andReturn());
        var facts = json.readTree(jdbc.queryForObject("SELECT facts::text FROM reclaim_snapshot_items WHERE snapshot_id=?::uuid AND assignment_id=?::uuid", String.class, run.path("snapshot_id").asText(), "7f259edc-2eac-57e0-b0c2-e46b5628e68a"));
        assertEquals("PENDING_REVIEW", facts.path("candidate").path("candidate_status").asText());
        assertEquals("TF_ENDED_UNUSED_30D", facts.path("candidate").path("candidate_reason_code").asText());
        assertEquals("19.00", facts.path("candidate").path("cost_impact").path("monthly_amount").asText());
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM reclaim_snapshot_items WHERE snapshot_id=?::uuid AND facts->'candidate'->>'review_required'='true'", Integer.class, run.path("snapshot_id").asText()));
        assertEquals(before, jdbc.queryForObject("SELECT jsonb_agg(to_jsonb(a) ORDER BY id)::text FROM access_assignments a", String.class));
    }
}
