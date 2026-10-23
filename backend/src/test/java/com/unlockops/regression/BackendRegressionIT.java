package com.unlockops.regression;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Set;
import java.util.TreeMap;
import java.util.UUID;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
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

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * Characterization tests written against the original implementation.
 * HTTP, SQL effects and real JSON queue messages are the contract: no application classes are mocked/imported.
 * Runs only with mvn verify -Pregression; Docker is required and each run gets disposable services.
 */
@SpringBootTest(properties = {
    "app.demo-enabled=true", "app.demo-password=regression-password",
    "spring.rabbitmq.listener.simple.retry.initial-interval=10ms",
    "spring.rabbitmq.listener.simple.retry.max-interval=20ms"
})
@AutoConfigureMockMvc
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class BackendRegressionIT {
    private static final String REQUESTER = "10000000-0000-0000-0000-000000000001";
    private static final String LEADER = "10000000-0000-0000-0000-000000000002";
    private static final String HEAD = "10000000-0000-0000-0000-000000000008";
    private static final String TF_RESOURCE = "20000000-0000-0000-0000-000000000001";
    private static final Set<String> PUBLIC_FIELDS = Set.of(
        "id", "requester_id", "approver_id", "platform", "contents", "status", "reason_code", "diagnosis",
        "result_type", "proposal", "resource_id", "requested_role", "decision_reason", "decided_at", "verification_ok",
        "created_at", "updated_at", "requester_name", "employee_no");

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
    }

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired RabbitTemplate rabbit;
    @Autowired ObjectMapper json;

    @AfterAll static void stopPublishingBeforeContainersStop(@Autowired ScheduledAnnotationBeanPostProcessor scheduling) {
        scheduling.destroy();
    }

    @BeforeEach
    void resetRequests() {
        // Only the disposable Testcontainers database is reset. Reference seed data remains intact.
        jdbc.execute("TRUNCATE access_execution_receipts,mock_entitlement_memberships,reclaim_scope_assignments,approval_steps,access_plan_versions,assignment_usage,retention_exceptions,reclaim_run_items,reclaim_notifications,reclaim_targets,reclaim_snapshot_items,access_assignments,grant_receipts,problem_events,outbox,inbox_events,problems RESTART IDENTITY");
        jdbc.update("UPDATE tfs SET starts_on=CURRENT_DATE-1,ends_on=NULL");
        jdbc.update("UPDATE tf_members SET active=true");
        jdbc.update("UPDATE jira_role_permissions SET can_browse=true");
        jdbc.update("UPDATE department_budgets SET remaining_monthly_amount=CASE "
            + "WHEN department_id='00000000-0000-0000-0000-000000000002'::uuid THEN 10 ELSE 150 END");
        RabbitAdmin admin = new RabbitAdmin(rabbit);
        for (String queue : new String[]{"analysis", "execution", "dead"}) admin.purgeQueue("unlockops." + queue);
    }

    @Test
    void loginRotatesSessionAndProfileContainsNoCredentials() throws Exception {
        MockHttpSession session = new MockHttpSession();
        String oldId = session.getId();
        MvcResult result = mvc.perform(post("/api/auth/login").session(session).with(csrf())
            .contentType("application/json").content("{\"loginId\":\"kim.dev@example.test\",\"password\":\"regression-password\"}"))
            .andExpect(status().isOk()).andReturn();
        assertNotEquals(oldId, session.getId());
        JsonNode profile = body(result);
        assertEquals(Set.of("id", "login_id", "employee_no", "name", "role", "job_grade", "job_family", "department"), keys(profile));
        assertEquals("REQUESTER", profile.path("role").asText());
        assertEquals("사원", profile.path("job_grade").asText());
        assertEquals(profile, body(mvc.perform(get("/api/auth/me").session(session)).andExpect(status().isOk()).andReturn()));
        mvc.perform(post("/api/auth/logout").session(session).with(csrf())).andExpect(status().isNoContent());
        assertTrue(session.isInvalid());
        mvc.perform(post("/api/auth/login").with(csrf()).contentType("application/json")
            .content("{\"loginId\":\"kim_dev\",\"password\":\"wrong-password\"}"))
            .andExpect(status().isUnauthorized()).andExpect(jsonPath("$.message").exists());
    }

    @Test
    void csrfAndAnonymousAccessRemainProtected() throws Exception {
        mvc.perform(get("/api/health")).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("UP"));
        mvc.perform(get("/api/auth/csrf")).andExpect(status().isOk())
            .andExpect(jsonPath("$.token").isString()).andExpect(jsonPath("$.headerName").isString());
        mvc.perform(get("/api/problems")).andExpect(status().isUnauthorized());
        MockHttpSession session = login("kim_dev");
        mvc.perform(post("/api/problems").session(session).contentType("application/json")
            .content("{\"platform\":\"GITHUB\",\"contents\":\"요청\"}"))
            .andExpect(status().isForbidden());
        mvc.perform(get("/api/problems").session(session)).andExpect(status().isForbidden());
        mvc.perform(get("/api/approvals/summary").session(session)).andExpect(status().isForbidden());
    }

    @ParameterizedTest
    @CsvSource({"GITHUB,payment-core", "JIRA,PAY", "SLACK,#proj-payment", "NOTION,pay-wiki"})
    void creationPersistsAuthenticatedRequesterAndPublishesOriginalJobContract(String platform, String contents) throws Exception {
        String id = create(login("kim_dev"), platform, "  " + contents + "  ", false);
        JsonNode job = receive("analysis");
        assertEquals(Set.of("event_id", "job_type", "problem_id", "requester_id", "platform", "contents", "idempotency_key", "plan_hash"), keys(job));
        assertEquals("ANALYZE", job.path("job_type").asText());
        assertEquals(id, job.path("problem_id").asText());
        assertEquals(REQUESTER, job.path("requester_id").asText());
        assertEquals(platform, job.path("platform").asText());
        assertEquals(contents, job.path("contents").asText());
        assertTrue(job.path("plan_hash").isNull());
        assertTrue(job.path("idempotency_key").isNull());
        assertEquals(HEAD, field(id, "approver_id"));
        await().atMost(Duration.ofSeconds(5)).untilAsserted(() -> assertNotNull(
            jdbc.queryForObject("SELECT published_at FROM outbox WHERE event_id=?", Object.class, UUID.fromString(job.path("event_id").asText()))));
    }

    @ParameterizedTest
    @CsvSource({"UNKNOWN,request,false", "GITHUB,'   ',false", "GITHUB,request,true", "SLACK,request,true"})
    void invalidCreationWritesNeitherProblemNorOutbox(String platform, String contents, boolean simulate) throws Exception {
        ObjectNode request = json.createObjectNode().put("platform", platform).put("contents", contents).put("simulateJiraFailure", simulate);
        mvc.perform(post("/api/problems").session(login("kim_dev")).with(csrf()).contentType("application/json").content(request.toString()))
            .andExpect(status().isBadRequest());
        assertEquals(0, count("problems"));
        assertEquals(0, count("outbox"));
    }

    @Test
    void jiraDemoFailureFlagIsStoredButNotAddedToTheWorkerEnvelope() throws Exception {
        String id = create(login("kim_dev"), "JIRA", "PAY", true);
        assertEquals(Boolean.TRUE, jdbc.queryForObject("SELECT simulate_jira_failure FROM problems WHERE id=?", Boolean.class, UUID.fromString(id)));
        assertFalse(receive("analysis").has("simulate_jira_failure"));
    }

    @Test
    void analysisReassignsToTfLeaderAndPublicViewsNeverExposeInternalFields() throws Exception {
        MockHttpSession requester = login("kim_dev");
        String id = waiting(requester);
        assertEquals(LEADER, field(id, "approver_id"));
        JsonNode own = detail(requester, id);
        assertEquals(StreamSupport.stream(PUBLIC_FIELDS.spliterator(), false).collect(Collectors.toSet()),
            keysWithoutEvents(own));
        assertEquals("WAITING_APPROVAL", own.path("status").asText());
        for (JsonNode event : own.path("events")) assertEquals(Set.of("message"), keys(event.path("payload")));
        JsonNode mine = body(mvc.perform(get("/api/problems?mine=true").session(requester)).andExpect(status().isOk()).andReturn());
        assertEquals(PUBLIC_FIELDS, keys(mine.get(0)));
        JsonNode assigned = detail(login("park_lead"), id);
        assertTrue(assigned.path("evidence").isArray());
        assertEquals("payment-core", assigned.path("plan").path("resource_key").asText());
        assertEquals(planHash(plan(id)), assigned.path("plan_hash").asText());
        assertTrue(assigned.path("events").get(0).path("payload").path("result").has("evidence"));
        mvc.perform(get("/api/problems/" + id).session(login("yoon_head"))).andExpect(status().isForbidden());
        mvc.perform(get("/api/problems/" + id).session(login("lee_ops"))).andExpect(status().isForbidden());
        assertEquals(id, detail(login("song_ops"), id).path("id").asText());
        mvc.perform(get("/api/problems/" + UUID.randomUUID()).session(requester)).andExpect(status().isNotFound());
    }

    @Test
    void approvalStoresOneExecutionAndRejectsWrongActorHashAndReplay() throws Exception {
        String id = waiting(login("kim_dev"));
        String hash = field(id, "plan_hash");
        decide(login("song_ops"), id, true, hash, "", 403);
        decide(login("park_lead"), id, true, "0".repeat(64), "", 409);
        assertEquals(0, routingCount("execution"));
        MockHttpSession approver = login("park_lead");
        decide(approver, id, true, hash, "  업무상 필요  ", 200);
        JsonNode execution = receive("execution");
        assertEquals("EXECUTE", execution.path("job_type").asText());
        assertEquals(hash, execution.path("plan_hash").asText());
        assertEquals(id + ":" + hash, execution.path("idempotency_key").asText());
        assertEquals(hash, field(id, "approved_plan_hash"));
        assertEquals(LEADER, field(id, "decided_by"));
        assertEquals("업무상 필요", field(id, "decision_reason"));
        assertEquals("HUMAN", field(id, "decision_source"));
        assertEquals("HUMAN_APPROVED", field(id, "reason_code"));
        decide(approver, id, true, hash, "", 409);
        assertEquals(1, routingCount("execution"));
    }

    @Test
    void failedExecutionEnqueueRollsBackApprovalAndStateTransition() throws Exception {
        String id = waiting(login("kim_dev"));
        MockHttpSession approver = login("park_lead");
        String hash = field(id, "plan_hash");
        jdbc.execute("ALTER TABLE outbox ADD CONSTRAINT test_block_execution CHECK (routing_key <> 'execution')");
        try {
            decide(approver, id, true, hash, "필요 확인", 500);
            assertEquals("WAITING_APPROVAL", field(id, "status"));
            assertNull(field(id, "decided_at"));
            assertNull(field(id, "approved_plan_hash"));
            assertNull(field(id, "idempotency_key"));
            assertEquals(0, routingCount("execution"));
            assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM problem_events WHERE problem_id=? AND kind='HUMAN_DECISION'",
                Integer.class, UUID.fromString(id)));
        } finally {
            jdbc.execute("ALTER TABLE outbox DROP CONSTRAINT test_block_execution");
        }
        decide(approver, id, true, hash, "재시도", 200);
        assertEquals("EXECUTING", field(id, "status"));
        assertEquals(1, routingCount("execution"));
    }

    @Test
    void selfApprovalIsForbiddenEvenIfTheDatabaseAssignmentPointsToRequester() throws Exception {
        String id = waiting(login("kim_dev"));
        jdbc.update("UPDATE problems SET requester_id=? WHERE id=?", UUID.fromString(LEADER), UUID.fromString(id));
        jdbc.update("UPDATE problems SET approver_id=requester_id WHERE id=?", UUID.fromString(id));
        decide(login("park_lead"), id, true, field(id, "plan_hash"), "", 403);
        assertEquals(0, routingCount("execution"));
        JsonNode own = detail(login("park_lead"), id);
        assertFalse(own.has("plan_hash"));
        assertEquals(PUBLIC_FIELDS, keysWithoutEvents(own));
    }

    @Test
    void rejectionRequiresReasonAndDoesNotEnqueueExecution() throws Exception {
        String id = waiting(login("kim_dev"));
        MockHttpSession approver = login("park_lead");
        String hash = field(id, "plan_hash");
        decide(approver, id, false, hash, "   ", 400);
        decide(approver, id, false, hash, "  업무 대상 아님  ", 200);
        assertEquals("REJECTED", field(id, "status"));
        assertEquals("HUMAN_REJECTED", field(id, "reason_code"));
        assertEquals("업무 대상 아님", field(id, "decision_reason"));
        assertNull(field(id, "idempotency_key"));
        assertNull(field(id, "approved_plan_hash"));
        assertEquals(0, routingCount("execution"));
    }

    @Test
    void approvalRevalidatesMembershipAndPlanDigestRatherThanTrustingStoredHash() throws Exception {
        String id = waiting(login("kim_dev"));
        String hash = field(id, "plan_hash");
        MockHttpSession approver = login("park_lead");
        jdbc.update("UPDATE tf_members SET active=false WHERE user_id=?", UUID.fromString(REQUESTER));
        decide(approver, id, true, hash, "", 409);
        jdbc.update("UPDATE tf_members SET active=true WHERE user_id=?", UUID.fromString(REQUESTER));
        jdbc.update("UPDATE problems SET plan=jsonb_set(plan,'{requested_role}','\"Read\"') WHERE id=?", UUID.fromString(id));
        decide(approver, id, true, hash, "", 409);
        assertEquals("WAITING_APPROVAL", field(id, "status"));
        assertEquals(0, routingCount("execution"));
        assertNull(field(id, "decided_by"));
    }

    @Test
    void duplicateAndLateAnalysisCannotOverwriteApprovedPlan() throws Exception {
        String id = waiting(login("kim_dev"));
        String hash = field(id, "plan_hash");
        decide(login("park_lead"), id, true, hash, "승인", 200);
        ObjectNode late = envelope(id, "ANALYZE", "ANALYZED", result("REJECTED", "LATE_RESULT", null));
        send(late);
        awaitInbox(late);
        send(late);
        // A different following message provides a processing barrier after the duplicate delivery.
        ObjectNode barrier = envelope(id, "ANALYZE", "PROGRESS", null);
        send(barrier);
        awaitInbox(barrier);
        assertEquals("EXECUTING", field(id, "status"));
        assertEquals(hash, field(id, "approved_plan_hash"));
        assertEquals("HUMAN_APPROVED", field(id, "reason_code"));
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM problem_events WHERE event_id=?", Integer.class,
            UUID.fromString(late.path("event_id").asText())));
    }

    @Test
    void progressAndWorkerFailureFollowExistingStateTransitions() throws Exception {
        String id = create(login("kim_dev"), "GITHUB", "payment-core", false);
        ObjectNode progress = envelope(id, "ANALYZE", "PROGRESS", null).put("node", "collect_evidence");
        send(progress);
        awaitInbox(progress);
        assertEquals("DIAGNOSING", field(id, "status"));
        ObjectNode failed = envelope(id, "ANALYZE", "FAILED", null).put("error_code", "CHECKPOINT_MISSING");
        send(failed);
        awaitInbox(failed);
        assertEquals("FAILED", field(id, "status"));
        assertEquals("CHECKPOINT_MISSING", field(id, "reason_code"));
        ObjectNode stale = envelope(id, "ANALYZE", "ANALYZED", result("WAITING_APPROVAL", "ELIGIBLE", plan(id)));
        send(stale);
        awaitInbox(stale);
        assertEquals("FAILED", field(id, "status"));
    }

    @Test
    void guidanceCompletionIsConsistentAcrossQueueDatabaseAndHttp() throws Exception {
        MockHttpSession requester = login("kim_dev");
        String id = create(requester, "GITHUB", "Read와 Write 차이를 알려주세요", false);
        ObjectNode outcome = result("DONE", "RAG_GUIDANCE", null).put("result_type", "GUIDANCE");
        ObjectNode event = envelope(id, "ANALYZE", "ANALYZED", outcome);
        send(event);
        awaitInbox(event);
        assertEquals("DONE", field(id, "status"));
        assertEquals("GUIDANCE", field(id, "result_type"));
        assertNull(field(id, "verification_ok"));
        assertEquals(0, routingCount("execution"));
        JsonNode response = detail(requester, id);
        assertEquals("GUIDANCE", response.path("result_type").asText());
        assertTrue(response.path("events").toString().contains("안내가 완료됐어요"));
        assertEquals(0, count("grant_receipts"));
    }

    @Test
    void legacyGuidanceCompletesWithoutMutatingTheAuditEnvelope() throws Exception {
        String id = create(login("kim_dev"), "GITHUB", "권한 안내", false);
        ObjectNode event = envelope(id, "ANALYZE", "ANALYZED", result("MANUAL_REVIEW", "RAG_GUIDANCE", null));
        send(event);
        awaitInbox(event);
        assertEquals("DONE", field(id, "status"));
        assertEquals("GUIDANCE", field(id, "result_type"));
        JsonNode audit = json.readTree(jdbc.queryForObject("SELECT payload::text FROM problem_events WHERE event_id=?",
            String.class, UUID.fromString(event.path("event_id").asText())));
        assertEquals(event, audit);
    }

    @Test
    void legacyBudgetResultIsNormalizedWhileOriginalAuditPayloadIsPreserved() throws Exception {
        String id = create(login("kim_dev"), "GITHUB", "payment-core", false);
        ObjectNode legacy = envelope(id, "ANALYZE", "ANALYZED", result("ON_HOLD", "INSUFFICIENT_BUDGET", null));
        send(legacy);
        awaitInbox(legacy);
        assertEquals("REJECTED", field(id, "status"));
        assertEquals("BUDGET_INSUFFICIENT", field(id, "reason_code"));
        JsonNode audit = json.readTree(jdbc.queryForObject("SELECT payload::text FROM problem_events WHERE event_id=?",
            String.class, UUID.fromString(legacy.path("event_id").asText())));
        assertEquals(legacy, audit);
    }

    @ParameterizedTest
    @CsvSource({"missing_evidence", "extra_plan_field", "wrong_requester", "wrong_resource", "excess_role", "inactive_tf"})
    void invalidPlansFallBackToManualReviewAndClearExecutionFields(String invalid) throws Exception {
        String id = create(login("kim_dev"), "GITHUB", "payment-core", false);
        ObjectNode plan = plan(id);
        ObjectNode outcome = result("WAITING_APPROVAL", "ELIGIBLE", plan);
        switch (invalid) {
            case "missing_evidence" -> outcome.putArray("evidence");
            case "extra_plan_field" -> plan.put("unexpected", "private");
            case "wrong_requester" -> plan.put("requester_id", LEADER);
            case "wrong_resource" -> plan.put("resource_key", "other-resource");
            case "excess_role" -> plan.put("requested_role", "Admin");
            case "inactive_tf" -> jdbc.update("UPDATE tf_members SET active=false WHERE user_id=?", UUID.fromString(REQUESTER));
            default -> fail("Unknown test case");
        }
        ObjectNode event = envelope(id, "ANALYZE", "ANALYZED", outcome);
        send(event);
        awaitInbox(event);
        assertEquals("MANUAL_REVIEW", field(id, "status"));
        assertEquals("SERVER_PLAN_VALIDATION", field(id, "reason_code"));
        for (String name : new String[]{"resource_id", "requested_role", "plan", "plan_hash"}) assertNull(field(id, name), name);
        assertEquals(0, routingCount("execution"));
    }

    @ParameterizedTest
    @CsvSource({
        "kim_dev,GITHUB,internal-tools,Write,MANUAL_REVIEW",
        "oh_dev,GITHUB,internal-tools,Write,WAITING_APPROVAL",
        "lee_ops,GITHUB,docs-site,Read,WAITING_APPROVAL",
        "lee_ops,GITHUB,docs-site,Write,MANUAL_REVIEW",
        "oh_dev,GITHUB,payment-core,Write,MANUAL_REVIEW",
        "kim_dev,NOTION,dev-wiki,Can view,WAITING_APPROVAL",
        "lee_ops,NOTION,dev-wiki,Can view,MANUAL_REVIEW",
        "kim_dev,NOTION,hr-confidential,Can view,MANUAL_REVIEW",
        "jung_data,GITHUB,copilot-seat,Seat,MANUAL_REVIEW",
        "choi_copilot,GITHUB,copilot-seat,Seat,MANUAL_REVIEW",
        "kim_dev,GITHUB,copilot-seat,Seat,WAITING_APPROVAL",
        "kim_dev,JIRA,PAY,Developer,WAITING_APPROVAL",
        "kim_dev,SLACK,#proj-payment,Member,WAITING_APPROVAL",
        "kim_dev,NOTION,pay-wiki,Can view,WAITING_APPROVAL"
    })
    void grantPolicyPreservesJobGradeFamilyMembershipDepartmentBudgetAndSeatRules(
            String login, String platform, String resource, String role, String expected) throws Exception {
        String id = create(login(login), platform, resource, false);
        String resourceId = jdbc.queryForObject("SELECT id::text FROM resources WHERE external_id=?", String.class, resource);
        ObjectNode plan = plan(id).put("requester_id", field(id, "requester_id")).put("platform", platform)
            .put("resource_id", resourceId).put("resource_key", resource).put("requested_role", role);
        ObjectNode event = envelope(id, "ANALYZE", "ANALYZED", result("WAITING_APPROVAL", "ELIGIBLE", plan));
        send(event);
        awaitInbox(event);
        assertEquals(expected, field(id, "status"));
    }

    @Test
    void jiraRoleWithoutBrowsePermissionCannotBecomeAnApprovablePlan() throws Exception {
        String id = create(login("kim_dev"), "JIRA", "PAY", false);
        jdbc.update("UPDATE jira_role_permissions SET can_browse=false WHERE saas_role='Developer'");
        ObjectNode plan = plan(id).put("platform", "JIRA").put("resource_key", "PAY")
            .put("resource_id", "20000000-0000-0000-0000-000000000005").put("requested_role", "Developer");
        ObjectNode event = envelope(id, "ANALYZE", "ANALYZED", result("WAITING_APPROVAL", "ELIGIBLE", plan));
        send(event);
        awaitInbox(event);
        assertEquals("MANUAL_REVIEW", field(id, "status"));
    }

    @Test
    void executionCompletionRequiresVerificationAndReceiptAndPreservesHumanDecision() throws Exception {
        String id = waiting(login("kim_dev"));
        String hash = field(id, "plan_hash");
        decide(login("park_lead"), id, true, hash, "승認", 200);
        jdbc.update("INSERT INTO grant_receipts(idempotency_key,problem_id,result) VALUES (?,?,?::jsonb)",
            id + ":" + hash, UUID.fromString(id), "{}");
        ObjectNode done = result("DONE", "GRANTED", null).put("verification_ok", true);
        ObjectNode event = envelope(id, "EXECUTE", "EXECUTED", done);
        send(event);
        awaitInbox(event);
        assertEquals("DONE", field(id, "status"));
        assertEquals("HUMAN", field(id, "decision_source"));
        assertEquals(LEADER, field(id, "decided_by"));
        assertEquals(hash, field(id, "approved_plan_hash"));
        assertEquals("Write", field(id, "requested_role"));
        assertEquals(hash, field(id, "plan_hash"));
        assertEquals(LEADER, field(id, "approver_id"));
    }

    @ParameterizedTest
    @CsvSource({"false", "true"})
    void invalidCompletionRollsBackInboxAuditAndProblemUpdate(boolean verified) throws Exception {
        String id = waiting(login("kim_dev"));
        decide(login("park_lead"), id, true, field(id, "plan_hash"), "", 200);
        ObjectNode invalid = envelope(id, "EXECUTE", "EXECUTED", result("DONE", "GRANTED", null).put("verification_ok", verified));
        send(invalid);
        JsonNode dead = receive("dead");
        assertEquals(invalid, dead);
        assertEquals("EXECUTING", field(id, "status"));
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM inbox_events WHERE event_id=?", Integer.class,
            UUID.fromString(invalid.path("event_id").asText())));
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM problem_events WHERE event_id=?", Integer.class,
            UUID.fromString(invalid.path("event_id").asText())));
    }

    @Test
    void analysisCannotReturnAnExecutionOnlyState() throws Exception {
        String id = create(login("kim_dev"), "GITHUB", "payment-core", false);
        ObjectNode invalid = envelope(id, "ANALYZE", "ANALYZED", result("EXECUTING", "INVALID", null));
        send(invalid);
        assertEquals(invalid, receive("dead"));
        assertEquals("RECEIVED", field(id, "status"));
        assertEquals(0, count("inbox_events"));
        assertEquals(0, count("problem_events"));
    }

    @Test
    void summaryUsesAssignedApproverKstCreationWeekAndOverlappingOutcomeCounts() throws Exception {
        String[] ids = new String[6];
        for (int i = 0; i < ids.length; i++) ids[i] = create(login("kim_dev"), "GITHUB", "request " + i, false);
        jdbc.update("UPDATE problems SET approver_id=?", UUID.fromString(LEADER));
        String week = "date_trunc('week',CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul'";
        jdbc.update("UPDATE problems SET created_at=(" + week + ") WHERE id=?", UUID.fromString(ids[0]));
        jdbc.update("UPDATE problems SET created_at=(" + week + ")+INTERVAL '7 days'-INTERVAL '1 microsecond' WHERE id=?", UUID.fromString(ids[1]));
        jdbc.update("UPDATE problems SET created_at=(" + week + ")-INTERVAL '1 microsecond' WHERE id=?", UUID.fromString(ids[2]));
        jdbc.update("UPDATE problems SET created_at=(" + week + ")+INTERVAL '7 days' WHERE id=?", UUID.fromString(ids[3]));
        jdbc.update("UPDATE problems SET status='FAILED',decision_source='HUMAN',approved_plan_hash=?,decided_by=? WHERE id=?",
            "a".repeat(64), UUID.fromString(LEADER), UUID.fromString(ids[0]));
        jdbc.update("UPDATE problems SET status='REJECTED' WHERE id=?", UUID.fromString(ids[1]));
        jdbc.update("UPDATE problems SET requester_id='10000000-0000-0000-0000-000000000003' WHERE id=?", UUID.fromString(ids[4]));
        jdbc.update("UPDATE problems SET approver_id=? WHERE id=?", UUID.fromString(HEAD), UUID.fromString(ids[5]));
        JsonNode summary = summary(login("park_lead"));
        assertEquals(Set.of("department", "memberCount", "weekRequests", "approved", "rejected", "failed"), keys(summary));
        assertEquals(3, summary.path("weekRequests").asInt());
        assertEquals(1, summary.path("approved").asInt());
        assertEquals(1, summary.path("rejected").asInt());
        assertEquals(1, summary.path("failed").asInt());
        assertEquals(1, summary(login("yoon_head")).path("weekRequests").asInt());
        JsonNode ops = summary(login("song_ops"));
        assertEquals(0, ops.path("weekRequests").asInt());
        assertEquals("운영팀", ops.path("department").asText());
        assertTrue(ops.path("memberCount").asInt() > 0);
        JsonNode all = body(mvc.perform(get("/api/problems").session(login("song_ops"))).andExpect(status().isOk()).andReturn());
        assertEquals(6, all.size());
    }

    @Test
    void pythonCanonicalPlanDigestIsStable() throws Exception {
        assertEquals("adf632fef5f9ee0c7ad0b1868230544f4cc71e7f20cde20903f5d251c1aaf1d4",
            planHash(plan("40000000-0000-0000-0000-000000000001")));
    }

    private MockHttpSession login(String login) throws Exception {
        return (MockHttpSession) mvc.perform(post("/api/auth/login").with(csrf()).contentType("application/json")
            .content(json.createObjectNode().put("loginId", login).put("password", "regression-password").toString()))
            .andExpect(status().isOk()).andReturn().getRequest().getSession(false);
    }

    private String create(MockHttpSession session, String platform, String contents, boolean simulate) throws Exception {
        ObjectNode request = json.createObjectNode().put("platform", platform).put("contents", contents)
            .put("simulateJiraFailure", simulate).put("requester_id", LEADER);
        JsonNode response = body(mvc.perform(post("/api/problems").session(session).with(csrf()).contentType("application/json")
            .content(request.toString())).andExpect(status().isAccepted()).andReturn());
        assertEquals(Set.of("id", "status"), keys(response));
        assertEquals("RECEIVED", response.path("status").asText());
        return response.path("id").asText();
    }

    private String waiting(MockHttpSession session) throws Exception {
        String id = create(session, "GITHUB", "payment-core push가 안 됩니다", false);
        // Use the authenticated requester recorded by the server, including approver-own-request coverage.
        ObjectNode candidate = plan(id).put("requester_id", field(id, "requester_id"));
        ObjectNode event = envelope(id, "ANALYZE", "ANALYZED", result("WAITING_APPROVAL", "ELIGIBLE", candidate));
        send(event);
        awaitInbox(event);
        assertEquals("WAITING_APPROVAL", field(id, "status"));
        return id;
    }

    private void decide(MockHttpSession session, String id, boolean approved, String hash, String reason, int status) throws Exception {
        ObjectNode decision = json.createObjectNode().put("approved", approved).put("expectedPlanHash", hash).put("reason", reason);
        mvc.perform(post("/api/problems/" + id + "/decision").session(session).with(csrf()).contentType("application/json")
            .content(decision.toString())).andExpect(status().is(status));
    }

    private JsonNode detail(MockHttpSession session, String id) throws Exception {
        return body(mvc.perform(get("/api/problems/" + id).session(session)).andExpect(status().isOk()).andReturn());
    }

    private JsonNode summary(MockHttpSession session) throws Exception {
        return body(mvc.perform(get("/api/approvals/summary").session(session)).andExpect(status().isOk()).andReturn());
    }

    private ObjectNode plan(String id) {
        return json.createObjectNode().put("problem_id", id).put("requester_id", REQUESTER).put("platform", "GITHUB")
            .put("resource_id", TF_RESOURCE).put("resource_key", "payment-core").put("requested_role", "Write");
    }

    private ObjectNode result(String status, String code, ObjectNode plan) {
        ObjectNode result = json.createObjectNode().put("status", status).put("reasonCode", code)
            .put("summary", "분석 결과").put("diagnosis", "현재 권한 부족").put("proposal", "Write 권한 제안")
            .put("nextAction", "승인 검토").put("agent_mode", "demo");
        result.putArray("evidence").addObject().put("source", "private-policy").put("article", "TF-1");
        result.set("plan", plan);
        return result;
    }

    private ObjectNode envelope(String id, String job, String kind, ObjectNode result) {
        ObjectNode event = json.createObjectNode().put("event_id", UUID.randomUUID().toString()).put("problem_id", id)
            .put("job_type", job).put("kind", kind);
        if (result != null) event.set("result", result);
        return event;
    }

    private void send(ObjectNode event) {
        MessageProperties properties = new MessageProperties();
        properties.setContentType("application/json");
        rabbit.send("unlockops", "results", new Message(event.toString().getBytes(StandardCharsets.UTF_8), properties));
    }

    private void awaitInbox(ObjectNode event) {
        await().atMost(Duration.ofSeconds(10)).untilAsserted(() -> assertEquals(1,
            jdbc.queryForObject("SELECT count(*) FROM inbox_events WHERE event_id=?", Integer.class,
                UUID.fromString(event.path("event_id").asText()))));
    }

    private JsonNode receive(String queue) throws Exception {
        Message message = rabbit.receive("unlockops." + queue, 10000);
        assertNotNull(message, "Expected queue message on " + queue);
        return json.readTree(message.getBody());
    }

    private String field(String id, String column) {
        // Column names come only from literal test cases.
        return jdbc.queryForObject("SELECT " + column + "::text FROM problems WHERE id=?", String.class, UUID.fromString(id));
    }

    private int count(String table) { return jdbc.queryForObject("SELECT count(*) FROM " + table, Integer.class); }
    private int routingCount(String routing) {
        return jdbc.queryForObject("SELECT count(*) FROM outbox WHERE routing_key=?", Integer.class, routing);
    }
    private JsonNode body(MvcResult result) throws Exception { return json.readTree(result.getResponse().getContentAsByteArray()); }
    private Set<String> keys(JsonNode node) {
        return StreamSupport.stream(((Iterable<String>) node::fieldNames).spliterator(), false).collect(Collectors.toSet());
    }
    private Set<String> keysWithoutEvents(JsonNode node) {
        Set<String> result = keys(node);
        result.remove("events");
        return result;
    }
    private String planHash(ObjectNode plan) throws Exception {
        TreeMap<String, Object> sorted = new TreeMap<>();
        plan.fields().forEachRemaining(field -> sorted.put(field.getKey(), field.getValue().asText()));
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(json.writeValueAsBytes(sorted)));
    }
}
