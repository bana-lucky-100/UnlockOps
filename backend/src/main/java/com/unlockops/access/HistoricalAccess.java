package com.unlockops.access;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.common.workflow.WorkflowStore;
import com.unlockops.contracts.v2.WorkflowTypes.*;
import java.util.*;
import static com.unlockops.common.workflow.WorkflowStore.*;
import static com.unlockops.contracts.v2.WorkflowTypes.REASON_STATUSES;

/** Read projection of old records. It never supplies a current plan or execution identity. */
final class HistoricalAccess {
    private HistoricalAccess() {}
    static boolean matches(JsonNode p) { return p.path("contract_version").asInt()==1; }
    static boolean pending(JsonNode p) { return !Set.of("DONE","REJECTED","FAILED").contains(str(p,"status")); }
    static String summary(JsonNode p) {
        return "이전 요청 기록: "+str(p,"status")+" / "+Objects.toString(str(p,"reason_code"),"사유 미기록")
            +("ACCESS_VERIFIED".equals(str(p,"result_type"))?" · 당시 권한 검증 완료":"")
            +"\n"+Objects.toString(str(p,"diagnosis"),"");
    }
    static AccessView view(WorkflowStore db,JsonNode p) {
        boolean needsReanalysis=pending(p);
        Status status=needsReanalysis?Status.MANUAL_REVIEW:Status.valueOf(str(p,"status"));
        String reason=str(p,"reason_code");
        String message="이전 요청의 처리 기록입니다.\n"+Objects.toString(str(p,"proposal"),summary(p));
        String result=null;Boolean verified=null;List<ApprovalStep> steps=List.of();
        if(needsReanalysis) {
            reason="PLAN_REVIEW_REQUIRED";
            message+="\n재개하면 현재 정책으로 다시 분석하고 새로운 승인 절차를 시작합니다. 이전 계획과 승인은 재사용하지 않습니다.";
        } else if(status==Status.DONE) {
            String actor=str(p,"decided_by"),acted=str(p,"decided_at");
            if("ACCESS_VERIFIED".equals(str(p,"result_type")) && p.path("verification_ok").asBoolean()
                    && actor!=null && acted!=null && !actor.equals(str(p,"requester_id"))) {
                result="ACCESS_VERIFIED";reason="VERIFIED";verified=true;
                steps=List.of(new ApprovalStep(1,actor,ApprovalStatus.APPROVED,str(p,"decision_reason"),acted));
            } else {
                // A successful history lookup does not invent an unrecorded approval.
                result="GUIDANCE";reason="RAG_GUIDANCE";message+="\n"+summary(p);
            }
        } else {
            String expected=reason==null?null:REASON_STATUSES.get(reason);
            if(expected==null || !expected.equals(status.name()))
                reason=status==Status.REJECTED?"POLICY_NOT_ELIGIBLE":"TOOL_CALL_FAILED";
            if("VERIFICATION_FAILED".equals(reason))verified=false;
        }
        return db.checked(new AccessView(2,"ACCESS_REQUEST",status,reason,message,null,steps.size(),steps,verified,
            str(p,"id"),result,null,null),AccessView.class);
    }
    static Map<String,Object> report(WorkflowStore db,JsonNode p) {
        var out=new LinkedHashMap<String,Object>();
        out.put("workflow",view(db,p));out.put("contents",str(p,"contents"));out.put("analysis_summary",summary(p));
        out.put("platform",str(p,"platform"));out.put("requester_id",str(p,"requester_id"));
        out.put("requester_name",str(db.one("SELECT jsonb_build_object('name',name) FROM users WHERE id=?",uuid(p,"requester_id")),"name"));
        out.put("created_at",str(p,"created_at"));out.put("plan",null);out.put("policy_evidence",List.of());
        out.put("approvers",List.of());out.put("entitlement_code",str(p,"requested_role"));
        out.put("resource_name",uuid(p,"resource_id")==null?null:str(db.one("SELECT jsonb_build_object('name',name) FROM resources WHERE id=?",uuid(p,"resource_id")),"name"));
        out.put("history",db.rows("SELECT to_jsonb(e) FROM problem_events e WHERE problem_id=? ORDER BY id DESC LIMIT 100",uuid(p,"id")));
        // Original plan, reason codes and evidence are history data, not a v2 grant contract.
        out.put("historical_record",p);return out;
    }
}
