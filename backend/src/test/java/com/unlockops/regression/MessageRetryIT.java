package com.unlockops.regression;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.ScheduledAnnotationBeanPostProcessor;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.*;

/** Real PostgreSQL errors and broker deliveries; fault injection exists only in this disposable test database. */
@SpringBootTest(properties = {
    "app.demo-enabled=true", "app.demo-password=regression-password",
    "spring.rabbitmq.listener.simple.retry.initial-interval=10ms",
    "spring.rabbitmq.listener.simple.retry.max-interval=20ms"
})
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class MessageRetryIT {
    static final UUID REQUESTER = UUID.fromString("10000000-0000-0000-0000-000000000001");
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

    @Autowired JdbcTemplate jdbc;
    @Autowired RabbitTemplate rabbit;
    @Autowired ObjectMapper json;
    UUID problemId;

    @BeforeAll static void installProbe(@Autowired JdbcTemplate jdbc) {
        jdbc.execute("CREATE SEQUENCE retry_attempts");
        jdbc.execute("CREATE TABLE retry_fault(event_id UUID PRIMARY KEY, failures INTEGER, sql_state TEXT)");
        // Sequences survive transaction rollback, so the probe counts actual attempts rather than committed rows.
        jdbc.execute("""
            CREATE FUNCTION probe_result_attempt() RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE fault retry_fault%ROWTYPE; attempt BIGINT;
            BEGIN
                SELECT * INTO fault FROM retry_fault WHERE event_id=NEW.event_id;
                IF FOUND THEN
                    attempt := nextval('retry_attempts');
                    IF attempt <= fault.failures THEN
                        RAISE EXCEPTION USING ERRCODE=fault.sql_state, MESSAGE='retry regression fault';
                    END IF;
                END IF;
                RETURN NEW;
            END $$
            """);
        jdbc.execute("CREATE TRIGGER probe_result_attempt BEFORE INSERT ON inbox_events FOR EACH ROW EXECUTE FUNCTION probe_result_attempt()");
    }

    @BeforeEach void reset() {
        jdbc.execute("TRUNCATE grant_receipts,problem_events,outbox,inbox_events,problems,retry_fault");
        jdbc.execute("ALTER SEQUENCE retry_attempts RESTART WITH 1");
        new RabbitAdmin(rabbit).purgeQueue("unlockops.dead");
        problemId = UUID.randomUUID();
        jdbc.update("INSERT INTO problems(id,requester_id,platform,contents,thread_id) VALUES (?,?,?,?,?)",
            problemId, REQUESTER, "GITHUB", "retry regression", problemId.toString());
    }

    @AfterAll static void stopScheduler(@Autowired ScheduledAnnotationBeanPostProcessor scheduling) { scheduling.destroy(); }

    @Test void transientFailureRecoversOnSameEventAndCommitsOnce() throws Exception {
        String key = problemId + ":retry-regression";
        jdbc.update("UPDATE problems SET status='EXECUTING',idempotency_key=? WHERE id=?", key, problemId);
        jdbc.update("INSERT INTO grant_receipts(idempotency_key,problem_id,result) VALUES (?,?,?::jsonb)", key, problemId, "{}");
        ObjectNode event = event("EXECUTE", "EXECUTED");
        event.putObject("result").put("status", "DONE").put("reasonCode", "VERIFIED")
            .put("proposal", "반영을 확인했습니다.").put("verification_ok", true);
        fault(event, 1, "40001");
        send(event);
        await().atMost(Duration.ofSeconds(10)).untilAsserted(() -> assertEquals("DONE", status()));
        assertEquals(2, attempts());
        assertAppliedOnce(event);
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM grant_receipts WHERE problem_id=?", Integer.class, problemId));
        assertNull(rabbit.receive("unlockops.dead"));
        capture("01-transient-recovered", event, "40001: serialization_failure (first attempt only)", 0);
        send(event);
        ObjectNode barrier = event("EXECUTE", "PROGRESS");
        send(barrier);
        await().atMost(Duration.ofSeconds(10)).untilAsserted(() -> assertEquals(1, inboxCount(barrier)));
        assertAppliedOnce(event);
        assertEquals("DONE", status());
    }

    @Test void persistentTransientFailureRetriesThreeTimesThenDeadLettersWithoutPartialWrites() throws Exception {
        ObjectNode event = event("ANALYZE", "PROGRESS");
        fault(event, 99, "40001");
        send(event);
        assertDead(event, 3, "RECEIVED", "03-transient-exhausted");
    }

    @Test void permanentDatabaseConstraintFailureDoesNotRetry() throws Exception {
        ObjectNode event = event("ANALYZE", "PROGRESS");
        fault(event, 99, "23514");
        send(event);
        assertDead(event, 1, "RECEIVED", null);
    }

    @Test void unknownDatabaseFailureIsQuarantinedWithoutGuessingItIsTransient() throws Exception {
        ObjectNode event = event("ANALYZE", "PROGRESS");
        fault(event, 99, "P0001");
        send(event);
        assertDead(event, 1, "RECEIVED", null);
    }

    @Test void invalidCompletionIsRejectedOnceAndRollsBackInboxAndAudit() throws Exception {
        jdbc.update("UPDATE problems SET status='EXECUTING' WHERE id=?", problemId);
        ObjectNode event = event("EXECUTE", "EXECUTED");
        event.putObject("result").put("status", "DONE").put("reasonCode", "INVALID")
            .put("proposal", "unverified").put("verification_ok", false);
        fault(event, 0, "40001");
        send(event);
        assertDead(event, 1, "EXECUTING", "02-permanent-rejected");
    }

    @Test void malformedEnvelopeIsDeadLetteredWithoutDatabaseWrites() throws Exception {
        ObjectNode event = event("ANALYZE", "PROGRESS");
        event.remove("job_type");
        fault(event, 0, "40001");
        send(event);
        assertDead(event, 0, "RECEIVED", null);
    }

    ObjectNode event(String job, String kind) {
        return json.createObjectNode().put("event_id", UUID.randomUUID().toString())
            .put("problem_id", problemId.toString()).put("job_type", job).put("kind", kind);
    }

    void fault(ObjectNode event, int failures, String sqlState) {
        jdbc.update("INSERT INTO retry_fault VALUES (?,?,?)", eventId(event), failures, sqlState);
    }

    void send(ObjectNode event) {
        MessageProperties properties = new MessageProperties();
        properties.setContentType("application/json");
        // Worker results do not set AMQP message_id; the consumer must also support this actual envelope.
        rabbit.send("unlockops", "results", new Message(event.toString().getBytes(StandardCharsets.UTF_8), properties));
    }

    void assertDead(ObjectNode event, int expectedAttempts, String expectedStatus, String scenario) throws Exception {
        await().atMost(Duration.ofSeconds(10)).untilAsserted(() -> assertEquals(1,
            new RabbitAdmin(rabbit).getQueueInfo("unlockops.dead").getMessageCount()));
        assertEquals(expectedAttempts, attempts());
        assertEquals(expectedStatus, status());
        assertEquals(0, inboxCount(event));
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM problem_events WHERE problem_id=?", Integer.class, problemId));
        if (scenario != null) capture(scenario, event,
            scenario.startsWith("02") ? "INVALID_RESULT" : "40001: serialization_failure (persistent)", 1);
        Message dead = rabbit.receive("unlockops.dead", 10000);
        assertNotNull(dead);
        assertEquals(event, json.readTree(dead.getBody()));
    }

    void capture(String scenario, ObjectNode event, String fault, int deadReady) throws Exception {
        ObjectNode evidence = json.createObjectNode().put("scenario", scenario).put("problemId", problemId.toString())
            .put("eventId", event.path("event_id").asText()).put("fault", fault).put("deadReady", deadReady)
            .put("attempts", attempts()).put("status", status()).put("inboxEvents", inboxCount(event))
            .put("auditEvents", jdbc.queryForObject("SELECT count(*) FROM problem_events WHERE event_id=?", Integer.class, eventId(event)))
            .put("receipts", jdbc.queryForObject("SELECT count(*) FROM grant_receipts WHERE problem_id=?", Integer.class, problemId));
        RetryEvidence.capture(evidence, BROKER, json);
    }

    void assertAppliedOnce(ObjectNode event) {
        assertEquals(1, inboxCount(event));
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM problem_events WHERE event_id=?", Integer.class, eventId(event)));
    }

    int attempts() { return jdbc.queryForObject("SELECT CASE WHEN is_called THEN last_value ELSE 0 END FROM retry_attempts", Integer.class); }
    int inboxCount(ObjectNode event) { return jdbc.queryForObject("SELECT count(*) FROM inbox_events WHERE event_id=?", Integer.class, eventId(event)); }
    UUID eventId(ObjectNode event) { return UUID.fromString(event.path("event_id").asText()); }
    String status() { return jdbc.queryForObject("SELECT status FROM problems WHERE id=?", String.class, problemId); }
}
