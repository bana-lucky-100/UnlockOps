package com.unlockops;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class ProblemQueriesTest {
    JdbcTemplate jdbc;
    GrantRules rules;
    ProblemService service;
    UUID requester=UUID.randomUUID(),approver=UUID.randomUUID(),id=UUID.randomUUID();
    Map<String,Object> row;
    @BeforeEach void setup() {
        jdbc=mock(JdbcTemplate.class); rules=mock(GrantRules.class);
        service=new ProblemService(jdbc,new Jsons(new ObjectMapper()),rules,true);
        row=new HashMap<>(); row.put("id",id); row.put("requester_id",requester); row.put("approver_id",approver);
        row.put("status","WAITING_APPROVAL"); row.put("evidence_json","[\"private-source\"]");
        row.put("plan_json","{\"resource_key\":\"payment-core\"}"); row.put("plan_hash","private-hash");
        when(jdbc.queryForList(contains("p.*"),eq(id))).thenReturn(List.of(row));
        when(jdbc.queryForList(contains("FROM problem_events"),eq(id))).thenReturn(List.of());
    }
    AppUser actor(UUID user,String role) { return new AppUser(user,"actor","hash",role); }

    @Test void requesterReadsOwnRequestWithoutApproverPrivileges() {
        var result=service.detail(actor(requester,"REQUESTER"),id);
        assertEquals(id,result.get("id"));
        assertFalse(result.containsKey("evidence_json")); assertFalse(result.containsKey("plan_hash"));
        assertEquals(List.of(),result.get("events"));
        verify(rules,never()).requireApprover(any());
    }
    @Test void anotherApproverCannotReadAnUnassignedRequest() {
        var error=assertThrows(ResponseStatusException.class,
            ()->service.detail(actor(UUID.randomUUID(),"APPROVER"),id));
        assertEquals(403,error.getStatusCode().value());
    }
    @Test void assignedApproverRetainsEvidenceAndPlanHash() {
        var result=service.detail(actor(approver,"APPROVER"),id);
        assertEquals(List.of("private-source"),result.get("evidence"));
        assertEquals("private-hash",result.get("plan_hash"));
    }
    @Test void mineAlwaysFiltersUsingTheAuthenticatedUser() {
        when(jdbc.queryForList(contains("WHERE p.requester_id=?"),eq(requester))).thenReturn(List.of(row));
        var result=service.list(actor(requester,"REQUESTER"),true);
        assertEquals(1,result.size()); assertFalse(result.getFirst().containsKey("plan_hash"));
        verify(jdbc).queryForList(contains("WHERE p.requester_id=?"),eq(requester));
        verify(rules,never()).requireApprover(any());
    }
    @Test void requesterCannotReadOthersEvenWhenTheyKnowTheId() {
        var user=actor(UUID.randomUUID(),"REQUESTER");
        doThrow(new ResponseStatusException(HttpStatus.FORBIDDEN)).when(rules).requireApprover(user);
        var error=assertThrows(ResponseStatusException.class,()->service.detail(user,id));
        assertEquals(403,error.getStatusCode().value());
        verify(jdbc,never()).queryForList(contains("FROM problem_events"),any(UUID.class));
    }
    @Test void summaryRequiresApproverBeforeReadingDepartmentData() {
        var user=actor(requester,"REQUESTER");
        doThrow(new ResponseStatusException(HttpStatus.FORBIDDEN)).when(rules).requireApprover(user);
        assertThrows(ResponseStatusException.class,()->service.approvalSummary(user));
        verifyNoInteractions(jdbc);
    }
}
