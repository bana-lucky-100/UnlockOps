package com.unlockops.access;

import com.fasterxml.jackson.databind.*;
import com.unlockops.common.json.Jsons;
import com.unlockops.common.workflow.WorkflowStore;
import com.unlockops.contracts.v2.WorkflowTypes.Status;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class ExistingAccountPlanningTest {
    @Test void nonDeveloperUsesKnownJobFamilyWithoutInventingAJobFunctionOnlyWhenMappingAllowsIt() {
        var mapper=new ObjectMapper();String policyId=UUID.randomUUID().toString();
        var p=mapper.createObjectNode().put("company_id",new UUID(0,0).toString())
            .put("requester_id",UUID.randomUUID().toString()).put("platform","GITHUB");
        var user=mapper.createObjectNode().put("employment_status","ACTIVE").put("job_family","NON_DEV")
            .put("job_grade","대리").put("department_id",UUID.randomUUID().toString());
        var ent=mapper.createObjectNode().put("platform","GITHUB").put("resource_id",UUID.randomUUID().toString())
            .put("revision",1).put("access_scope","GENERAL").put("external_role","Read").put("kind","ROLE");
        var mapping=ent.putObject("mapping").put("mock",true).put("uses_job_family",true);
        String content="## POL-LEGACY\n기존 권한";
        var policy=mapper.createObjectNode().put("policy_id",policyId).put("revision",1).put("content",content).put("source_hash",WorkflowStore.hash(content));
        var price=mapper.createObjectNode().put("pricing_id",UUID.randomUUID().toString()).put("policy_id",policyId).put("policy_revision",1);
        var facts=mapper.createObjectNode().put("account_exists",true).put("license_active",true)
            .put("work_scope_assigned",true).put("job_function","UNKNOWN");
        var jdbc=mock(JdbcTemplate.class);
        var db=new WorkflowStore(jdbc,new Jsons(mapper)) {
            @Override public JsonNode one(String sql,Object...args) { return user; }
            @Override public List<JsonNode> rows(String sql,Object...args) {
                if(sql.contains("policy_revisions"))return List.of(policy);
                if(sql.contains("pricing_revisions"))return List.of(price);
                if(sql.contains("saas_context_facts"))return List.of(facts);
                throw new AssertionError(sql);
            }
            @Override public boolean exists(String sql,Object...args) {
                if(sql.contains("access_assignments"))return true;
                throw new AssertionError(sql);
            }
        };
        var planner=new AccessPlanningService(db) {
            @Override public JsonNode entitlement(UUID companyId,UUID entitlementId) { return ent; }
        };
        assertEquals("ALREADY_HAS_ACCESS",planner.assess(p,UUID.randomUUID()).reason());
        mapping.remove("uses_job_family");
        assertEquals("MISSING_SOURCE_EVIDENCE",planner.assess(p,UUID.randomUUID()).reason());
        verifyNoInteractions(jdbc);
    }
    @Test void importedCeilingsStillRejectAnEntryLevelWriterAndANonDeveloper() {
        var mapper=new ObjectMapper();
        for(var profile:List.of(List.of("DEV","사원"),List.of("NON_DEV","대리"))) {
            String company=new UUID(0,0).toString(),policyId=UUID.randomUUID().toString();
            var p=mapper.createObjectNode().put("id",UUID.randomUUID().toString()).put("company_id",company)
                .put("requester_id",UUID.randomUUID().toString()).put("platform","GITHUB");
            var user=mapper.createObjectNode().put("employment_status","ACTIVE").put("job_family",profile.get(0)).put("job_grade",profile.get(1));
            var ent=mapper.createObjectNode().put("platform","GITHUB").put("resource_id",UUID.randomUUID().toString())
                .put("revision",1).put("access_scope","GENERAL");
            var mapping=ent.putObject("mapping").put("mock",true);
            mapping.putArray("allowed_job_families").add("DEV");mapping.putArray("allowed_job_grades").add("대리").add("과장").add("차장").add("부장");
            String content="## POL-LEGACY\n기존 권한 상한";
            var policy=mapper.createObjectNode().put("policy_id",policyId).put("revision",1).put("content",content).put("source_hash",WorkflowStore.hash(content));
            var price=mapper.createObjectNode().put("pricing_id",UUID.randomUUID().toString()).put("policy_id",policyId).put("policy_revision",1);
            var jdbc=mock(JdbcTemplate.class);
            var db=new WorkflowStore(jdbc,new Jsons(mapper)) {
                @Override public JsonNode one(String sql,Object...args) { return user; }
                @Override public List<JsonNode> rows(String sql,Object...args) {
                    if(sql.contains("policy_revisions"))return List.of(policy);
                    if(sql.contains("pricing_revisions"))return List.of(price);
                    throw new AssertionError("Ineligible requests must stop before querying approvers or execution facts: "+sql);
                }
            };
            var planner=new AccessPlanningService(db) {
                @Override public JsonNode entitlement(UUID companyId,UUID entitlementId) { return ent; }
            };
            var result=planner.assess(p,UUID.randomUUID());
            assertEquals(Status.REJECTED,result.status());assertEquals("POLICY_NOT_ELIGIBLE",result.reason());
            assertNull(result.plan());verifyNoInteractions(jdbc);
        }
    }
}
