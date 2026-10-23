package com.unlockops.regression;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.unlockops.access.*;
import com.unlockops.common.json.Jsons;
import com.unlockops.common.workflow.*;
import com.unlockops.contracts.v2.WorkflowTypes.*;
import com.unlockops.messaging.workflow.WorkflowJobs;
import java.util.*;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.*;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.*;
import static com.unlockops.common.workflow.WorkflowStore.*;
import static org.junit.jupiter.api.Assertions.*;

/** Upgrade real V8 data, then use the same planner/approvals/executor as current accounts. */
@Testcontainers
class ExistingAccountsMigrationIT {
    @Container static final PostgreSQLContainer<?> DB=new PostgreSQLContainer<>("postgres:16-alpine");
    private final UUID kim=UUID.fromString("10000000-0000-0000-0000-000000000001");
    private final UUID choi=UUID.fromString("10000000-0000-0000-0000-000000000004");
    private final UUID head=UUID.fromString("10000000-0000-0000-0000-000000000008");
    private final UUID operator=UUID.fromString("10000000-0000-0000-0000-000000000009");
    private final UUID pending=UUID.fromString("40000000-0000-0000-0000-000000000001");
    private final UUID completed=UUID.fromString("40000000-0000-0000-0000-000000000002");

    @Test void upgradePreservesFactsAndHistoryAndSupportsApprovedIdempotentGrants() {
        var source=new DriverManagerDataSource(DB.getJdbcUrl(),DB.getUsername(),DB.getPassword());
        var jdbc=new JdbcTemplate(source);
        Flyway.configure().dataSource(source).target("8").load().migrate();
        jdbc.update("""
            INSERT INTO problems(id,requester_id,approver_id,platform,contents,status,proposal,thread_id,resource_id,
              requested_role,plan,plan_hash,approved_plan_hash,idempotency_key)
            VALUES(?,?,?,'GITHUB','payment-core Write 권한 주세요','WAITING_APPROVAL','이전 대기 기록',?,
              '20000000-0000-0000-0000-000000000001','Write','{"requested_role":"Write"}',repeat('a',64),repeat('a',64),'old-key')
            """,pending,kim,head,pending.toString());
        jdbc.update("""
            INSERT INTO problems(id,requester_id,approver_id,platform,contents,status,proposal,thread_id,
              verification_ok,result_type,reason_code,decided_by,decided_at)
            VALUES(?,?,?,'GITHUB','이전 완료 요청','DONE','이전 완료 기록',?,true,'ACCESS_VERIFIED','VERIFIED',?,now())
            """,completed,kim,head,completed.toString(),head);
        // A stale permissions row is not an effective GitHub team membership.
        jdbc.update("DELETE FROM github_team_members WHERE user_id=? AND team_id='internal-tools-read'",kim);
        String balances=jdbc.queryForObject("SELECT jsonb_agg(to_jsonb(b) ORDER BY department_id)::text FROM department_budgets b",String.class);
        String oldPermissions=jdbc.queryForObject("SELECT jsonb_agg(to_jsonb(p) ORDER BY user_id,resource_id)::text FROM permissions p",String.class);
        Flyway.configure().dataSource(source).load().migrate();
        assertEquals(balances,jdbc.queryForObject("SELECT jsonb_agg(to_jsonb(b) ORDER BY department_id)::text FROM department_budgets b",String.class));
        assertEquals(oldPermissions,jdbc.queryForObject("SELECT jsonb_agg(to_jsonb(p) ORDER BY user_id,resource_id)::text FROM permissions p",String.class));
        assertEquals(2,jdbc.queryForObject("SELECT count(*) FROM problem_events WHERE kind='WORKFLOW_HISTORY_IMPORTED'",Integer.class));
        assertEquals(0,jdbc.queryForObject("SELECT count(*) FROM access_assignments a JOIN resources r ON r.id=a.resource_id WHERE a.user_id=? AND r.external_id='internal-tools'",Integer.class,kim));
        assertEquals(0,jdbc.queryForObject("SELECT count(*) FROM assignment_usage WHERE observation_status<>'UNKNOWN'",Integer.class));

        var db=new WorkflowStore(jdbc,new Jsons(new ObjectMapper()));var acl=new WorkflowAccessControl(db);
        var planner=new AccessPlanningService(db);var jobs=new WorkflowJobs(db);
        var workflow=new AccessWorkflowService(db,acl,planner,jobs);var executor=new AccessExecutionService(db,planner,workflow,true);
        var transaction=new TransactionTemplate(new DataSourceTransactionManager(source));
        transaction.executeWithoutResult(tx->{
            assertFalse(workflow.catalog(kim).isEmpty());assertEquals(2,workflow.summaries(kim).size());
            assertEquals(Status.MANUAL_REVIEW,workflow.get(kim,pending).status());
            assertEquals("ACCESS_VERIFIED",workflow.get(kim,completed).resultType());
            assertEquals("ACCESS_VERIFIED",((com.fasterxml.jackson.databind.JsonNode)workflow.report(kim,completed).get("historical_record")).path("result_type").asText());
            assertThrows(org.springframework.web.server.ResponseStatusException.class,()->workflow.get(choi,pending));
            // A V1 plan cannot enter any worker/execution endpoint.
            assertThrows(org.springframework.web.server.ResponseStatusException.class,()->db.problem(pending,false));
            var resumed=workflow.resume(kim,pending);assertEquals(Status.RECEIVED,resumed.status());
            var p=db.problem(pending,false);assertNull(str(p,"plan_hash"));assertNull(str(p,"approved_plan_hash"));
            assertNull(str(p,"idempotency_key"));assertNull(str(p,"decided_by"));
            assertEquals("ANALYZE",db.one("SELECT payload FROM outbox WHERE event_id=?",uuid(p,"active_job_event_id")).path("job_type").asText());

            var seat=db.one("SELECT to_jsonb(e) FROM entitlements e WHERE code='COPILOT_SEAT'");
            UUID entitlement=uuid(seat,"id");
            var read=db.one("SELECT to_jsonb(e) FROM entitlements e JOIN resources r ON r.id=e.resource_id WHERE r.external_id='docs-site' AND e.code='READ'");
            assertEquals("ALREADY_HAS_ACCESS",planner.assess(db.json.tree("{\"company_id\":\"00000000-0000-0000-0000-000000000000\",\"requester_id\":\"10000000-0000-0000-0000-000000000003\",\"platform\":\"GITHUB\"}"),uuid(read,"id")).reason());
            assertEquals("DUPLICATE_SEAT",planner.assess(db.json.tree("{\"company_id\":\"00000000-0000-0000-0000-000000000000\",\"requester_id\":\""+choi+"\",\"platform\":\"GITHUB\"}"),entitlement).reason());
            var created=workflow.create(kim,new AccessRequestInput(2,Platform.GITHUB,"GitHub Copilot 좌석 신청합니다.",str(seat,"resource_id"),entitlement.toString()),"existing-account-seat");
            UUID id=UUID.fromString(created.problemId());p=db.problem(id,false);
            var assessment=planner.assess(p,entitlement);assertEquals(Status.WAITING_APPROVAL,assessment.status());
            assertEquals(List.of(head.toString(),operator.toString()),assessment.plan().approverIds());
            var steps=List.of(new ApprovalStep(1,head.toString(),ApprovalStatus.WAITING,null,null),new ApprovalStep(2,operator.toString(),ApprovalStatus.PENDING,null,null));
            var policy=db.one("SELECT to_jsonb(p) FROM policy_revisions p WHERE company_id=?",new UUID(0,0));
            String section=Arrays.stream(str(policy,"content").split("(?m)(?=^## )")).filter(s->s.startsWith("## ")).findFirst().orElseThrow().strip();
            var citation=new PolicyEvidence(str(policy,"doc_id"),section.lines().findFirst().orElseThrow().substring(3),"1",str(policy,"source_hash"),section);
            var waiting=new AccessView(2,"ACCESS_REQUEST",Status.WAITING_APPROVAL,"ELIGIBLE","검토 보고서",1,2,steps,null,id.toString(),null,db.codec.planHash(assessment.plan()),null);
            workflow.analysis(p,new AccessEvent(2,UUID.randomUUID().toString(),str(p,"active_job_event_id"),entitlement.toString(),List.of(citation),"ACCESS_REQUEST",id.toString(),"ANALYZE","ANALYZED",waiting));
            var view=workflow.get(kim,id);
            assertThrows(org.springframework.web.server.ResponseStatusException.class,()->workflow.decide(kim,id,new ApprovalDecisionInput("APPROVE",view.planHash(),view.planVersion(),null)));
            workflow.decide(head,id,new ApprovalDecisionInput("APPROVE",view.planHash(),view.planVersion(),null));
            workflow.decide(operator,id,new ApprovalDecisionInput("APPROVE",view.planHash(),view.planVersion(),null));
            p=db.problem(id,false);
            var input=new AccessExecutionService.ExecutionInput(uuid(p,"active_job_event_id"),str(p,"approved_plan_hash"),str(p,"idempotency_key"));
            var receipt=executor.execute(id,input);assertEquals(receipt,executor.execute(id,input));
            assertEquals(true,executor.verify(id,input).get("verification_ok"));
            assertEquals("131.00",jdbc.queryForObject("SELECT remaining_monthly_amount::text FROM department_budgets WHERE department_id='00000000-0000-0000-0000-000000000001'",String.class));
        });
        // Flyway re-entry cannot duplicate imported memberships or charge any budget.
        int assignments=jdbc.queryForObject("SELECT count(*) FROM access_assignments",Integer.class);
        Flyway.configure().dataSource(source).load().migrate();
        assertEquals(assignments,jdbc.queryForObject("SELECT count(*) FROM access_assignments",Integer.class));
    }
}
