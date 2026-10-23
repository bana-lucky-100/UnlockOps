package com.unlockops.reclaim;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.contracts.v2.WorkflowTypes.*;
import java.time.*;
import java.util.*;
import static com.unlockops.common.workflow.WorkflowStore.*;

/** Pure rules over frozen facts. Missing observations never mean zero usage. */
public final class ReclaimPolicy {
    private ReclaimPolicy() {}
    public static ReclaimCandidate evaluate(JsonNode f,JsonNode policy,List<JsonNode> rules,OffsetDateTime asOf) {
        String status=null,rule=null,exclude=null,message="필수 사실 확인이 필요합니다.";
        var cost=f.path("price");
        CostImpact impact=cost.isObject()?new CostImpact("ESTIMATED",cost.path("monthly_amount").decimalValue().setScale(2).toPlainString(),str(cost,"currency"),str(cost,"source_kind")):
            new CostImpact("UNKNOWN",null,null,null);
        var evidence=com.unlockops.common.workflow.PolicyArticles.reclaim(policy);
        var facts=List.of(new FactEvidence("reclaim_snapshot_items",str(f,"assignment_id"),asOf.toString()));
        var left=rules.stream().filter(r->"EMPLOYEE_LEFT".equals(str(r,"code"))).findFirst();
        var idle=rules.stream().filter(r->"TF_ENDED_UNUSED_30D".equals(str(r,"code"))).findFirst();
        if("LEFT".equals(str(f,"employment_status")) && left.isPresent()) {
            status="PENDING_REVIEW";rule="EMPLOYEE_LEFT";message="퇴사자의 좌석입니다. 담당자가 회수 필요성을 검토해야 합니다.";
        } else if("ACTIVE".equals(str(f,"employment_status")) && idle.isPresent()) {
            var r=idle.get();rule="TF_ENDED_UNUSED_30D";
            if(r.path("exclude_retention").asBoolean() && f.path("retention").asBoolean()) {
                status="RETAINED";exclude="RETENTION_APPROVED";message="유효한 유지 승인이 있어 후보에서 제외했습니다.";
            } else if(r.path("exclude_other_active_tf").asBoolean() && f.path("other_active_tf").asBoolean()) {
                status="EXCLUDED";exclude="ACTIVE_OTHER_TF";message="다른 활성 TF에서 이용 중인 좌석입니다.";
            } else if(f.path("origin_tf_id").isNull()) {
                status="EXCLUDED";exclude="USAGE_RESUMED";rule=null;message="프로젝트 지급 좌석이 아니므로 이 규칙의 회수 대상이 아닙니다.";
            } else if(!f.path("tf_ends_on").isNull() && !"UNKNOWN".equals(str(f,"observation_status")) && str(f,"observation_status")!=null && str(f,"observed_at")!=null) {
                var end=LocalDate.parse(str(f,"tf_ends_on")).plusDays(1).atStartOfDay(ZoneId.of("Asia/Seoul")).toOffsetDateTime();
                var granted=OffsetDateTime.parse(str(f,"granted_at"));
                OffsetDateTime last=str(f,"last_used_at")==null?granted:OffsetDateTime.parse(str(f,"last_used_at"));
                OffsetDateTime observed=OffsetDateTime.parse(str(f,"observed_at"));
                // Observation must cover the snapshot date, not merely exist from months ago.
                if(!observed.isAfter(asOf) && !observed.atZoneSameInstant(ZoneId.of("Asia/Seoul")).toLocalDate().isBefore(asOf.atZoneSameInstant(ZoneId.of("Asia/Seoul")).toLocalDate())) {
                    var start=end.isAfter(granted)?end:granted;if(last.isAfter(start))start=last;
                    if(!start.plusDays(r.path("idle_days").intValue()).isAfter(asOf)) {
                        status="PENDING_REVIEW";message="TF 종료 후 연속 미사용 기준을 충족한 좌석입니다. 실제 권한 변경 없이 검토 후보로 알립니다.";
                    } else {status="EXCLUDED";exclude="USAGE_RESUMED";message="TF 종료 후 연속 미사용 기간 기준을 충족하지 않습니다.";}
                }
            } else if(f.path("tf_ends_on").isNull()) {
                status="EXCLUDED";exclude="ACTIVE_OTHER_TF";message="원래 TF가 아직 종료되지 않았습니다.";
            }
        }
        if("UNKNOWN".equals(impact.status()) && "PENDING_REVIEW".equals(status)) {status=null;exclude=null;message="회수 조건은 확인했지만 비용 근거가 없어 추가 검토가 필요합니다.";}
        return new ReclaimCandidate(str(f,"assignment_id"),null,null,Platform.valueOf(str(f,"platform")),status==null?null:CandidateStatus.valueOf(status),rule,exclude,null,status==null,null,null,"NONE","template",message,evidence,facts,impact);
    }
}
