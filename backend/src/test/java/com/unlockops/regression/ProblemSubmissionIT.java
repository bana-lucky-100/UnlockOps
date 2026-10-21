package com.unlockops.regression;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.unlockops.messaging.repository.OutboxRepository;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.ScheduledAnnotationBeanPostProcessor;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Real HTTP handling and independent PostgreSQL transactions, including a deliberately blocked winner. */
@SpringBootTest(properties = {
    "app.demo-enabled=true", "app.demo-password=submission-password",
    "spring.rabbitmq.listener.simple.auto-startup=false",
    "logging.level.org.springframework=WARN", "logging.level.com.unlockops=WARN"
})
@AutoConfigureMockMvc
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ProblemSubmissionIT {
    @Container static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:16-alpine");
    @Container static final RabbitMQContainer BROKER = new RabbitMQContainer("rabbitmq:4-management-alpine");

    @DynamicPropertySource static void services(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
        registry.add("spring.rabbitmq.host", BROKER::getHost);
        registry.add("spring.rabbitmq.port", BROKER::getAmqpPort);
        registry.add("spring.rabbitmq.username", BROKER::getAdminUsername);
        registry.add("spring.rabbitmq.password", BROKER::getAdminPassword);
    }

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper json;
    @MockitoSpyBean OutboxRepository outbox;
    MockHttpSession requester;

    @AfterAll static void stopPublishingBeforeContainersStop(@Autowired ScheduledAnnotationBeanPostProcessor scheduling) {
        // Keep Spring's own context lifecycle; stop background DB polling while its services are still alive.
        scheduling.destroy();
    }

    @BeforeEach void resetRequests() throws Exception {
        jdbc.execute("TRUNCATE grant_receipts,problem_events,outbox,inbox_events,problems RESTART IDENTITY");
        requester = login("kim_dev");
    }

    @Test void repeatedKeyCreatesOneRequestAndOutbox() throws Exception {
        String key = UUID.randomUUID().toString();
        Response first = submit(key, request("GITHUB", "payment-core", false), requester);
        Response retry = submit(key, request("GITHUB", "payment-core", false), requester);
        assertEquals(202, first.code());
        assertEquals(202, retry.code());
        assertEquals(first.body(), retry.body());
        assertCounts(1);
        JsonNode job = json.readTree(jdbc.queryForObject("SELECT payload::text FROM outbox", String.class));
        assertEquals(first.body().path("id"), job.path("problem_id"));
        assertEquals("ANALYZE", job.path("job_type").asText());
        assertFalse(job.has("client_request_key"));
        assertNull(jdbc.queryForObject("SELECT idempotency_key FROM problems", String.class));
    }

    @Test void responseLossAndStatusChangeReplayTheInitialAcceptanceWithoutResettingState() throws Exception {
        String key = UUID.randomUUID().toString();
        Response accepted = submit(key, request("GITHUB", "payment-core", false), requester);
        jdbc.update("UPDATE problems SET status='DIAGNOSING'");
        // Discard the first response and retry using a new authenticated HTTP session.
        Response retry = submit(key, request("GITHUB", "payment-core", false), login("kim_dev"));
        assertEquals(202, retry.code());
        assertEquals(accepted.body(), retry.body());
        assertEquals("RECEIVED", retry.body().path("status").asText());
        assertEquals("DIAGNOSING", jdbc.queryForObject("SELECT status FROM problems", String.class));
        assertCounts(1);
        JsonNode own = json.readTree(mvc.perform(get("/api/problems/" + accepted.body().path("id").asText()).session(requester))
            .andExpect(status().isOk()).andReturn().getResponse().getContentAsByteArray());
        assertFalse(own.has("client_request_key"));
    }

    @ParameterizedTest @ValueSource(strings = {"contents", "platform", "simulateJiraFailure"})
    void aKeyCannotBeReusedForDifferentValidInput(String field) throws Exception {
        String key = UUID.randomUUID().toString();
        ObjectNode original = request("JIRA", "PAY", false);
        assertEquals(202, submit(key, original, requester).code());
        ObjectNode changed = original.deepCopy();
        switch (field) {
            case "contents" -> changed.put("contents", "different request");
            case "platform" -> changed.put("platform", "GITHUB");
            case "simulateJiraFailure" -> changed.put("simulateJiraFailure", true);
        }
        Response conflict = submit(key, changed, requester);
        assertEquals(409, conflict.code());
        assertTrue(conflict.body().path("message").isTextual());
        assertEquals("PAY", jdbc.queryForObject("SELECT contents FROM problems", String.class));
        assertCounts(1);
    }

    @Test void normalizationAndOmittedFalseReplayTheSameRequest() throws Exception {
        String key = UUID.randomUUID().toString();
        Response first = submit(key, request("GITHUB", "  payment-core  ", false), requester);
        ObjectNode omitted = request("GITHUB", "payment-core", false);
        omitted.remove("simulateJiraFailure");
        Response retry = submit(key, omitted, requester);
        assertEquals(first.body(), retry.body());
        assertEquals(202, retry.code());
        assertCounts(1);
    }

    @Test void usersHaveIndependentKeysAndNewKeysAllowIntentionalNewRequests() throws Exception {
        String key = UUID.randomUUID().toString();
        Response first = submit(key, request("GITHUB", "payment-core", false), requester);
        Response other = submit(key, request("GITHUB", "payment-core", false), login("lee_ops"));
        Response newIntent = submit(UUID.randomUUID().toString(), request("GITHUB", "payment-core", false), requester);
        assertEquals(202, other.code());
        assertEquals(202, newIntent.code());
        assertNotEquals(first.body().path("id"), other.body().path("id"));
        assertNotEquals(first.body().path("id"), newIntent.body().path("id"));
        assertCounts(3);
    }

    @Test void legacyRequestsWithoutAKeyRemainIndependent() throws Exception {
        Response first = submit(null, request("GITHUB", "payment-core", false), requester);
        Response second = submit(null, request("GITHUB", "payment-core", false), requester);
        assertEquals(202, first.code());
        assertEquals(202, second.code());
        assertNotEquals(first.body().path("id"), second.body().path("id"));
        assertCounts(2);
    }

    @ParameterizedTest @ValueSource(strings = {"", " ", "bad key", "키", "bad/key"})
    void invalidKeysNeverCreateRequests(String key) throws Exception {
        assertEquals(400, submit(key, request("GITHUB", "payment-core", false), requester).code());
        assertCounts(0);
    }

    @Test void keyLengthAndCaseAreRespected() throws Exception {
        assertEquals(400, submit("a".repeat(129), request("GITHUB", "request", false), requester).code());
        Response accepted = submit("a".repeat(128), request("GITHUB", "request", false), requester);
        assertEquals(202, accepted.code());
        assertEquals(accepted.body(), submit("a".repeat(128), request("GITHUB", "request", false), requester).body());
        assertEquals(202, submit("UPPER", request("GITHUB", "request", false), requester).code());
        assertEquals(202, submit("upper", request("GITHUB", "request", false), requester).code());
        assertCounts(3);
    }

    @Test void invalidBodiesDoNotReserveAKeyAndAuthenticationAndCsrfStillApply() throws Exception {
        String key = UUID.randomUUID().toString();
        assertEquals(400, submit(key, request("GITHUB", "   ", false), requester).code());
        assertEquals(400, submit(key, request("SLACK", "request", true), requester).code());
        mvc.perform(post("/api/problems").with(csrf()).header("Idempotency-Key", key)
            .contentType("application/json").content(request("GITHUB", "request", false).toString()))
            .andExpect(status().isUnauthorized());
        mvc.perform(post("/api/problems").session(requester).header("Idempotency-Key", key)
            .contentType("application/json").content(request("GITHUB", "request", false).toString()))
            .andExpect(status().isForbidden());
        assertCounts(0);
        assertEquals(202, submit(key, request("GITHUB", "request", false), requester).code());
        assertCounts(1);
    }

    @Test void concurrentSameKeySubmissionsCreateOneRequest() throws Exception {
        String key = UUID.randomUUID().toString();
        List<Response> responses = concurrently(8, index -> submit(key, request("GITHUB", "payment-core", false), requester));
        for (Response response : responses) {
            assertEquals(202, response.code());
            assertEquals(responses.getFirst().body(), response.body());
        }
        assertCounts(1);
    }

    @Test void concurrentDifferentBodiesAcceptOnlyOnePayload() throws Exception {
        String key = UUID.randomUUID().toString();
        List<Response> responses = concurrently(2, index -> submit(key, request("GITHUB", "request-" + index, false), requester));
        assertEquals(List.of(202, 409), responses.stream().map(Response::code).sorted().toList());
        assertCounts(1);
    }

    @Test void outboxFailureRollsBackTheRequestAndAllowsRetryingTheKey() throws Exception {
        String key = UUID.randomUUID().toString();
        AtomicBoolean failOnce = new AtomicBoolean(true);
        doAnswer(call -> {
            if (failOnce.getAndSet(false)) throw new IllegalStateException("Injected outbox failure");
            return call.callRealMethod();
        }).when(outbox).enqueue(any());
        assertEquals(500, submit(key, request("GITHUB", "request", false), requester).code());
        assertCounts(0);
        assertEquals(202, submit(key, request("GITHUB", "request", false), requester).code());
        assertCounts(1);
    }

    @Test void aWaitingContenderCanCreateTheRequestAfterTheFirstTransactionRollsBack() throws Exception {
        String key = UUID.randomUUID().toString();
        CountDownLatch rowInserted = new CountDownLatch(1), release = new CountDownLatch(1);
        AtomicBoolean first = new AtomicBoolean(true);
        doAnswer(call -> {
            if (first.getAndSet(false)) {
                rowInserted.countDown();
                assertTrue(release.await(10, TimeUnit.SECONDS));
                throw new IllegalStateException("Injected rollback after reserving the key");
            }
            return call.callRealMethod();
        }).when(outbox).enqueue(any());
        try (var pool = Executors.newFixedThreadPool(2)) {
            Future<Response> winner = pool.submit(() -> submit(key, request("GITHUB", "request", false), requester));
            try {
                assertTrue(rowInserted.await(10, TimeUnit.SECONDS));
                Future<Response> contender = pool.submit(() -> submit(key, request("GITHUB", "request", false), requester));
                await().atMost(Duration.ofSeconds(5)).until(() -> jdbc.queryForObject("""
                    SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()
                    AND wait_event_type='Lock' AND query ILIKE '%INSERT INTO problems%'
                    """, Integer.class) > 0);
                release.countDown();
                assertEquals(500, winner.get(15, TimeUnit.SECONDS).code());
                assertEquals(202, contender.get(15, TimeUnit.SECONDS).code());
            } finally { release.countDown(); }
        }
        assertCounts(1);
    }

    @FunctionalInterface interface ConcurrentRequest { Response send(int index) throws Exception; }
    private List<Response> concurrently(int count, ConcurrentRequest request) throws Exception {
        CountDownLatch ready = new CountDownLatch(count), start = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(count)) {
            List<Future<Response>> futures = new ArrayList<>();
            for (int i = 0; i < count; i++) {
                final int index = i;
                futures.add(pool.submit(() -> {
                    ready.countDown();
                    assertTrue(start.await(10, TimeUnit.SECONDS));
                    return request.send(index);
                }));
            }
            try {
                assertTrue(ready.await(10, TimeUnit.SECONDS));
                start.countDown();
                List<Response> results = new ArrayList<>();
                for (Future<Response> future : futures) results.add(future.get(20, TimeUnit.SECONDS));
                return results;
            } finally { start.countDown(); }
        }
    }

    private MockHttpSession login(String login) throws Exception {
        return (MockHttpSession) mvc.perform(post("/api/auth/login").with(csrf()).contentType("application/json")
            .content(json.createObjectNode().put("loginId", login).put("password", "submission-password").toString()))
            .andExpect(status().isOk()).andReturn().getRequest().getSession(false);
    }

    private ObjectNode request(String platform, String contents, boolean simulate) {
        return json.createObjectNode().put("platform", platform).put("contents", contents).put("simulateJiraFailure", simulate);
    }

    private Response submit(String key, ObjectNode body, MockHttpSession session) throws Exception {
        var request = post("/api/problems").session(session).with(csrf()).contentType("application/json").content(body.toString());
        if (key != null) request.header("Idempotency-Key", key);
        var response = mvc.perform(request).andReturn().getResponse();
        return new Response(response.getStatus(), json.readTree(response.getContentAsByteArray()));
    }

    private void assertCounts(int expected) {
        assertEquals(expected, jdbc.queryForObject("SELECT count(*) FROM problems", Integer.class), "problems");
        assertEquals(expected, jdbc.queryForObject("SELECT count(*) FROM outbox WHERE routing_key='analysis'", Integer.class), "analysis outbox");
    }

    private record Response(int code, JsonNode body) {}
}
