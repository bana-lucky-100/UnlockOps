package com.unlockops;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.unlockops.common.json.Jsons;
import com.unlockops.contracts.v2.WorkflowTypes.Status;
import com.unlockops.access.AccessPlanningService;
import com.unlockops.common.workflow.WorkflowStore;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/** Read-only reporting must use the same price/balance as the actual planning decision. */
class AccessPlanningReviewTest {
    private final ObjectMapper mapper=new ObjectMapper();

    @Test void approvalAndBudgetHoldExposeObservedFactsWithoutChangingPlanOrWriting() throws Exception {
        var vectors=mapper.readTree(Files.readString(Path.of("../contracts/phase2/examples/vectors.json")));
        var plan=vectors.path("valid").get(0).path("payload");
        String department=UUID.randomUUID().toString();
        var user=mapper.createObjectNode().put("employment_status","ACTIVE").put("job_family","DEV").put("department_id",department);
        var ent=mapper.createObjectNode().put("platform","SNOWFLAKE").put("access_scope","TF")
            .put("tf_id",UUID.randomUUID().toString()).put("security_grade","INTERNAL")
            .put("resource_id",plan.path("resource_id").asText()).put("revision",1)
            .put("code","ANALYST").put("kind","ROLE").put("external_role","ANALYST").put("resource_name","analysis-warehouse");
        ent.set("mapping",mapper.createObjectNode().put("mock",true));
        String content="## POL-06 제2조\n서버 가격과 예산을 확인한다.\n";
        var policy=mapper.createObjectNode().put("policy_id",plan.path("policy_id").asText()).put("revision",1)
            .put("doc_id","P2").put("article","POL-06").put("content",content).put("source_hash",WorkflowStore.hash(content));
        var price=mapper.createObjectNode().put("pricing_id",plan.path("pricing_id").asText()).put("revision",1)
            .put("policy_id",plan.path("policy_id").asText()).put("policy_revision",1)
            .put("monthly_amount",120).put("currency","USD").put("cost_basis","USAGE_ESTIMATE").put("source_kind","SYNTHETIC_CONTRACT");
        var facts=mapper.createObjectNode().put("account_exists",true).put("license_active",true)
            .put("work_scope_assigned",true).put("job_function","ANALYST");
        var route=mapper.createObjectNode().put("route_id",plan.path("route_id").asText()).put("revision",1)
            .put("policy_id",plan.path("policy_id").asText()).put("policy_revision",1).putNull("extra_step_threshold");
        route.putArray("steps").add("DEPARTMENT_HEAD").add("SAAS_OPERATOR");
        var problem=(ObjectNode)plan.deepCopy();
        problem.put("id",plan.path("problem_id").asText());
        for(int remaining:List.of(150,10)) {
            var jdbc=mock(JdbcTemplate.class);
            var db=new WorkflowStore(jdbc,new Jsons(mapper)) {
                @Override public JsonNode one(String sql,Object... args) {
                    if(sql.contains("FROM users"))return user;
                    throw new AssertionError(sql);
                }
                @Override public List<JsonNode> rows(String sql,Object... args) {
                    if(sql.contains("FROM policy_revisions"))return List.of(policy);
                    if(sql.contains("FROM pricing_revisions"))return List.of(price);
                    if(sql.contains("FROM saas_context_facts"))return List.of(facts);
                    if(sql.contains("FROM approval_route_revisions"))return List.of(route);
                    if(sql.contains("FROM operator_assignments"))return List.of(mapper.createObjectNode().put("id",
                        plan.path("approver_ids").get("DEPARTMENT_HEAD".equals(args[3])?0:1).asText()));
                    if(sql.contains("FROM department_budgets"))return List.of(mapper.createObjectNode().put("currency","USD").put("remaining_monthly_amount",remaining));
                    throw new AssertionError(sql);
                }
                @Override public boolean exists(String sql,Object... args) {
                    if(sql.contains("FROM tf_members"))return true;
                    if(sql.contains("FROM access_assignments"))return false;
                    throw new AssertionError(sql);
                }
            };
            var planner=new AccessPlanningService(db) {
                @Override public JsonNode entitlement(UUID company,UUID id) {return ent;}
            };
            var result=planner.assess(problem,UUID.fromString(plan.path("entitlement_id").asText()));
            assertEquals(remaining==150?Status.WAITING_APPROVAL:Status.ON_HOLD,result.status());
            assertEquals(remaining+".00",result.review_facts().remaining_budget());
            assertEquals("120.00",result.review_facts().monthly_amount());
            assertTrue(result.review_facts().tf_member());
            assertEquals("SYNTHETIC_CONTRACT",result.review_facts().price_source_kind());
            var serialized=mapper.valueToTree(result);
            assertEquals("analysis-warehouse",serialized.path("review_facts").path("resource_name").asText());
            assertFalse(serialized.path("review_facts").path("checked_at").asText().isBlank());
            if(remaining==150)assertEquals(vectors.path("plan_sha256").asText(),db.codec.planHash(result.plan()));
            else assertNull(result.plan());
            verifyNoInteractions(jdbc);
        }
    }
}
