package com.unlockops.access;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.unlockops.common.json.Jsons;
import com.unlockops.common.workflow.*;
import com.unlockops.contracts.v2.WorkflowTypes.*;
import com.unlockops.messaging.workflow.WorkflowJobs;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class ExistingAccountHistoryTest {
    private final ObjectMapper mapper=new ObjectMapper();
    private final UUID id=UUID.fromString("40000000-0000-0000-0000-000000000001");
    private final UUID requester=UUID.fromString("10000000-0000-0000-0000-000000000001");
    private final UUID approver=UUID.fromString("10000000-0000-0000-0000-000000000002");
    private final UUID company=new UUID(0,0);
    private ObjectNode record(String status) {
        return mapper.createObjectNode().put("id",id.toString()).put("contract_version",1)
            .put("company_id",company.toString()).put("requester_id",requester.toString())
            .put("approver_id",approver.toString()).put("platform","GITHUB").put("contents","payment-core Write 권한 주세요")
            .put("status",status).put("proposal","당시 처리 안내").put("plan_hash","a".repeat(64))
            .put("approved_plan_hash","a".repeat(64)).put("idempotency_key","old-execution-key");
    }
    private WorkflowStore store() { return new WorkflowStore(mock(JdbcTemplate.class),new Jsons(mapper)); }

    @ParameterizedTest
    @ValueSource(strings={"RECEIVED","DIAGNOSING","WAITING_APPROVAL","ON_HOLD","EXECUTING","MANUAL_REVIEW","LEGACY_PENDING"})
    void nonTerminalHistoryOffersReanalysisWithoutRequiringACurrentEnum(String originalStatus) {
        var p=record(originalStatus);p.set("plan",mapper.createObjectNode().put("requested_role","Write"));
        var view=HistoricalAccess.view(store(),p);
        assertEquals(Status.MANUAL_REVIEW,view.status());assertEquals("PLAN_REVIEW_REQUIRED",view.reasonCode());
        assertTrue(view.approvalSteps().isEmpty());assertNull(view.planHash());assertNull(view.planVersion());
        assertTrue(view.message().contains("이전 계획과 승인은 재사용하지 않습니다"));
        assertEquals(originalStatus,p.path("status").asText()); // Reading cannot mutate the record.
    }
    @Test void anUnknownHistoricalPendingStatusDoesNotBreakTheUsersList() {
        var oldPending=record("LEGACY_PENDING");
        var rejected=record("REJECTED").put("id",UUID.randomUUID().toString());
        var db=new WorkflowStore(mock(JdbcTemplate.class),new Jsons(mapper)) {
            @Override public List<JsonNode> rows(String sql,Object...args) {
                if(sql.contains("FROM problems p")) return List.of(oldPending,rejected);
                throw new AssertionError(sql);
            }
        };
        var acl=mock(WorkflowAccessControl.class);
        when(acl.actor(requester)).thenReturn(mapper.createObjectNode().put("company_id",company.toString()));
        var service=new AccessWorkflowService(db,acl,mock(AccessPlanningService.class),mock(WorkflowJobs.class));
        var views=service.list(requester);
        assertEquals(2,views.size());
        assertEquals(Status.MANUAL_REVIEW,views.getFirst().status());
        assertEquals("PLAN_REVIEW_REQUIRED",views.getFirst().reasonCode());
        assertEquals(Status.REJECTED,views.getLast().status());
        verifyNoInteractions(db.jdbc);
    }
    @Test void verifiedHistoryUsesOnlyTheRecordedApprovalAndNeverExposesOldExecutionIdentity() {
        var p=record("DONE").put("result_type","ACCESS_VERIFIED").put("verification_ok",true)
            .put("decided_by",approver.toString()).put("decided_at","2026-10-21T09:00:00+09:00");
        var view=HistoricalAccess.view(store(),p);
        assertEquals("ACCESS_VERIFIED",view.resultType());assertTrue(view.verificationOk());
        assertEquals(approver.toString(),view.approvalSteps().getFirst().approverId());
        assertNull(view.planHash());assertNull(view.planVersion());
        p.remove("decided_by");view=HistoricalAccess.view(store(),p);
        assertEquals("GUIDANCE",view.resultType());assertTrue(view.approvalSteps().isEmpty());
        assertTrue(view.message().contains("당시 권한 검증 완료"));
    }
    @Test void oldReasonStatusMismatchStillReturnsReadableHistory() {
        var p=record("REJECTED").put("reason_code","BUDGET_INSUFFICIENT");
        var view=HistoricalAccess.view(store(),p);
        assertEquals(Status.REJECTED,view.status());assertEquals("POLICY_NOT_ELIGIBLE",view.reasonCode());
        assertTrue(HistoricalAccess.summary(p).contains("BUDGET_INSUFFICIENT"));
    }
    @Test void originalApproverCanReadTheirRecordButTenantBoundaryStillApplies() {
        var db=spy(store());var p=record("WAITING_APPROVAL");
        doReturn(mapper.createObjectNode().put("company_id",company.toString()).put("employment_status","ACTIVE"))
            .when(db).one("SELECT to_jsonb(u) - 'password_hash' FROM users u WHERE id=?",approver);
        var acl=new WorkflowAccessControl(db);assertDoesNotThrow(()->acl.problem(approver,p));
        p.put("company_id",UUID.randomUUID().toString());
        assertEquals(403,assertThrows(ResponseStatusException.class,()->acl.problem(approver,p)).getStatusCode().value());
    }
    @Test void reanalysisArchivesOldStateAndQueuesAnalysisWithoutExecutingTheOldPlan() {
        var db=spy(store());var p=record("EXECUTING");var acl=mock(WorkflowAccessControl.class);
        var jobs=mock(WorkflowJobs.class);var planner=mock(AccessPlanningService.class);
        doReturn(p).when(db).problemRecord(id,true);
        var next=p.deepCopy().put("contract_version",2).put("status","RECEIVED");
        doReturn(next).when(db).problem(id,false);
        var service=spy(new AccessWorkflowService(db,acl,planner,jobs));
        doReturn(new AccessView(2,"ACCESS_REQUEST",Status.RECEIVED,null,"재접수",null,0,List.of(),null,id.toString(),null,null,null))
            .when(service).view(next);
        service.resume(requester,id);
        verify(service).audit(id,"HISTORY_REANALYSIS",p);
        verify(jobs).access(id,"ANALYZE",null,null);verifyNoMoreInteractions(jobs);verifyNoInteractions(planner);
        verify(db.jdbc).update(argThat((String sql)->sql.contains("contract_version=2") && sql.contains("approved_plan_hash=NULL")
                && sql.contains("active_job_event_id=NULL") && sql.contains("idempotency_key=NULL") && sql.contains("decided_by=NULL")),
            eq("payment-core Write 권한 주세요"),eq("GITHUB"),isNull(),anyString(),eq(id));
    }
    @Test void completedHistoryCannotBeReexecutedThroughResume() {
        var db=spy(store());doReturn(record("DONE")).when(db).problemRecord(id,true);
        var jobs=mock(WorkflowJobs.class);
        var service=new AccessWorkflowService(db,mock(WorkflowAccessControl.class),mock(AccessPlanningService.class),jobs);
        assertEquals(409,assertThrows(ResponseStatusException.class,()->service.resume(requester,id)).getStatusCode().value());
        verifyNoInteractions(jobs,db.jdbc);
    }
}
