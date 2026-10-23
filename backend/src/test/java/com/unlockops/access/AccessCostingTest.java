package com.unlockops.access;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.unlockops.common.json.Jsons;
import com.unlockops.common.workflow.WorkflowStore;
import java.time.OffsetDateTime;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class AccessCostingTest {
    final ObjectMapper json=new ObjectMapper();
    final String company=UUID.randomUUID().toString(),user=UUID.randomUUID().toString(),entitlement=UUID.randomUUID().toString(),policyId=UUID.randomUUID().toString();
    final ObjectNode request=json.createObjectNode().put("company_id",company).put("requester_id",user).put("platform","NOTION");
    final ObjectNode ent=json.createObjectNode().put("id",entitlement).put("revision",1).put("kind","ROLE");
    final ObjectNode policy=json.createObjectNode().put("policy_id",policyId).put("revision",4);
    final ObjectNode price=json.createObjectNode().put("monthly_amount",20).put("cost_basis","SEAT_MONTHLY");
    final ObjectNode rule=json.createObjectNode().put("operation","PERMISSION_ONLY").put("billing_scope","workspace-a").put("required_license","BUSINESS");
    ObjectNode fact(String coverage) {
        return json.createObjectNode().put("coverage",coverage).put("purchase_required","NOT_COVERED".equals(coverage)).put("observed_at",OffsetDateTime.now().minusMinutes(1).toString()).put("source_reference","test:workspace-a");
    }
    AccessCosting.Decision assess(List<JsonNode> rules,List<JsonNode> observations) {
        var db=new WorkflowStore(null,new Jsons(json)) {
            @Override public List<JsonNode> rows(String sql,Object...args) {
                if(sql.contains("FROM access_cost_rules"))return rules;
                if(sql.contains("FROM saas_license_facts")) {
                    assertEquals(List.of(UUID.fromString(company),UUID.fromString(user),"NOTION","workspace-a","BUSINESS"),Arrays.asList(args));
                    return observations;
                }
                throw new AssertionError(sql);
            }
        };
        return AccessCosting.assess(db,request,ent,price,policy);
    }
    @Test void existingScopedLicenseAddsPermissionWithoutBuyingAnotherSeat() {
        var result=assess(List.of(rule),List.of(fact("COVERED")));
        assertTrue(result.known());assertEquals("20.00",result.facts().unit_monthly_amount());
        assertEquals("0.00",result.facts().incremental_monthly_amount());
        assertEquals("0.00",result.facts().budget_monthly_amount());assertEquals("NO_ADDITIONAL_COST",result.facts().cost_basis());
        price.put("monthly_amount",70); // The same rule applies to an already licensed Tableau-style permission.
        assertEquals("0.00",assess(List.of(rule),List.of(fact("COVERED"))).facts().budget_monthly_amount());
    }
    @Test void missingUnknownExpiredOrFutureLicenseCannotBecomeFree() {
        for(var facts:List.<List<JsonNode>>of(List.of(),List.of(fact("UNKNOWN")),
            List.of(fact("COVERED").put("valid_until",OffsetDateTime.now().minusSeconds(1).toString())),
            List.of(fact("COVERED").put("observed_at",OffsetDateTime.now().plusDays(1).toString())))) {
            var result=assess(List.of(rule),facts);assertFalse(result.known());assertEquals("BUDGET_UNAVAILABLE",result.reason());
        }
    }
    @Test void permissionRequestWithoutLicenseDoesNotSilentlyPurchaseIt() {
        var result=assess(List.of(rule),List.of(fact("NOT_COVERED")));
        assertFalse(result.known());assertEquals("OUT_OF_SCOPE",result.reason());
    }
    @Test void realSeatRequestChargesOnlyWhenNotAlreadyCovered() {
        ent.put("kind","SEAT");rule.put("operation","PURCHASE_SEAT");
        assertEquals("20.00",assess(List.of(rule),List.of(fact("NOT_COVERED"))).facts().budget_monthly_amount());
        assertEquals("0.00",assess(List.of(rule),List.of(fact("COVERED"))).facts().budget_monthly_amount());
        assertEquals("BUDGET_UNAVAILABLE",assess(List.of(rule),List.of(fact("NOT_COVERED").putNull("purchase_required"))).reason());
        assertEquals("BUDGET_UNAVAILABLE",assess(List.of(rule),List.of(fact("NOT_COVERED").put("purchase_required",false))).reason());
    }
    @Test void usageBudgetIsNotASeatPurchaseOrInvoice() {
        rule.put("operation","USAGE_ALLOCATION").putNull("billing_scope").putNull("required_license");
        price.put("monthly_amount",120).put("cost_basis","USAGE_ESTIMATE");
        var result=assess(List.of(rule),List.of());
        assertTrue(result.known());assertEquals("120.00",result.facts().budget_monthly_amount());assertNull(result.facts().incremental_monthly_amount());
    }
    @Test void legacyRoleWithSeatPriceIsNotAutomaticallyCharged() {
        assertEquals("BUDGET_UNAVAILABLE",assess(List.of(),List.of()).reason());
        price.put("monthly_amount",0).put("cost_basis","NO_ADDITIONAL_COST");
        assertEquals("0.00",assess(List.of(),List.of()).facts().budget_monthly_amount());
    }
    @Test void missingRuleOrPurchaseScopeNeverAssumesAnotherSeatIsNeeded() {
        ent.put("kind","SEAT");rule.put("operation","PURCHASE_SEAT");
        assertEquals("BUDGET_UNAVAILABLE",assess(List.of(),List.of(fact("COVERED"))).reason());
        rule.putNull("billing_scope").putNull("required_license");
        assertEquals("BUDGET_UNAVAILABLE",assess(List.of(rule),List.of(fact("COVERED"))).reason());
        price.put("cost_basis","USAGE_ESTIMATE");
        assertEquals("BUDGET_UNAVAILABLE",assess(List.of(),List.of()).reason());
    }
    @Test void importedSeatCompatibilityDoesNotApplyToLaterPolicies() {
        request.put("company_id",new UUID(0,0).toString());ent.put("kind","SEAT");
        policy.put("doc_id","EXISTING-POLICY").put("revision",1);
        price.put("source_reference","V9:existing-department_budgets");
        assertEquals("20.00",assess(List.of(),List.of()).facts().budget_monthly_amount());
        policy.put("revision",2);
        assertEquals("BUDGET_UNAVAILABLE",assess(List.of(),List.of()).reason());
    }
}
