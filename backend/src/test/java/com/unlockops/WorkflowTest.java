package com.unlockops;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.unlockops.contracts.v2.WorkflowTypes.*;
import com.unlockops.reclaim.ReclaimPolicy;
import com.unlockops.common.workflow.*;
import com.unlockops.messaging.workflow.*;
import com.unlockops.access.*;
import com.unlockops.reclaim.ReclaimResultService;
import com.unlockops.common.json.Jsons;
import java.time.OffsetDateTime;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/** Only the risky boundaries: unused-period start, unknown observations, old events and duplicate execution. */
class WorkflowTest {
    private final ObjectMapper mapper=new ObjectMapper();
    private final String id="10000000-0000-0000-0000-000000000001";
    private JsonNode node(String s) throws Exception {return mapper.readTree(s);}
    private JsonNode policy() throws Exception {return node("""
        {"doc_id":"P2","article":"5","revision":1,"source_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","content":"policy"}
        """);}
    private List<JsonNode> rules() throws Exception {return List.of(node("""
        {"code":"TF_ENDED_UNUSED_30D","idle_days":30,"exclude_retention":true,"exclude_other_active_tf":true}
        """),node("{\"code\":\"EMPLOYEE_LEFT\"}"));}
    private ObjectNode facts() throws Exception {return (ObjectNode)node("""
        {"assignment_id":"10000000-0000-0000-0000-000000000001","platform":"GITHUB","employment_status":"ACTIVE",
         "origin_tf_id":"10000000-0000-0000-0000-000000000002","tf_ends_on":"2026-09-20",
         "granted_at":"2026-08-01T00:00:00+09:00","last_used_at":"2026-09-05T09:00:00+09:00",
         "observation_status":"KNOWN","observed_at":"2026-10-22T09:00:00+09:00",
         "retention":false,"other_active_tf":false,
         "price":{"monthly_amount":19.00,"currency":"USD","source_kind":"SYNTHETIC_CONTRACT"}}
        """);}
    @Test void unusedPeriodStartsAtLatestFactAndUnknownDoesNotMeanUnused() throws Exception {
        var time=OffsetDateTime.parse("2026-10-22T09:00:00+09:00");var f=facts();
        assertEquals(CandidateStatus.PENDING_REVIEW,ReclaimPolicy.evaluate(f,policy(),rules(),time).candidateStatus());
        f.put("last_used_at","2026-10-01T00:00:00+09:00");
        assertEquals(CandidateStatus.EXCLUDED,ReclaimPolicy.evaluate(f,policy(),rules(),time).candidateStatus());
        f.put("observation_status","UNKNOWN");f.putNull("last_used_at");
        assertTrue(ReclaimPolicy.evaluate(f,policy(),rules(),time).reviewRequired());
        f=facts();f.putNull("price");assertTrue(ReclaimPolicy.evaluate(f,policy(),rules(),time).reviewRequired());
    }
    @Test void retentionAndOtherTfExcludeButLeftEmployeeUsesSeparateRule() throws Exception {
        var time=OffsetDateTime.parse("2026-10-22T09:00:00+09:00");var f=facts();f.put("retention",true);
        assertEquals(CandidateStatus.RETAINED,ReclaimPolicy.evaluate(f,policy(),rules(),time).candidateStatus());
        f.put("retention",false);f.put("other_active_tf",true);
        assertEquals("ACTIVE_OTHER_TF",ReclaimPolicy.evaluate(f,policy(),rules(),time).exclusionReasonCode());
        f.put("employment_status","LEFT");
        assertEquals("EMPLOYEE_LEFT",ReclaimPolicy.evaluate(f,policy(),rules(),time).candidateReasonCode());
    }
    @Test void oldAnalysisGenerationIsAuditedWithoutApplyingIt() throws Exception {
        JdbcTemplate jdbc=mock(JdbcTemplate.class);var db=spy(new WorkflowStore(jdbc,new Jsons(mapper)));
        var access=mock(AccessWorkflowService.class);var execution=mock(AccessExecutionService.class);var reclaim=mock(ReclaimResultService.class);
        doReturn(node("{\"active_job_event_id\":\"20000000-0000-0000-0000-000000000001\"}")).when(db).problem(UUID.fromString(id),true);
        when(jdbc.update("INSERT INTO inbox_events(event_id) VALUES(?) ON CONFLICT DO NOTHING",UUID.fromString(id))).thenReturn(1);
        var raw=node("""
            {"schema_version":2,"event_id":"10000000-0000-0000-0000-000000000001",
             "job_event_id":"30000000-0000-0000-0000-000000000001","task_type":"ACCESS_REQUEST",
             "problem_id":"10000000-0000-0000-0000-000000000001","job_type":"ANALYZE","event_type":"PROGRESS",
             "result":{"schema_version":2,"task_type":"ACCESS_REQUEST","problem_id":"10000000-0000-0000-0000-000000000001","status":"DIAGNOSING","message":"진행 중"}}
            """);
        new WorkflowResults(db,access,execution,reclaim).apply(raw);
        verifyNoInteractions(access,execution,reclaim);
    }
    @Test void existingReceiptIsReturnedWithoutAnotherGrantOrBudgetCharge() throws Exception {
        JdbcTemplate jdbc=mock(JdbcTemplate.class);var db=spy(new WorkflowStore(jdbc,new Jsons(mapper)));
        var planner=mock(AccessPlanningService.class);var workflow=mock(AccessWorkflowService.class);String hash="a".repeat(64);
        var p=mapper.createObjectNode().put("active_job_event_id",id).put("approved_plan_hash",hash).put("plan_hash",hash).put("idempotency_key","key");
        doReturn(p).when(db).problem(UUID.fromString(id),true);
        var receipt=node("{\"executed\":true}");
        doReturn(List.of(receipt)).when(db).rows("SELECT result FROM access_execution_receipts WHERE problem_id=?",UUID.fromString(id));
        assertEquals(receipt,new AccessExecutionService(db,planner,workflow,true).execute(UUID.fromString(id),new AccessExecutionService.ExecutionInput(UUID.fromString(id),hash,"key")));
        verifyNoInteractions(jdbc,planner,workflow);
    }

    @Test void decisionsBindToTheCurrentRoundEvenWhenThePlanHashIsUnchanged() throws Exception {
        JdbcTemplate jdbc=mock(JdbcTemplate.class);var db=spy(new WorkflowStore(jdbc,new Jsons(mapper)));
        var acl=mock(WorkflowAccessControl.class);var planner=mock(AccessPlanningService.class);var jobs=mock(WorkflowJobs.class);
        var service=spy(new AccessWorkflowService(db,acl,planner,jobs));
        var vectors=mapper.readTree(java.nio.file.Files.readString(java.nio.file.Path.of("../contracts/phase2/examples/vectors.json")));
        var raw=vectors.path("valid").get(0).path("payload");var plan=db.decode(raw,GrantPlanV2.class);
        var actor=UUID.fromString(plan.approverIds().getFirst());var problem=UUID.fromString(id);
        String hash=vectors.path("plan_sha256").asText();
        var p=mapper.createObjectNode().put("id",id).put("requester_id",plan.requesterId())
            .put("status","WAITING_APPROVAL").put("active_plan_version",2).put("plan_hash",hash);
        p.set("plan",raw);
        doReturn(p).when(db).problem(problem,true);
        for(String action:List.of("APPROVE","REJECT","HOLD")) {
            var error=assertThrows(org.springframework.web.server.ResponseStatusException.class,
                ()->service.decide(actor,problem,new ApprovalDecisionInput(action,hash,1,"검토 사유")));
            assertEquals(409,error.getStatusCode().value());
        }
        verifyNoInteractions(jdbc,planner,jobs);
        // The identical hash with the current version can still advance the approval route.
        doReturn(mapper.createObjectNode().put("step",1).put("approver_id",actor.toString())).when(db)
            .one("SELECT to_jsonb(s) FROM approval_steps s WHERE problem_id=? AND plan_version=? AND status='WAITING'",problem,2);
        when(planner.sameCurrentPlan(p,plan)).thenReturn(true);
        doReturn(p).when(db).problem(problem,false);doReturn(null).when(service).view(p);
        service.decide(actor,problem,new ApprovalDecisionInput("APPROVE",hash,2,null));
        verify(jdbc).update("UPDATE approval_steps SET status=?,reason=?,acted_at=now() WHERE problem_id=? AND plan_version=? AND step=?","APPROVED",null,problem,2,1);
    }
}
