package com.unlockops.access;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.common.workflow.WorkflowStore;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import static com.unlockops.common.workflow.WorkflowStore.*;

/** Server-side incremental cost, independent of role names and LLM narration. */
public final class AccessCosting {
    private AccessCosting() {}
    public record Facts(String operation,String unit_monthly_amount,String incremental_monthly_amount,
        String budget_monthly_amount,String cost_basis,String billing_scope,String license_code,
        String license_coverage,String license_observed_at,String license_source_reference) {}
    public record Decision(Facts facts,String reason,String message) {
        public boolean known() {return facts!=null;}
    }
    private static Decision unknown(String message) {return new Decision(null,"BUDGET_UNAVAILABLE",message);}
    private static boolean legacySeatPrice(JsonNode request,JsonNode policy,JsonNode price) {
        // Only the original V9 import may retain its explicitly declared seat purchase.
        return new java.util.UUID(0,0).equals(uuid(request,"company_id"))
            && "EXISTING-POLICY".equals(str(policy,"doc_id")) && policy.path("revision").asInt()==1
            && "V9:existing-department_budgets".equals(str(price,"source_reference"));
    }
    public static Decision assess(WorkflowStore db,JsonNode request,JsonNode ent,JsonNode price,JsonNode policy) {
        var rules=db.rows("SELECT to_jsonb(r) FROM access_cost_rules r WHERE company_id=? AND entitlement_id=? AND entitlement_revision=? AND policy_id=? AND policy_revision=?",
            uuid(request,"company_id"),uuid(ent,"id"),ent.path("revision").intValue(),uuid(policy,"policy_id"),policy.path("revision").intValue());
        String operation,scope=null,license=null,coverage="NOT_REQUIRED",observed=null,source=null;
        Boolean purchaseRequired=null;
        String basis=str(price,"cost_basis");BigDecimal unit=price.path("monthly_amount").decimalValue();
        if(rules.isEmpty()) {
            // An explicit zero-cost permission is safe to preserve. Missing new
            // rules must never turn unit prices into purchase/usage authorization.
            operation=switch(basis) {
                case "NO_ADDITIONAL_COST" -> unit.signum()==0?"PERMISSION_ONLY":"UNKNOWN";
                case "SEAT_MONTHLY" -> "SEAT".equals(str(ent,"kind")) && legacySeatPrice(request,policy,price)?"PURCHASE_SEAT":"UNKNOWN";
                default -> "UNKNOWN";
            };
        } else {
            if(rules.size()!=1) return unknown("비용 적용 규칙을 유일하게 확인할 수 없습니다.");
            var rule=rules.getFirst();operation=str(rule,"operation");scope=str(rule,"billing_scope");license=str(rule,"required_license");
            if("PURCHASE_SEAT".equals(operation) && (scope==null || scope.isBlank() || license==null || license.isBlank()))
                return unknown("좌석 구매 규칙의 대상 조직과 라이선스 코드를 확인해야 합니다.");
            if(scope!=null && license!=null) {
                var facts=db.rows("SELECT to_jsonb(f) FROM saas_license_facts f WHERE company_id=? AND user_id=? AND platform=? AND billing_scope=? AND license_code=?",
                    uuid(request,"company_id"),uuid(request,"requester_id"),str(request,"platform"),scope,license);
                if(facts.size()!=1) return unknown("대상 워크스페이스·조직의 라이선스 보유 여부를 확인해야 합니다.");
                var fact=facts.getFirst();coverage=str(fact,"coverage");observed=str(fact,"observed_at");source=str(fact,"source_reference");
                purchaseRequired=fact.path("purchase_required").isBoolean()?fact.path("purchase_required").asBoolean():null;
                if(observed==null || source==null || source.isBlank() || OffsetDateTime.parse(observed).isAfter(OffsetDateTime.now())
                    || str(fact,"valid_until")!=null && !OffsetDateTime.parse(str(fact,"valid_until")).isAfter(OffsetDateTime.now()))
                    return unknown("유효한 라이선스 관측 근거가 필요합니다.");
                if(!"COVERED".equals(coverage) && !"NOT_COVERED".equals(coverage))
                    return unknown("라이선스 보유 여부가 미확인입니다. 추가 비용을 0으로 추정하지 않습니다.");
            } else if(scope!=null || license!=null) return unknown("라이선스 적용 범위를 확인해야 합니다.");
        }
        BigDecimal budget,incremental;
        switch(operation) {
            case "PERMISSION_ONLY" -> {
                if(license!=null && !"COVERED".equals(coverage))
                    return new Decision(null,"OUT_OF_SCOPE","필요한 라이선스를 먼저 확보해야 합니다. 권한 추가로 좌석을 자동 구매하지 않습니다.");
                if(license==null && (unit.signum()!=0 || !"NO_ADDITIONAL_COST".equals(basis)))
                    return unknown("추가 비용 없음의 적용 근거를 확인해야 합니다.");
                budget=BigDecimal.ZERO;incremental=BigDecimal.ZERO;basis="NO_ADDITIONAL_COST";
            }
            case "PURCHASE_SEAT" -> {
                if(!"SEAT".equals(str(ent,"kind")) || !"SEAT_MONTHLY".equals(basis))
                    return unknown("좌석 구매 요청과 가격 기준이 일치하지 않습니다.");
                if(license!=null && !"COVERED".equals(coverage) && !Boolean.TRUE.equals(purchaseRequired))
                    return unknown("신규 구매 필요 여부를 확인해야 합니다. 미배정 좌석·업그레이드 조건을 단가만으로 계산하지 않습니다.");
                budget="COVERED".equals(coverage)?BigDecimal.ZERO:unit;incremental=budget;
                if(budget.signum()==0) basis="NO_ADDITIONAL_COST";
            }
            case "USAGE_ALLOCATION" -> {
                if(!"USAGE_ESTIMATE".equals(basis)) return unknown("사용량 예산 배정 기준을 확인해야 합니다.");
                budget=unit;incremental=null; // A reservation is not an observed vendor invoice.
            }
            default -> {return unknown("권한 변경과 라이선스 비용의 적용 규칙을 확인해야 합니다.");}
        }
        return new Decision(new Facts(operation,unit.setScale(2).toPlainString(),incremental==null?null:incremental.setScale(2).toPlainString(),
            budget.setScale(2).toPlainString(),basis,scope,license,coverage,observed,source),null,null);
    }
}
