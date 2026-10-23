package com.unlockops.regression;

import com.fasterxml.jackson.databind.*;
import com.unlockops.access.*;
import com.unlockops.common.json.Jsons;
import com.unlockops.common.workflow.*;
import com.unlockops.contracts.v2.WorkflowTypes.*;
import com.unlockops.messaging.workflow.WorkflowJobs;
import java.nio.file.*;
import java.sql.DriverManager;
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

/** PostgreSQL regression: existing-license grants cannot debit a second seat price. */
@Testcontainers
class AccessCostsIT {
    @Container static final PostgreSQLContainer<?> DB=new PostgreSQLContainer<>("postgres:16-alpine");
    WorkflowStore db;AccessPlanningService planner;AccessWorkflowService workflow;AccessExecutionService execution;
    final ObjectMapper json=new ObjectMapper();UUID requester,company,department;
    JsonNode entitlement(String platform) {
        return db.one("SELECT to_jsonb(e) FROM entitlements e JOIN resources r ON r.id=e.resource_id WHERE e.company_id=? AND r.platform=? AND (r.platform<>'GITHUB' OR e.code='COPILOT_SEAT')",company,platform);
    }
    AccessPlanningService.Assessment assess(String platform) {
        var ent=entitlement(platform);
        return planner.assess(json.createObjectNode().put("id",UUID.randomUUID().toString()).put("company_id",company.toString())
            .put("requester_id",requester.toString()).put("platform",platform).put("resource_id",str(ent,"resource_id")),uuid(ent,"id"));
    }
    JsonNode grant(String platform) {
        var ent=entitlement(platform);
        var created=workflow.create(requester,new AccessRequestInput(2,Platform.valueOf(platform),platform+" 업무 권한 신청",str(ent,"resource_id"),str(ent,"id")),UUID.randomUUID().toString());
        UUID id=UUID.fromString(created.problemId());var p=db.problem(id,false);var assessment=planner.assess(p,uuid(ent,"id"));
        assertEquals(Status.WAITING_APPROVAL,assessment.status());
        var policy=db.one("SELECT to_jsonb(p) FROM policy_revisions p WHERE company_id=? ORDER BY revision DESC LIMIT 1",company);
        String section=Arrays.stream(str(policy,"content").split("(?m)(?=^## )")).filter(s->s.startsWith("## ")).findFirst().orElseThrow().strip();
        var citation=new PolicyEvidence(str(policy,"doc_id"),section.lines().findFirst().orElseThrow().substring(3),"4",str(policy,"source_hash"),section);
        var ids=assessment.plan().approverIds();
        var steps=new ArrayList<ApprovalStep>();
        for(int n=0;n<ids.size();n++)steps.add(new ApprovalStep(n+1,ids.get(n),n==0?ApprovalStatus.WAITING:ApprovalStatus.PENDING,null,null));
        var waiting=new AccessView(2,"ACCESS_REQUEST",Status.WAITING_APPROVAL,"ELIGIBLE","검토 보고서",1,2,steps,null,id.toString(),null,db.codec.planHash(assessment.plan()),null);
        workflow.analysis(p,new AccessEvent(2,UUID.randomUUID().toString(),str(p,"active_job_event_id"),str(ent,"id"),List.of(citation),"ACCESS_REQUEST",id.toString(),"ANALYZE","ANALYZED",waiting));
        for(String actor:ids) {
            var view=workflow.get(requester,id);
            workflow.decide(UUID.fromString(actor),id,new ApprovalDecisionInput("APPROVE",view.planHash(),view.planVersion(),null));
        }
        p=db.problem(id,false);
        var input=new AccessExecutionService.ExecutionInput(uuid(p,"active_job_event_id"),str(p,"approved_plan_hash"),str(p,"idempotency_key"));
        var receipt=execution.execute(id,input);
        assertEquals(receipt,execution.execute(id,input));
        assertEquals(true,execution.verify(id,input).get("verification_ok"));
        return receipt;
    }
    @Test void upgradedCostRulesKeepLicensedEditsFreeAndRealPurchasesBudgeted() throws Exception {
        Flyway.configure().dataSource(DB.getJdbcUrl(),DB.getUsername(),DB.getPassword()).load().migrate();
        try(var connection=DriverManager.getConnection(DB.getJdbcUrl(),DB.getUsername(),DB.getPassword());var sql=connection.createStatement()) {
            for(String file:List.of("seed.sql","policies/apply.sql","policies/apply-v4.sql","policies/apply-costs.sql","policies/apply-costs.sql"))
                sql.execute(Files.readString(Path.of("../data/phase2/"+file)));
        }
        var source=new DriverManagerDataSource(DB.getJdbcUrl(),DB.getUsername(),DB.getPassword());var jdbc=new JdbcTemplate(source);
        var catalog=json.readTree(Files.readString(Path.of("../data/phase2/catalog.json"))).path("companies").path("A");
        requester=UUID.fromString(catalog.path("users").path("requester").asText());company=uuid(catalog,"company_id");department=uuid(catalog,"department_id");
        db=new WorkflowStore(jdbc,new Jsons(json));planner=new AccessPlanningService(db);
        workflow=new AccessWorkflowService(db,new WorkflowAccessControl(db),planner,new WorkflowJobs(db));execution=new AccessExecutionService(db,planner,workflow,true);
        new TransactionTemplate(new DataSourceTransactionManager(source)).executeWithoutResult(tx->{
            jdbc.update("UPDATE department_budgets SET remaining_monthly_amount=10 WHERE department_id=?",department);
            for(String platform:List.of("NOTION","TABLEAU_CLOUD")) {
                var result=assess(platform);assertEquals(Status.WAITING_APPROVAL,result.status());
                assertEquals("0.00",result.plan().monthlyAmount());assertEquals("NO_ADDITIONAL_COST",result.plan().costBasis());
                assertEquals("0.00",grant(platform).path("charged_amount").asText());
            }
            assertEquals("10.00",jdbc.queryForObject("SELECT remaining_monthly_amount::text FROM department_budgets WHERE department_id=?",String.class,department));
            assertEquals("BUDGET_INSUFFICIENT",assess("GITHUB").reason());
            jdbc.update("UPDATE department_budgets SET remaining_monthly_amount=50 WHERE department_id=?",department);
            assertEquals("19.00",grant("GITHUB").path("charged_amount").asText());
            assertEquals("31.00",jdbc.queryForObject("SELECT remaining_monthly_amount::text FROM department_budgets WHERE department_id=?",String.class,department));
            assertEquals("COVERED",jdbc.queryForObject("SELECT coverage FROM saas_license_facts WHERE company_id=? AND user_id=? AND platform='GITHUB'",String.class,company,requester));
        });
    }
}
