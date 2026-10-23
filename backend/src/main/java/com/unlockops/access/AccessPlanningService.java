package com.unlockops.access;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.contracts.v2.WorkflowTypes.*;
import com.unlockops.common.workflow.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import static com.unlockops.common.workflow.WorkflowStore.*;

/** Structured baseline rules and role resolution. LLM output never decides price or approvers. */
@Service
public class AccessPlanningService {
    private final WorkflowStore db;
    public AccessPlanningService(WorkflowStore db) { this.db=db; }
    /** Read-only reporting facts. They never participate in approval or execution authorization. */
    public record ReviewFacts(String checked_at,String resource_name,String entitlement_code,String entitlement_kind,
        String access_scope,Boolean tf_member,String monthly_amount,String currency,String remaining_budget,String price_source_kind,
        AccessCosting.Facts cost_assessment) {}
    public record Assessment(Status status,String reason,String message,GrantPlanV2 plan,List<PolicyEvidence> evidence,ReviewFacts review_facts) {
        public Assessment(Status status,String reason,String message,GrantPlanV2 plan,List<PolicyEvidence> evidence) {
            this(status,reason,message,plan,evidence,null);
        }
    }
    private Assessment stop(Status status,String reason,String message) { return new Assessment(status,reason,message,null,List.of()); }

    public JsonNode entitlement(UUID company,UUID id) {
        return db.one("""
            SELECT to_jsonb(x) FROM (SELECT e.*,r.name AS resource_name,r.platform,r.access_scope,r.tf_id,r.security_grade,
              r.owner_department_id,r.designated_department_id,er.revision,er.external_role,er.mapping
              FROM entitlements e JOIN resources r ON r.id=e.resource_id
              JOIN LATERAL (SELECT * FROM entitlement_revisions er WHERE er.entitlement_id=e.id ORDER BY revision DESC LIMIT 1) er ON true
              WHERE e.id=? AND e.company_id=?) x
            """,id,company);
    }
    public Assessment assess(JsonNode p,UUID entitlementId) {
        UUID company=uuid(p,"company_id"),requester=uuid(p,"requester_id");
        if(entitlementId==null) return stop(Status.MANUAL_REVIEW,"OUT_OF_SCOPE","부여할 권한 항목을 확인해야 합니다.");
        var user=db.one("SELECT to_jsonb(u) - 'password_hash' FROM users u WHERE id=?",requester);
        var ent=entitlement(company,entitlementId);
        if(!str(p,"platform").equals(str(ent,"platform")) || uuid(p,"resource_id")!=null && !uuid(p,"resource_id").equals(uuid(ent,"resource_id")))
            return stop(Status.MANUAL_REVIEW,"OUT_OF_SCOPE","요청 범위와 권한 항목이 다릅니다.");
        if(!"ACTIVE".equals(str(user,"employment_status"))) return stop(Status.REJECTED,"POLICY_NOT_ELIGIBLE","현재 재직자에게만 권한을 부여할 수 있습니다.");
        var policies=db.rows("SELECT to_jsonb(p) FROM policy_revisions p WHERE company_id=? ORDER BY revision DESC",company);
        if(policies.isEmpty()) return stop(Status.MANUAL_REVIEW,"MISSING_SOURCE_EVIDENCE","정책 원문이 필요합니다.");
        // Baseline supports one effective policy family and one DEFAULT route per company.
        var policy=policies.getFirst();
        if(policies.stream().anyMatch(x->!uuid(x,"policy_id").equals(uuid(policy,"policy_id"))) ||
            !hash(str(policy,"content")).equals(str(policy,"source_hash")))
            return stop(Status.MANUAL_REVIEW,"MISSING_SOURCE_EVIDENCE","정책 원문과 버전을 확인해야 합니다.");
        var prices=db.rows("""
            SELECT to_jsonb(p) FROM pricing_revisions p WHERE company_id=? AND entitlement_id=? AND entitlement_revision=?
              AND effective_from<=? AND (effective_until IS NULL OR effective_until>=?) ORDER BY revision DESC
            """,company,entitlementId,ent.path("revision").intValue(),today(),today());
        if(prices.isEmpty()) return stop(Status.MANUAL_REVIEW,"MISSING_SOURCE_EVIDENCE","유효한 가격 근거가 없습니다.");
        var price=prices.getFirst();
        if(prices.stream().anyMatch(x->!uuid(x,"pricing_id").equals(uuid(price,"pricing_id"))) ||
            !uuid(price,"policy_id").equals(uuid(policy,"policy_id")) || price.path("policy_revision").intValue()!=policy.path("revision").intValue())
            return stop(Status.MANUAL_REVIEW,"MISSING_SOURCE_EVIDENCE","정책과 가격 버전을 확인해야 합니다.");
        var mapping=ent.path("mapping");
        if(!mapping.path("mock").asBoolean() || mapping.path("allows_admin").asBoolean())
            return stop(Status.MANUAL_REVIEW,"OUT_OF_SCOPE","베이스라인에서 실행할 수 없는 권한 매핑입니다.");
        if(mapping.has("grantable") && !mapping.path("grantable").asBoolean())
            return stop(Status.REJECTED,"POLICY_NOT_ELIGIBLE","현재 정책에서 신청할 수 없는 권한입니다.");
        // Data-bound limits preserve the original organisation's role ceilings.
        // Other tenants keep their existing rules unless their mapping declares a limit.
        for(var limit:Map.of("allowed_job_families","job_family","allowed_job_grades","job_grade").entrySet()) {
            if(!mapping.has(limit.getKey())) continue;
            var allowed=mapping.path(limit.getKey());
            if(!allowed.isArray()) return stop(Status.MANUAL_REVIEW,"MISSING_SOURCE_EVIDENCE","권한 상한 매핑을 확인해야 합니다.");
            boolean matches=false;
            for(var value:allowed) if(value.asText().equals(str(user,limit.getValue()))) matches=true;
            if(!matches) return stop(Status.REJECTED,"POLICY_NOT_ELIGIBLE","직무·직급별 권한 상한을 넘는 요청입니다.");
        }
        if("TF".equals(str(ent,"access_scope")) && !db.exists("""
            SELECT EXISTS(SELECT 1 FROM tf_members m JOIN tfs t ON t.id=m.tf_id WHERE m.user_id=? AND m.tf_id=?
              AND m.active AND t.starts_on<=? AND (t.ends_on IS NULL OR t.ends_on>=?))
            """,requester,uuid(ent,"tf_id"),today(),today()))
            return stop(Status.REJECTED,"NOT_TF_MEMBER","현재 TF 구성원이 아닙니다.");
        if(("DEPARTMENT".equals(str(ent,"access_scope")) && !uuid(user,"department_id").equals(uuid(ent,"owner_department_id"))) ||
            ("CONFIDENTIAL".equals(str(ent,"security_grade")) && !uuid(user,"department_id").equals(uuid(ent,"designated_department_id"))))
            return stop(Status.REJECTED,"POLICY_NOT_ELIGIBLE","권한을 부여할 수 있는 부서 범위가 아닙니다.");
        var facts=db.rows("SELECT to_jsonb(f) FROM saas_context_facts f WHERE company_id=? AND user_id=? AND platform=?",company,requester,str(p,"platform"));
        if(facts.isEmpty()) return stop(Status.MANUAL_REVIEW,"MISSING_SOURCE_EVIDENCE","계정·직무 사실이 확인되지 않았습니다.");
        var f=facts.getFirst();
        for(String field:List.of("account_exists","license_active","work_scope_assigned"))
            if(f.path(field).isNull()) return stop(Status.MANUAL_REVIEW,"MISSING_SOURCE_EVIDENCE","필수 계정·업무 사실이 누락되었습니다.");
        if(!f.path("account_exists").asBoolean() || !f.path("license_active").asBoolean())
            return stop(Status.MANUAL_REVIEW,"OUT_OF_SCOPE","계정 또는 기본 라이선스를 먼저 확인해야 합니다.");
        if(mapping.path("requires_existing_data_access").asBoolean() && !f.path("data_access").asBoolean())
            return stop(Status.MANUAL_REVIEW,"OUT_OF_SCOPE","기존 데이터 접근 범위를 먼저 확인해야 합니다.");
        if("DATABRICKS".equals(str(p,"platform")) && (f.path("job_run_as_principal").asText("").isBlank() || !f.path("job_run_as_data_access").asBoolean()))
            return stop(Status.MANUAL_REVIEW,"MISSING_SOURCE_EVIDENCE","작업 Run as 실행 주체의 데이터 접근 권한 확인이 필요합니다.");
        String function=str(f,"job_function"),platform=str(p,"platform");
        // Imported mappings explicitly use stored job_family/resource scope;
        // they do not need an invented SALES/OPS/etc. job_function for NON_DEV.
        if("UNKNOWN".equals(function) && (!mapping.path("uses_job_family").asBoolean()
                || !Set.of("GITHUB","JIRA","SLACK","NOTION").contains(platform)))
            return stop(Status.MANUAL_REVIEW,"MISSING_SOURCE_EVIDENCE","직무 확인이 필요합니다.");
        boolean eligible=switch(platform) {
            case "GITHUB" -> "DEV".equals(str(user,"job_family")) || "Read".equals(str(ent,"external_role"));
            case "SNOWFLAKE","DATABRICKS" -> Set.of("DEV","ANALYST").contains(function);
            case "TABLEAU_CLOUD" -> "ANALYST".equals(function);
            case "SALESFORCE" -> "SALES".equals(function);
            case "DATADOG" -> "OPS".equals(function);
            case "FIGMA" -> "DESIGN".equals(function);
            default -> true;
        };
        if(!eligible || !f.path("work_scope_assigned").asBoolean()) return stop(Status.REJECTED,"POLICY_NOT_ELIGIBLE","직무·업무 배정 조건에 맞지 않습니다.");
        if(db.exists("SELECT EXISTS(SELECT 1 FROM access_assignments WHERE user_id=? AND entitlement_id=? AND status='ACTIVE')",requester,entitlementId))
            return "SEAT".equals(str(ent,"kind")) ? stop(Status.REJECTED,"DUPLICATE_SEAT","이미 좌석을 보유하고 있습니다.") :
                stop(Status.DONE,"ALREADY_HAS_ACCESS","조회 결과 필요한 권한을 이미 보유하고 있습니다.");
        var cost=AccessCosting.assess(db,p,ent,price,policy);
        if(!cost.known()) return stop(Status.MANUAL_REVIEW,cost.reason(),cost.message());
        var routes=db.rows("SELECT to_jsonb(r) FROM approval_route_revisions r WHERE company_id=? AND code='DEFAULT' ORDER BY revision DESC",company);
        if(routes.isEmpty()) return stop(Status.MANUAL_REVIEW,"APPROVER_UNAVAILABLE","승인 경로가 없습니다.");
        var route=routes.getFirst();
        if(routes.stream().anyMatch(x->!uuid(x,"route_id").equals(uuid(route,"route_id"))) || !uuid(route,"policy_id").equals(uuid(policy,"policy_id")) || route.path("policy_revision").intValue()!=policy.path("revision").intValue())
            return stop(Status.MANUAL_REVIEW,"MISSING_SOURCE_EVIDENCE","정책과 승인 경로 버전이 다릅니다.");
        var roles=new ArrayList<String>();route.path("steps").forEach(x->roles.add(x.asText()));
        BigDecimal amount=new BigDecimal(cost.facts().budget_monthly_amount());
        if(!route.path("extra_step_threshold").isNull()) {
            if(!str(price,"currency").equals(str(route,"currency"))) return stop(Status.MANUAL_REVIEW,"BUDGET_UNAVAILABLE","승인 기준 통화와 가격 통화가 다릅니다.");
            if(amount.compareTo(route.path("extra_step_threshold").decimalValue())>=0) roles.add("IT_HEAD");
        }
        var approvers=new ArrayList<String>();
        for(String role:roles) {
            var actors=db.rows("""
                SELECT to_jsonb(u) - 'password_hash' FROM operator_assignments o JOIN users u ON u.id=o.user_id
                WHERE o.company_id=? AND o.department_id=? AND o.platform=? AND o.capability=?
                  AND u.employment_status='ACTIVE' AND u.role='APPROVER' ORDER BY u.id
                """,company,uuid(user,"department_id"),platform,role);
            if(actors.size()!=1 || requester.equals(uuid(actors.getFirst(),"id")) || approvers.contains(str(actors.getFirst(),"id")))
                return stop(Status.MANUAL_REVIEW,"APPROVER_UNAVAILABLE","승인자를 유일하게 지정할 수 없습니다.");
            approvers.add(str(actors.getFirst(),"id"));
        }
        var budgets=db.rows("SELECT to_jsonb(b) FROM department_budgets b WHERE department_id=?",uuid(user,"department_id"));
        if(budgets.isEmpty() || !str(budgets.getFirst(),"currency").equals(str(price,"currency")))
            return stop(Status.MANUAL_REVIEW,"BUDGET_UNAVAILABLE","예산 또는 통화 확인이 필요합니다.");
        var remaining=budgets.getFirst().path("remaining_monthly_amount").decimalValue();
        var reviewFacts=new ReviewFacts(OffsetDateTime.now(ZoneId.of("Asia/Seoul")).toString(),str(ent,"resource_name"),
            str(ent,"code"),str(ent,"kind"),str(ent,"access_scope"),"TF".equals(str(ent,"access_scope"))?true:null,
            amount.setScale(2).toPlainString(),str(price,"currency"),remaining.setScale(2).toPlainString(),str(price,"source_kind"),cost.facts());
        if(remaining.compareTo(amount)<0)
            return new Assessment(Status.ON_HOLD,"BUDGET_INSUFFICIENT","잔여 예산이 부족하여 보류되었습니다.",null,List.of(),reviewFacts);
        var plan=db.checked(new GrantPlanV2(2,str(p,"id"),company.toString(),requester.toString(),Platform.valueOf(platform),str(ent,"resource_id"),entitlementId.toString(),ent.path("revision").intValue(),str(price,"pricing_id"),price.path("revision").intValue(),amount.setScale(2).toPlainString(),str(price,"currency"),cost.facts().cost_basis(),str(policy,"policy_id"),policy.path("revision").intValue(),str(route,"route_id"),route.path("revision").intValue(),approvers),GrantPlanV2.class);
        var evidence=List.of(new PolicyEvidence(str(policy,"doc_id"),str(policy,"article"),str(policy,"revision"),str(policy,"source_hash"),str(policy,"content")));
        return new Assessment(Status.WAITING_APPROVAL,"ELIGIBLE","정책·직무·예산을 확인했습니다. 예상 예산 영향은 "+remaining.setScale(2).toPlainString()+" → "+remaining.subtract(amount).setScale(2).toPlainString()+" "+str(price,"currency")+"입니다. 순서대로 승인을 기다립니다.",plan,evidence,reviewFacts);
    }
    public boolean sameCurrentPlan(JsonNode p,GrantPlanV2 approved) {
        var next=assess(p,UUID.fromString(approved.entitlementId()));
        return next.plan()!=null && db.codec.planHash(next.plan()).equals(db.codec.planHash(approved));
    }
    public static LocalDate today() { return LocalDate.now(ZoneId.of("Asia/Seoul")); }
}
