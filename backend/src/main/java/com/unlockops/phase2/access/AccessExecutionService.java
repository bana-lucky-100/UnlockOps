package com.unlockops.phase2.access;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.contracts.v2.Phase2Types.*;
import com.unlockops.phase2.common.Phase2Store;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import static com.unlockops.phase2.common.Phase2Store.*;

@Service
public class AccessExecutionService {
    private final Phase2Store db;
    private final AccessPlanningService planner;
    private final AccessWorkflowService workflow;
    private final boolean demo;
    public AccessExecutionService(Phase2Store db,AccessPlanningService planner,AccessWorkflowService workflow,@Value("${app.demo-enabled:false}") boolean demo) {
        this.db=db;this.planner=planner;this.workflow=workflow;this.demo=demo;
    }
    public record ExecutionInput(UUID job_event_id,String plan_hash,String idempotency_key) {}
    private void identity(JsonNode p,ExecutionInput input) {
        conflict(input.job_event_id()!=null && input.job_event_id().equals(uuid(p,"active_job_event_id")) &&
            input.plan_hash()!=null && input.plan_hash().equals(str(p,"approved_plan_hash")) &&
            input.plan_hash().equals(str(p,"plan_hash")) && input.idempotency_key()!=null && input.idempotency_key().equals(str(p,"idempotency_key")),"실행 작업·승인 계획·멱등 키가 다릅니다.");
    }
    @Transactional
    public JsonNode execute(UUID id,ExecutionInput input) {
        forbid(demo);var p=db.problem(id,true);identity(p,input);
        var receipts=db.rows("SELECT result FROM access_execution_receipts WHERE problem_id=?",id);
        if(!receipts.isEmpty()) return receipts.getFirst();
        conflict("EXECUTING".equals(str(p,"status")),"실행 가능한 상태가 아닙니다.");
        var plan=db.decode(p.path("plan"),GrantPlanV2.class);
        // Company lock serializes mock grants across different requests for the same assignment/budget.
        db.mutex("v2-grant:"+plan.companyId());
        var user=db.one("SELECT to_jsonb(u) FROM users u WHERE id=?",UUID.fromString(plan.requesterId()));
        db.rows("SELECT to_jsonb(b) FROM department_budgets b WHERE department_id=? FOR UPDATE",uuid(user,"department_id"));
        var steps=db.rows("SELECT to_jsonb(s) FROM approval_steps s WHERE problem_id=? AND plan_version=? ORDER BY step",id,p.path("active_plan_version").intValue());
        conflict(steps.size()==plan.approverIds().size() && steps.stream().allMatch(s->"APPROVED".equals(str(s,"status"))) &&
            steps.stream().map(s->str(s,"approver_id")).toList().equals(plan.approverIds()),"필수 승인이 완료되지 않았습니다.");
        if(!planner.sameCurrentPlan(p,plan)) {
            workflow.state(id,Status.MANUAL_REVIEW,"PLAN_REVIEW_REQUIRED","실행 전 조건이 변경되어 재검토가 필요합니다.",null);
            return db.json.tree(db.json.write(Map.of("executed",false,"reason_code","PLAN_REVIEW_REQUIRED")));
        }
        var ent=planner.entitlement(UUID.fromString(plan.companyId()),UUID.fromString(plan.entitlementId()));
        var company=db.one("SELECT to_jsonb(c) FROM companies c WHERE id=?",UUID.fromString(plan.companyId()));
        forbid(company.path("is_mock").asBoolean());
        int charged=db.jdbc.update("""
            UPDATE department_budgets SET remaining_monthly_amount=remaining_monthly_amount-?,updated_at=now()
            WHERE department_id=? AND currency=? AND remaining_monthly_amount>=?
            """,new BigDecimal(plan.monthlyAmount()),uuid(user,"department_id"),plan.currency(),new BigDecimal(plan.monthlyAmount()));
        conflict(charged==1,"예산이 변경되었습니다.");
        UUID assignment=UUID.randomUUID();
        db.jdbc.update("""
            INSERT INTO access_assignments(id,company_id,user_id,resource_id,entitlement_id,entitlement_revision,origin_tf_id,granted_at,source_problem_id)
            VALUES(?,?,?,?,?,?,?,now(),?)
            """,assignment,UUID.fromString(plan.companyId()),UUID.fromString(plan.requesterId()),UUID.fromString(plan.resourceId()),UUID.fromString(plan.entitlementId()),plan.entitlementRevision(),uuid(ent,"tf_id"),id);
        db.jdbc.update("""
            INSERT INTO mock_entitlement_memberships(assignment_id,company_id,user_id,entitlement_id,entitlement_revision,mapping)
            VALUES(?,?,?,?,?,?::jsonb)
            """,assignment,UUID.fromString(plan.companyId()),UUID.fromString(plan.requesterId()),UUID.fromString(plan.entitlementId()),plan.entitlementRevision(),ent.path("mapping").toString());
        // UNKNOWN is deliberate: a grant does not prove that usage was observed.
        db.jdbc.update("INSERT INTO assignment_usage(assignment_id,company_id,observation_status,observed_at,source_reference) VALUES(?,?,'UNKNOWN',now(),'mock-grant:no-usage-observation')",assignment,UUID.fromString(plan.companyId()));
        var receipt=db.json.tree(db.json.write(Map.of("schema_version",2,"executed",true,"problem_id",id,"assignment_id",assignment,"plan_hash",input.plan_hash(),"idempotency_key",input.idempotency_key(),"charged_amount",plan.monthlyAmount(),"currency",plan.currency())));
        db.jdbc.update("""
            INSERT INTO access_execution_receipts(problem_id,company_id,plan_version,plan_hash,idempotency_key,assignment_id,result)
            VALUES(?,?,?,?,?,?,?::jsonb)
            """,id,UUID.fromString(plan.companyId()),p.path("active_plan_version").intValue(),input.plan_hash(),input.idempotency_key(),assignment,receipt.toString());
        workflow.audit(id,"MOCK_GRANTED",receipt);return receipt;
    }
    @Transactional(readOnly=true)
    public Map<String,Object> verify(UUID id,ExecutionInput input) {
        var p=db.problem(id,false);identity(p,input);
        boolean receipt=db.exists("SELECT EXISTS(SELECT 1 FROM access_execution_receipts WHERE problem_id=? AND plan_hash=? AND idempotency_key=?)",id,input.plan_hash(),input.idempotency_key());
        var result=new LinkedHashMap<String,Object>();
        result.put("schema_version",2);result.put("problem_id",id);result.put("receipt_exists",receipt);
        result.put("verification_ok",receipt?verified(p):null);result.put("source","mock_entitlement_memberships");return result;
    }
    private boolean verified(JsonNode p) {
        var plan=db.decode(p.path("plan"),GrantPlanV2.class);
        return db.exists("""
            SELECT EXISTS(SELECT 1 FROM access_execution_receipts r JOIN access_assignments a ON a.id=r.assignment_id
              JOIN mock_entitlement_memberships m ON m.assignment_id=a.id
              JOIN entitlement_revisions e ON e.entitlement_id=m.entitlement_id AND e.revision=m.entitlement_revision
              WHERE r.problem_id=? AND r.plan_hash=? AND r.idempotency_key=? AND a.status='ACTIVE'
                AND a.user_id=? AND a.entitlement_id=? AND a.entitlement_revision=?
                AND a.source_problem_id=r.problem_id AND m.company_id=a.company_id AND m.user_id=a.user_id
                AND m.entitlement_id=a.entitlement_id AND m.entitlement_revision=a.entitlement_revision AND m.mapping=e.mapping)
            """,uuid(p,"id"),str(p,"approved_plan_hash"),str(p,"idempotency_key"),UUID.fromString(plan.requesterId()),UUID.fromString(plan.entitlementId()),plan.entitlementRevision());
    }
    public void result(JsonNode p,AccessEvent event) {
        if(!"EXECUTING".equals(str(p,"status")) || "PROGRESS".equals(event.eventType())) return;
        UUID id=uuid(p,"id");
        if(event.result().status()==Status.DONE || "VERIFICATION_FAILED".equals(event.result().reasonCode())) {
            conflict(db.exists("SELECT EXISTS(SELECT 1 FROM access_execution_receipts WHERE problem_id=?)",id),"실행 영수증이 없습니다.");
            boolean ok=verified(p);
            db.jdbc.update("""
                UPDATE problems SET status=?,result_type=?,reason_code=?,proposal=?,verification_ok=?,updated_at=now() WHERE id=?
                """,ok?"DONE":"FAILED",ok?"ACCESS_VERIFIED":null,ok?"VERIFIED":"VERIFICATION_FAILED",
                ok?"권한 부여 후 실제 접근 상태를 확인했습니다.":"권한 변경 후 검증 결과가 일치하지 않습니다.",ok,id);
        } else workflow.state(id,Status.FAILED,"TOOL_CALL_FAILED","실행 또는 검증 도구 호출에 실패했습니다. 영수증을 확인해 주세요.",null);
    }
}
