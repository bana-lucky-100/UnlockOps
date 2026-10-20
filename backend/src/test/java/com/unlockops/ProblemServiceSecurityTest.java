package com.unlockops;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class ProblemServiceSecurityTest {
    JdbcTemplate jdbc;
    GrantRules rules;
    Jsons json;
    ProblemService service;
    UUID id=UUID.randomUUID(),requester=UUID.randomUUID(),approver=UUID.randomUUID();
    Map<String,Object> row;
    String hash;
    @BeforeEach void setup() {
        jdbc=mock(JdbcTemplate.class); rules=mock(GrantRules.class); json=new Jsons(new ObjectMapper());
        service=new ProblemService(jdbc,json,rules,true);
        Map<String,Object> plan=new HashMap<>();
        plan.put("problem_id",id.toString()); plan.put("requester_id",requester.toString());
        plan.put("platform","GITHUB"); plan.put("resource_id",UUID.randomUUID().toString());
        plan.put("resource_key","payment-core"); plan.put("requested_role","Write");
        hash=json.planHash(plan);
        row=new HashMap<>(); row.put("id",id); row.put("requester_id",requester); row.put("approver_id",approver);
        row.put("status","WAITING_APPROVAL"); row.put("plan_hash",hash); row.put("plan_json",json.write(plan));
        row.put("platform","GITHUB"); row.put("contents","payment-core push가 안 됩니다");
        when(jdbc.queryForList(contains("FOR UPDATE"),eq(id))).thenReturn(List.of(row));
        when(rules.validatePlan(anyMap(),anyMap())).thenReturn(approver);
    }
    AppUser actor(UUID actor) { return new AppUser(actor,"reviewer","hash","APPROVER"); }

    @Test void anotherApproverCannotExecuteDesignatedPlan() {
        var error=assertThrows(ResponseStatusException.class,()->service.decide(actor(UUID.randomUUID()),id,true,hash,""));
        assertEquals(403,error.getStatusCode().value());
        verify(jdbc,never()).update(anyString(),any(Object[].class));
    }
    @Test void requesterCannotApproveTheirOwnPlanEvenIfAssigned() {
        row.put("approver_id",requester);
        assertThrows(ResponseStatusException.class,()->service.decide(actor(requester),id,true,hash,""));
        verify(jdbc,never()).update(anyString(),any(Object[].class));
    }
    @Test void changedCardCannotBeApproved() {
        assertThrows(ResponseStatusException.class,()->service.decide(actor(approver),id,true,"0".repeat(64),""));
        verify(rules,never()).validatePlan(anyMap(),anyMap());
        verify(jdbc,never()).update(anyString(),any(Object[].class));
    }
    @Test void duplicateDecisionCannotEnqueueAnotherExecution() {
        row.put("status","EXECUTING");
        assertThrows(ResponseStatusException.class,()->service.decide(actor(approver),id,true,hash,""));
        verify(jdbc,never()).update(anyString(),any(Object[].class));
    }
    @Test void rejectionRequiresAReason() {
        assertThrows(ResponseStatusException.class,()->service.decide(actor(approver),id,false,hash,""));
        verify(jdbc,never()).update(anyString(),any(Object[].class));
    }
    @Test void validApprovalCreatesOneOutboxExecution() {
        var result=service.decide(actor(approver),id,true,hash,"업무상 필요 확인");
        assertEquals("EXECUTING",result.get("status"));
        verify(jdbc,times(1)).update(eq("INSERT INTO outbox(event_id,routing_key,payload) VALUES (?,?,?::jsonb)"),
            any(UUID.class),eq("execution"),anyString());
    }
}
