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
@org.junit.jupiter.api.TestMethodOrder(org.junit.jupiter.api.MethodOrderer.OrderAnnotation.class)
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
    @Autowired com.unlockops.messaging.workflow.WorkflowResults results;

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

    @Test @org.junit.jupiter.api.Order(1)
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

    private JsonNode execution(MockHttpSession session) throws Exception {
        return body(mvc.perform(get("/api/reclaim/targets/" + TARGET + "/execution").session(session))
            .andExpect(status().isOk()).andReturn());
    }

    private String input(JsonNode state) {
        return "{}";
    }

    private org.springframework.test.web.servlet.ResultActions revoke(MockHttpSession session, String key, String input) throws Exception {
        return mvc.perform(post("/api/reclaim/targets/" + TARGET + "/revoke").session(session).with(csrf())
            .header("Idempotency-Key", key).contentType("application/json").content(input));
    }

    @Test @org.junit.jupiter.api.Order(1)
    void revokesMockProviderAndAssignmentOnceAndPreservesHistoricalReportAndBudget() throws Exception {
        var operator = login("p2_a_operator");
        jdbc.update("INSERT INTO mock_entitlement_memberships(assignment_id,company_id,user_id,entitlement_id,entitlement_revision,mapping) SELECT id,company_id,user_id,entitlement_id,entitlement_revision,'{}'::jsonb FROM access_assignments WHERE id=?::uuid", ASSIGNMENT);
        String before = jdbc.queryForObject("SELECT report::text FROM reclaim_run_items WHERE target_id=?::uuid", String.class, TARGET);
        String budgets = jdbc.queryForObject("SELECT jsonb_agg(to_jsonb(b) ORDER BY department_id)::text FROM department_budgets b", String.class);
        var state = execution(operator);
        assertTrue(state.path("can_revoke").asBoolean());
        var input = input(state);
        var receipt = body(revoke(operator, "revoke-once", input).andExpect(status().isOk()).andReturn());
        assertTrue(receipt.path("verification_ok").asBoolean());
        assertTrue(receipt.path("provider_present_before").asBoolean());
        assertFalse(receipt.path("provider_present_after").asBoolean());
        assertEquals("INACTIVE", jdbc.queryForObject("SELECT status FROM access_assignments WHERE id=?::uuid AND ended_at IS NOT NULL", String.class, ASSIGNMENT));
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM mock_entitlement_memberships WHERE assignment_id=?::uuid", Integer.class, ASSIGNMENT));
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM reclaim_targets WHERE assignment_id=?::uuid AND closed_at IS NULL", Integer.class, ASSIGNMENT));
        revoke(operator, "revoke-once", input).andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("ALREADY_REVOKED"));
        revoke(operator, "other-key", input).andExpect(status().isConflict());
        assertEquals(before, jdbc.queryForObject("SELECT report::text FROM reclaim_run_items WHERE target_id=?::uuid", String.class, TARGET));
        assertEquals(budgets, jdbc.queryForObject("SELECT jsonb_agg(to_jsonb(b) ORDER BY department_id)::text FROM department_budgets b", String.class));
        var overview=body(mvc.perform(get("/api/reclaim/overview").session(operator)).andExpect(status().isOk()).andReturn());
        var current=java.util.stream.StreamSupport.stream(overview.path("targets").spliterator(),false)
            .filter(t->TARGET.equals(t.path("target_id").asText())).findFirst().orElseThrow();
        assertEquals("RECLAIMED",current.path("candidate_status").asText());
        assertEquals("REVOKED",current.path("action_taken").asText());
        assertFalse(current.path("can_revoke").asBoolean());assertFalse(current.path("reclaimed_at").isNull());
        assertEquals(0,overview.path("summary").path("review_target_count").asInt());
        assertEquals("REVOKED",jdbc.queryForObject("SELECT action_taken FROM reclaim_run_items WHERE run_id=?::uuid AND assignment_id=?::uuid",String.class,receipt.path("review_run_id").asText(),ASSIGNMENT));
        mvc.perform(get("/api/reclaim/targets/" + TARGET).session(operator)).andExpect(status().isOk());
        mvc.perform(get("/api/reclaim/executions").session(operator)).andExpect(status().isOk()).andExpect(jsonPath("$.items[0].id").value(receipt.path("id").asText()));
        mvc.perform(get("/api/reclaim/executions").session(login("p2_b_operator"))).andExpect(status().isOk()).andExpect(jsonPath("$.items").isEmpty());
        assertEquals("SUCCEEDED", execution(operator).path("execution_status").asText());
    }

    @Test @org.junit.jupiter.api.Order(1)
    void seedWithoutProviderCanBeReconciledWithoutInventingAProviderDeletion() throws Exception {
        var operator = login("p2_a_operator");
        var receipt = body(revoke(operator, "seed-without-provider", input(execution(operator))).andExpect(status().isOk()).andReturn());
        assertFalse(receipt.path("provider_present_before").asBoolean());
        assertTrue(receipt.path("verification_ok").asBoolean());
        String seed = Files.readString(SEED).replaceAll("(?m)^(BEGIN|COMMIT);[\\t ]*\\r?$", "");
        jdbc.execute((ConnectionCallback<Void>) c -> {try (var sql=c.createStatement()) { sql.execute(seed); } return null;});
        assertEquals("INACTIVE", jdbc.queryForObject("SELECT status FROM access_assignments WHERE id=?::uuid", String.class, ASSIGNMENT));
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM reclaim_execution_receipts WHERE assignment_id=?::uuid", Integer.class, ASSIGNMENT));
    }

    @Test @org.junit.jupiter.api.Order(1)
    void enforcesSessionCsrfCompanyAndWriteCapability() throws Exception {
        var operator = login("p2_a_operator");
        var input = input(execution(operator));
        mvc.perform(get("/api/reclaim/targets/" + TARGET + "/execution")).andExpect(status().isUnauthorized());
        mvc.perform(post("/api/reclaim/targets/" + TARGET + "/revoke").session(operator)
            .header("Idempotency-Key", "csrf").contentType("application/json").content(input)).andExpect(status().isForbidden());
        revoke(login("p2_b_operator"), "foreign", input).andExpect(status().isForbidden());
        revoke(login("p2_a_requester"), "requester", input).andExpect(status().isForbidden());
        jdbc.update("DELETE FROM operator_assignments WHERE user_id=(SELECT id FROM users WHERE login_id='p2_a_operator') AND capability='SAAS_OPERATOR'");
        assertFalse(execution(operator).path("can_revoke").asBoolean());
        revoke(operator, "reviewer-only", input).andExpect(status().isForbidden());
        assertEquals("ACTIVE", jdbc.queryForObject("SELECT status FROM access_assignments WHERE id=?::uuid", String.class, ASSIGNMENT));
    }

    @Test @org.junit.jupiter.api.Order(1)
    void rejectsExtraInputAndChangedUsageWithoutMutation() throws Exception {
        var operator = login("p2_a_operator");
        String input = input(execution(operator));
        revoke(operator,"extra-input","{\"executed_by\":\"other-user\"}").andExpect(status().isBadRequest());
        jdbc.update("UPDATE assignment_usage SET last_used_at=now(),observed_at=now(),observation_status='KNOWN' WHERE assignment_id=?::uuid", ASSIGNMENT);
        assertFalse(execution(operator).path("can_revoke").asBoolean());
        revoke(operator, "changed-usage", input).andExpect(status().isConflict());
        assertEquals("ACTIVE", jdbc.queryForObject("SELECT status FROM access_assignments WHERE id=?::uuid", String.class, ASSIGNMENT));
    }

    @Test @org.junit.jupiter.api.Order(1)
    void rejectsMissingKeyInvalidIdentifiersAndUnsupportedMode() throws Exception {
        var operator=login("p2_a_operator");String input=input(execution(operator));
        mvc.perform(post("/api/reclaim/targets/"+TARGET+"/revoke").session(operator).with(csrf()).contentType("application/json").content(input)).andExpect(status().isBadRequest());
        mvc.perform(get("/api/reclaim/targets/invalid/execution").session(operator)).andExpect(status().isBadRequest());
        mvc.perform(get("/api/reclaim/targets/00000000-0000-0000-0000-000000000001/execution").session(operator)).andExpect(status().isNotFound());
        mvc.perform(get("/api/reclaim/executions?cursor=-1").session(operator)).andExpect(status().isBadRequest());
        mvc.perform(get("/api/reclaim/executions").session(login("p2_a_requester"))).andExpect(status().isForbidden());
        jdbc.update("UPDATE companies SET is_mock=false WHERE id=(SELECT company_id FROM access_assignments WHERE id=?::uuid)",ASSIGNMENT);
        assertEquals("MOCK_ONLY",execution(operator).path("block_reason").asText());
        revoke(operator,"real-company",input).andExpect(status().isForbidden());
    }

    @Test @org.junit.jupiter.api.Order(1)
    void wrongPlatformAndDepartedOperatorsCannotReadOrExecute() throws Exception {
        var operator=login("p2_a_operator");String input=input(execution(operator));
        jdbc.update("DELETE FROM operator_assignments WHERE user_id=(SELECT id FROM users WHERE login_id='p2_a_operator') AND platform='GITHUB'");
        mvc.perform(get("/api/reclaim/targets/"+TARGET+"/execution").session(operator)).andExpect(status().isForbidden());
        revoke(operator,"wrong-platform",input).andExpect(status().isForbidden());
        jdbc.update("UPDATE users SET employment_status='LEFT' WHERE login_id='p2_a_operator'");
        mvc.perform(get("/api/reclaim/executions").session(operator)).andExpect(status().isForbidden());
    }

    private JsonNode startScan(MockHttpSession operator, String scopeKey) throws Exception {
        var scope = jdbc.queryForObject("SELECT id::text FROM reclaim_scopes WHERE scope_key=?", String.class, scopeKey);
        return body(mvc.perform(post("/api/reclaim/runs").session(operator).with(csrf())
            .header("Idempotency-Key", java.util.UUID.randomUUID().toString()).contentType("application/json")
            .content(json.writeValueAsString(java.util.Map.of("scope_id", scope))))
            .andExpect(status().isAccepted()).andReturn());
    }

    private JsonNode scanEvent(JsonNode run) throws Exception {
        var targets = json.createArrayNode();
        jdbc.queryForList("SELECT facts::text FROM reclaim_snapshot_items WHERE snapshot_id=?::uuid ORDER BY ordinal", String.class, run.path("snapshot_id").asText())
            .forEach(raw -> {try { targets.add(json.readTree(raw).path("candidate")); } catch (Exception e) {throw new RuntimeException(e);} });
        var view = ((com.fasterxml.jackson.databind.node.ObjectNode) run).deepCopy();
        long reviews = java.util.stream.StreamSupport.stream(targets.spliterator(),false).filter(x->x.path("review_required").asBoolean()).count();
        view.put("status","EXECUTING").put("reason_code","SCAN_IN_PROGRESS").put("scan_complete",true).put("needs_review_count",reviews).putNull("summary");
        var event=json.createObjectNode().put("schema_version",2).put("task_type","RECLAIM_SCAN").put("event_id",java.util.UUID.randomUUID().toString())
            .put("run_id",run.path("run_id").asText()).put("event_type","RECLAIM_CHECKED")
            .put("job_event_id",jdbc.queryForObject("SELECT active_job_event_id::text FROM reclaim_runs WHERE id=?::uuid",String.class,run.path("run_id").asText()));
        event.set("result",view);event.set("targets",targets);return event;
    }

    @Test @org.junit.jupiter.api.Order(1)
    void delayedScanCannotReopenOrRenotifyAndNextScanOmitsRevokedAssignment() throws Exception {
        var operator=login("p2_a_operator");
        var old=startScan(operator,"phase2:A:R-04");var delayed=scanEvent(old);
        // A newer completed scope can confirm this assignment while the older scope is delayed.
        jdbc.update("INSERT INTO reclaim_scope_assignments(scope_id,company_id,assignment_id) SELECT s.id,s.company_id,?::uuid FROM reclaim_scopes s WHERE scope_key='phase2:A:paid-seats'",ASSIGNMENT);
        var newer=startScan(operator,"phase2:A:paid-seats");results.apply(scanEvent(newer));
        var receipt=body(revoke(operator,"before-delayed",input(execution(operator))).andExpect(status().isOk()).andReturn());
        int notices=jdbc.queryForObject("SELECT count(*) FROM reclaim_notifications",Integer.class);
        results.apply(delayed);results.apply(delayed);
        assertEquals(notices,jdbc.queryForObject("SELECT count(*) FROM reclaim_notifications",Integer.class));
        assertEquals(0,jdbc.queryForObject("SELECT count(*) FROM reclaim_targets WHERE assignment_id=?::uuid AND closed_at IS NULL",Integer.class,ASSIGNMENT));
        assertEquals(receipt.path("id").asText(),jdbc.queryForObject("SELECT superseded_by_receipt_id::text FROM reclaim_run_items WHERE run_id=?::uuid",String.class,old.path("run_id").asText()));
        var next=startScan(operator,"phase2:A:R-04");results.apply(scanEvent(next));
        assertEquals(0,jdbc.queryForObject("SELECT count(*) FROM reclaim_snapshot_items WHERE snapshot_id=?::uuid",Integer.class,next.path("snapshot_id").asText()));
        assertEquals("NO_NEW_CANDIDATES",jdbc.queryForObject("SELECT reason_code FROM reclaim_runs WHERE id=?::uuid",String.class,next.path("run_id").asText()));
    }

    @Test @org.junit.jupiter.api.Order(1)
    void newerUnconfirmedReportBlocksAnOldTargetEvenIfCurrentFactsAreRestored() throws Exception {
        var operator=login("p2_a_operator");String prior=input(execution(operator));
        jdbc.update("UPDATE assignment_usage SET observation_status='UNKNOWN',last_used_at=NULL,observed_at=now() WHERE assignment_id=?::uuid",ASSIGNMENT);
        var newer=startScan(operator,"phase2:A:R-04");
        assertFalse(execution(operator).path("can_revoke").asBoolean());
        results.apply(scanEvent(newer));
        jdbc.update("UPDATE assignment_usage SET observation_status='KNOWN',last_used_at=now()-interval '47 days',observed_at=now() WHERE assignment_id=?::uuid",ASSIGNMENT);
        assertEquals("RECHECK_REQUIRED",execution(operator).path("block_reason").asText());
        revoke(operator,"old-confirmed-report",prior).andExpect(status().isConflict());
        mvc.perform(get("/api/reclaim/targets/"+TARGET).session(operator)).andExpect(status().isOk());
    }

    @Test @org.junit.jupiter.api.Order(1)
    void newlyApprovedRetentionPreventsRevocation() throws Exception {
        var operator=login("p2_a_operator");String prior=input(execution(operator));
        jdbc.update("INSERT INTO retention_exceptions(id,company_id,assignment_id,approved_by,valid_from,valid_until,reason) SELECT gen_random_uuid(),a.company_id,a.id,u.id,now()-interval '1 day',now()+interval '1 day','계속 사용' FROM access_assignments a JOIN users u ON u.login_id='p2_a_operator' WHERE a.id=?::uuid",ASSIGNMENT);
        assertEquals("CANDIDATE_CHANGED",execution(operator).path("block_reason").asText());
        revoke(operator,"retained",prior).andExpect(status().isConflict());
    }

    @Test @org.junit.jupiter.api.Order(1)
    @org.springframework.transaction.annotation.Transactional(propagation=org.springframework.transaction.annotation.Propagation.NOT_SUPPORTED)
    void receiptFailureRollsBackProviderAssignmentAndTarget() throws Exception {
        var operator=login("p2_a_operator");String input=input(execution(operator));
        jdbc.update("INSERT INTO mock_entitlement_memberships(assignment_id,company_id,user_id,entitlement_id,entitlement_revision,mapping) SELECT id,company_id,user_id,entitlement_id,entitlement_revision,'{}'::jsonb FROM access_assignments WHERE id=?::uuid",ASSIGNMENT);
        jdbc.execute("CREATE FUNCTION reject_revoke_test() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Injected receipt failure'; END $$");
        jdbc.execute("CREATE TRIGGER reject_revoke_test BEFORE INSERT ON reclaim_execution_receipts FOR EACH ROW EXECUTE FUNCTION reject_revoke_test()");
        try {
            revoke(operator,"rollback",input).andExpect(status().isInternalServerError());
            assertEquals("ACTIVE",jdbc.queryForObject("SELECT status FROM access_assignments WHERE id=?::uuid",String.class,ASSIGNMENT));
            assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM mock_entitlement_memberships WHERE assignment_id=?::uuid",Integer.class,ASSIGNMENT));
            assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM reclaim_targets WHERE id=?::uuid AND closed_at IS NULL",Integer.class,TARGET));
            assertEquals(0,jdbc.queryForObject("SELECT count(*) FROM reclaim_execution_receipts WHERE assignment_id=?::uuid",Integer.class,ASSIGNMENT));
        } finally {
            jdbc.execute("DROP TRIGGER reject_revoke_test ON reclaim_execution_receipts");jdbc.execute("DROP FUNCTION reject_revoke_test()");
            jdbc.update("DELETE FROM mock_entitlement_memberships WHERE assignment_id=?::uuid",ASSIGNMENT);
        }
    }

    @Test @org.junit.jupiter.api.Order(1)
    void successfulReceiptCannotBeRewritten() throws Exception {
        var operator=login("p2_a_operator");revoke(operator,"immutable",input(execution(operator))).andExpect(status().isOk());
        assertThrows(org.springframework.dao.DataAccessException.class,()->jdbc.update("UPDATE reclaim_execution_receipts SET reason='변경' WHERE assignment_id=?::uuid",ASSIGNMENT));
    }

    @Test @org.junit.jupiter.api.Order(100)
    @org.springframework.transaction.annotation.Transactional(propagation=org.springframework.transaction.annotation.Propagation.NOT_SUPPORTED)
    void concurrentReplaysCommitExactlyOneReceiptAndRegrantUsesANewAssignment() throws Exception {
        var operator=login("p2_a_operator");String input=input(execution(operator));
        try(var executor=java.util.concurrent.Executors.newFixedThreadPool(2)) {
            var gate=new java.util.concurrent.CountDownLatch(1);
            java.util.concurrent.Callable<Integer> call=()-> {gate.await();return revoke(operator,"concurrent",input).andReturn().getResponse().getStatus();};
            var first=executor.submit(call);var second=executor.submit(call);gate.countDown();
            var statuses=new java.util.ArrayList<>(java.util.List.of(first.get(20,java.util.concurrent.TimeUnit.SECONDS),second.get(20,java.util.concurrent.TimeUnit.SECONDS)));
            statuses.sort(Integer::compareTo);assertEquals(java.util.List.of(200,409),statuses);
        }
        assertEquals(1,jdbc.queryForObject("SELECT count(*) FROM reclaim_execution_receipts WHERE assignment_id=?::uuid",Integer.class,ASSIGNMENT));
        var run=startScan(operator,"phase2:A:paid-seats");results.apply(scanEvent(run));
        String r01Target=jdbc.queryForObject("SELECT target_id::text FROM reclaim_run_items WHERE run_id=?::uuid AND candidate_status='PENDING_REVIEW'",String.class,run.path("run_id").asText());
        var r01State=body(mvc.perform(get("/api/reclaim/targets/"+r01Target+"/execution").session(operator)).andExpect(status().isOk()).andReturn());
        String r01Input=input(r01State);
        try(var executor=java.util.concurrent.Executors.newFixedThreadPool(2)) {
            var gate=new java.util.concurrent.CountDownLatch(1);
            var calls=java.util.stream.Stream.of("competing-a","competing-b").map(key->executor.submit(()-> {
                gate.await();return mvc.perform(post("/api/reclaim/targets/"+r01Target+"/revoke").session(operator).with(csrf())
                    .header("Idempotency-Key",key).contentType("application/json").content(r01Input)).andReturn().getResponse().getStatus();
            })).toList();gate.countDown();
            var statuses=new java.util.ArrayList<Integer>();for(var call:calls)statuses.add(call.get(20,java.util.concurrent.TimeUnit.SECONDS));
            statuses.sort(Integer::compareTo);assertEquals(java.util.List.of(200,409),statuses);
        }
        // A later grant is a new assignment; the old receipt cannot prevent or revoke it.
        var replacement=java.util.UUID.randomUUID();
        jdbc.update("INSERT INTO access_assignments SELECT ?::uuid,company_id,user_id,resource_id,entitlement_id,entitlement_revision,'ACTIVE',origin_tf_id,now(),NULL,NULL FROM access_assignments WHERE id=?::uuid",replacement.toString(),ASSIGNMENT);
        revoke(operator,"new-click",input).andExpect(status().isConflict());
        assertEquals("ACTIVE",jdbc.queryForObject("SELECT status FROM access_assignments WHERE id=?",String.class,replacement));
    }
}
