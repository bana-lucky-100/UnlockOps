package com.unlockops.access;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.contracts.v2.WorkflowTypes.*;
import com.unlockops.common.workflow.*;
import com.unlockops.messaging.workflow.WorkflowJobs;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import static com.unlockops.common.workflow.WorkflowStore.*;

@Service
public class AccessWorkflowService {
    private final WorkflowStore db;
    private final WorkflowAccessControl acl;
    private final AccessPlanningService planner;
    private final WorkflowJobs jobs;
    public AccessWorkflowService(WorkflowStore db,WorkflowAccessControl acl,AccessPlanningService planner,WorkflowJobs jobs) {
        this.db=db;this.acl=acl;this.planner=planner;this.jobs=jobs;
    }
    @Transactional
    public AccessView create(UUID actor,AccessRequestInput input,String key) {
        key(key); var user=acl.actor(actor);
        conflict(!input.contents().isBlank(),"요청 내용을 입력해 주세요.");
        input=new AccessRequestInput(input.schemaVersion(),input.platform(),RequestPlatformScope.mask(input.contents()),input.resourceId(),input.entitlementId());
        UUID company=uuid(user,"company_id");
        db.mutex("access-request:"+actor+":"+key);
        var previous=db.rows("SELECT to_jsonb(p) FROM problems p WHERE requester_id=? AND client_request_key=?",actor,key);
        var payload=db.json.tree(db.json.write(input));
        if(!previous.isEmpty()) {
            var p=previous.getFirst();
            conflict(p.path("contract_version").asInt()==2 && payload.equals(p.path("request_payload")),"동일 요청 키에 다른 입력이 사용되었습니다.");
            return view(p);
        }
        var mentioned=RequestPlatformScope.mentioned(input.contents());
        if(!mentioned.isEmpty() && mentioned.getFirst()!=input.platform())
            input=new AccessRequestInput(input.schemaVersion(),mentioned.getFirst(),input.contents(),null,null);
        if(input.resourceId()!=null) {
            var resource=db.one("SELECT to_jsonb(r) FROM resources r WHERE id=? AND company_id=?",UUID.fromString(input.resourceId()),company);
            conflict(input.platform().name().equals(str(resource,"platform")),"자원 플랫폼이 다릅니다.");
        }
        if(input.entitlementId()!=null) {
            var ent=planner.entitlement(company,UUID.fromString(input.entitlementId()));
            conflict(input.platform().name().equals(str(ent,"platform")) && (input.resourceId()==null || input.resourceId().equals(str(ent,"resource_id"))),"권한 항목이 요청 범위와 다릅니다.");
        }
        UUID id=UUID.randomUUID();
        db.jdbc.update("""
            INSERT INTO problems(id,company_id,requester_id,platform,contents,resource_id,requested_entitlement_id,
              thread_id,client_request_key,request_payload,contract_version,status,proposal)
            VALUES(?,?,?,?,?,?,?, ?,?,?::jsonb,2,'RECEIVED','요청이 접수되었습니다.')
            """,id,company,actor,input.platform().name(),input.contents(),input.resourceId()==null?null:UUID.fromString(input.resourceId()),
            input.entitlementId()==null?null:UUID.fromString(input.entitlementId()),id.toString(),key,payload.toString());
        jobs.access(id,"ANALYZE",null,null);audit(id,"REQUESTED",payload);
        return view(db.problem(id,false));
    }
    @Transactional(readOnly=true)
    public AccessView get(UUID actor,UUID id) { var p=db.problem(id,false);acl.problem(actor,p);return view(p); }
    @Transactional(readOnly=true)
    public List<AccessView> list(UUID actor) { return visibleProblems(actor).stream().map(this::view).toList(); }
    private List<JsonNode> visibleProblems(UUID actor) {
        var user=acl.actor(actor);
        return db.rows("""
            SELECT to_jsonb(p) || jsonb_build_object('requester_name',requester.name)
            FROM problems p JOIN users requester ON requester.id=p.requester_id WHERE p.contract_version=2 AND p.company_id=? AND
              (p.requester_id=? OR EXISTS(SELECT 1 FROM approval_steps s WHERE s.problem_id=p.id AND s.plan_version=p.active_plan_version AND s.approver_id=?)
               OR EXISTS(SELECT 1 FROM operator_assignments o JOIN users u ON u.id=p.requester_id
                 WHERE o.user_id=? AND o.company_id=p.company_id AND o.department_id=u.department_id AND o.platform=p.platform AND o.capability='SAAS_OPERATOR'))
            ORDER BY p.created_at DESC LIMIT 100
            """,uuid(user,"company_id"),actor,actor,actor);
    }
    public AccessView view(JsonNode p) {
        var steps=db.rows("SELECT to_jsonb(s) FROM approval_steps s WHERE problem_id=? AND plan_version=? ORDER BY step",uuid(p,"id"),p.path("active_plan_version").isNull()?null:p.path("active_plan_version").intValue())
            .stream().map(s->new ApprovalStep(s.path("step").intValue(),str(s,"approver_id"),ApprovalStatus.valueOf(str(s,"status")),str(s,"reason"),str(s,"acted_at"))).toList();
        Integer current=steps.stream().filter(s->s.status()==ApprovalStatus.WAITING).map(ApprovalStep::step).findFirst().orElse(null);
        return db.checked(new AccessView(2,"ACCESS_REQUEST",Status.valueOf(str(p,"status")),str(p,"reason_code"),
            (str(p,"proposal")==null?"요청을 처리하고 있습니다.":str(p,"proposal"))+RequestPlatformScope.notice(p.path("contents").asText("")),current,steps.size(),steps,
            p.path("verification_ok").isNull()?null:p.path("verification_ok").booleanValue(),str(p,"id"),str(p,"result_type"),str(p,"plan_hash"),
            p.path("active_plan_version").isNull()?null:p.path("active_plan_version").intValue()),AccessView.class);
    }
    /** UI projections reuse the same visibility rule as the workflow list. */
    @Transactional(readOnly=true)
    public List<Map<String,Object>> summaries(UUID actor) {
        return visibleProblems(actor).stream().map(p->{
            var out=new LinkedHashMap<String,Object>();out.put("workflow",view(p));out.put("contents",str(p,"contents"));
            out.put("platform",str(p,"platform"));out.put("requester_id",str(p,"requester_id"));
            out.put("requester_name",str(p,"requester_name"));
            out.put("created_at",str(p,"created_at"));return (Map<String,Object>)out;
        }).toList();
    }
    @Transactional(readOnly=true)
    public List<JsonNode> catalog(UUID actor) {
        var user=acl.actor(actor);
        return db.rows("""
            SELECT jsonb_build_object('entitlement_id',e.id,'resource_id',r.id,'platform',r.platform,
                'resource_name',r.name,'resource_key',r.external_id,'entitlement_code',e.code,'kind',e.kind)
            FROM entitlements e JOIN resources r ON r.id=e.resource_id
            WHERE e.company_id=? ORDER BY r.platform,r.name,e.code
            """,uuid(user,"company_id"));
    }
    @Transactional(readOnly=true)
    public Map<String,Object> report(UUID actor,UUID id) {
        var p=db.problem(id,false);acl.problem(actor,p);
        var result=new LinkedHashMap<String,Object>();result.put("workflow",view(p));result.put("contents",str(p,"contents"));
        result.put("analysis_summary",str(p,"diagnosis"));result.put("plan",p.path("plan"));result.put("policy_evidence",p.path("evidence"));
        result.put("platform",str(p,"platform"));result.put("requester_id",str(p,"requester_id"));
        result.put("requester_name",str(db.one("SELECT jsonb_build_object('name',name) FROM users WHERE id=?",uuid(p,"requester_id")),"name"));
        result.put("created_at",str(p,"created_at"));
        result.put("approvers",db.rows("""
            SELECT jsonb_build_object('id',u.id,'name',u.name) FROM approval_steps s JOIN users u ON u.id=s.approver_id
            WHERE s.problem_id=? AND s.plan_version=? ORDER BY s.step
            """,id,p.path("active_plan_version").isNull()?null:p.path("active_plan_version").intValue()));
        result.put("resource_name",p.path("resource_id").isNull()?null:str(db.one("SELECT jsonb_build_object('name',name) FROM resources WHERE id=?",uuid(p,"resource_id")),"name"));
        result.put("entitlement_code",p.path("requested_entitlement_id").isNull()?null:str(db.one("SELECT jsonb_build_object('code',code) FROM entitlements WHERE id=?",uuid(p,"requested_entitlement_id")),"code"));
        result.put("history",db.rows("SELECT to_jsonb(e) FROM problem_events e WHERE problem_id=? ORDER BY id DESC LIMIT 100",id));return result;
    }
    @Transactional(readOnly=true)
    public Map<String,Object> context(UUID id) {
        var p=db.problem(id,false);
        var requester=db.one("SELECT jsonb_build_object('id',u.id,'company_id',u.company_id,'department_id',u.department_id,'employment_status',u.employment_status,'job_grade',u.job_grade,'job_family',u.job_family) FROM users u WHERE id=?",uuid(p,"requester_id"));
        var out=new LinkedHashMap<String,Object>();out.put("schema_version",2);out.put("problem",p);out.put("requester",requester);
        out.put("entitlements",db.rows("""
            SELECT to_jsonb(x) FROM (SELECT e.id,e.code,e.kind,e.resource_id,r.name,r.external_id,r.platform
              FROM entitlements e JOIN resources r ON r.id=e.resource_id WHERE e.company_id=? AND r.platform=?) x
            """,uuid(p,"company_id"),str(p,"platform")));
        out.put("facts",db.rows("SELECT to_jsonb(f) FROM saas_context_facts f WHERE company_id=? AND user_id=? AND platform=?",uuid(p,"company_id"),uuid(p,"requester_id"),str(p,"platform")));
        out.put("policies",db.rows("SELECT to_jsonb(p) FROM policy_revisions p WHERE company_id=? ORDER BY revision DESC",uuid(p,"company_id")));
        out.put("workflow",view(p));return out;
    }
    public record AssessmentInput(UUID job_event_id,UUID entitlement_id) {}
    @Transactional(readOnly=true)
    public AccessPlanningService.Assessment assessment(UUID id,AssessmentInput input) {
        var p=db.problem(id,false);
        conflict(input.job_event_id()!=null && input.job_event_id().equals(uuid(p,"active_job_event_id")) &&
            Set.of("RECEIVED","DIAGNOSING").contains(str(p,"status")),"현재 분석 작업이 아닙니다.");
        return planner.assess(p,input.entitlement_id());
    }
    @Transactional
    public AccessView decide(UUID actor,UUID id,ApprovalDecisionInput input) {
        acl.actor(actor);var p=db.problem(id,true);acl.problem(actor,p);
        conflict("WAITING_APPROVAL".equals(str(p,"status")),"현재 승인 대기 상태가 아닙니다.");
        conflict(Objects.equals(input.expectedPlanVersion(),p.path("active_plan_version").intValue()),"승인 회차가 변경되었습니다. 다시 조회해 주세요.");
        conflict(input.expectedPlanHash().equals(str(p,"plan_hash")),"승인 계획이 변경되었습니다. 다시 조회해 주세요.");
        var waiting=db.one("SELECT to_jsonb(s) FROM approval_steps s WHERE problem_id=? AND plan_version=? AND status='WAITING'",id,p.path("active_plan_version").intValue());
        forbid(actor.equals(uuid(waiting,"approver_id")) && !actor.equals(uuid(p,"requester_id")));
        var plan=db.decode(p.path("plan"),GrantPlanV2.class);
        if(!planner.sameCurrentPlan(p,plan)) {
            abandonSteps(p);state(id,Status.MANUAL_REVIEW,"PLAN_REVIEW_REQUIRED","정책·예산·승인자 조건이 변경되었습니다. 재분석해 주세요.",null);
            audit(id,"PLAN_REVIEW_REQUIRED",db.json.tree(db.json.write(input)));return view(db.problem(id,false));
        }
        String status=switch(input.action()) {case "APPROVE"->"APPROVED";case "REJECT"->"REJECTED";case "HOLD"->"ON_HOLD";default->throw new IllegalArgumentException("action");};
        int step=waiting.path("step").intValue(),version=p.path("active_plan_version").intValue();
        db.jdbc.update("UPDATE approval_steps SET status=?,reason=?,acted_at=now() WHERE problem_id=? AND plan_version=? AND step=?",status,input.reason(),id,version,step);
        db.jdbc.update("UPDATE problems SET decision_source='HUMAN',decided_by=?,decided_at=now(),decision_reason=? WHERE id=?",actor,input.reason(),id);
        if(!"APPROVE".equals(input.action())) {
            abandonSteps(p);state(id,"HOLD".equals(input.action())?Status.ON_HOLD:Status.REJECTED,
                "HOLD".equals(input.action())?"HELD_BY_APPROVER":"HUMAN_REJECTED",input.reason(),null);
        } else if(step<plan.approverIds().size()) {
            db.jdbc.update("UPDATE approval_steps SET status='WAITING' WHERE problem_id=? AND plan_version=? AND step=? AND status='PENDING'",id,version,step+1);
            db.jdbc.update("UPDATE problems SET approver_id=?,updated_at=now() WHERE id=?",UUID.fromString(plan.approverIds().get(step)),id);
        } else {
            String executionKey="v2:"+id+":"+version+":"+input.expectedPlanHash();
            db.jdbc.update("UPDATE problems SET approved_plan_hash=plan_hash,idempotency_key=? WHERE id=?",executionKey,id);
            state(id,Status.EXECUTING,"HUMAN_APPROVED","모든 승인이 완료되어 권한 부여를 진행합니다.",null);
            jobs.access(id,"EXECUTE",input.expectedPlanHash(),executionKey);
        }
        audit(id,"DECISION",db.json.tree(db.json.write(Map.of("actor_id",actor,"decision",input))));
        return view(db.problem(id,false));
    }
    @Transactional
    public AccessView resume(UUID actor,UUID id) {
        var p=db.problem(id,true);acl.problem(actor,p);
        conflict(Set.of("ON_HOLD","MANUAL_REVIEW").contains(str(p,"status")),"보류·수동 검토 요청만 재개할 수 있습니다.");
        abandonSteps(p);
        db.jdbc.update("""
            UPDATE problems SET status='RECEIVED',reason_code=NULL,result_type=NULL,verification_ok=NULL,
              plan=NULL,plan_hash=NULL,approved_plan_hash=NULL,active_plan_version=NULL,approver_id=NULL,
              idempotency_key=NULL,decision_reason=NULL,decision_source=NULL,decided_by=NULL,decided_at=NULL,
              diagnosis=NULL,proposal='최신 조건으로 다시 분석합니다.',updated_at=now() WHERE id=?
            """,id);
        jobs.access(id,"ANALYZE",null,null);audit(id,"RESUMED",db.json.tree(db.json.write(Map.of("actor_id",actor))));return view(db.problem(id,false));
    }
    /** Called inside the inbox transaction; current generation was checked by the router. */
    public void analysis(JsonNode p,AccessEvent event) {
        UUID id=uuid(p,"id");
        if(!Set.of("RECEIVED","DIAGNOSING").contains(str(p,"status"))) return;
        if("PROGRESS".equals(event.eventType())) {state(id,Status.DIAGNOSING,null,"요청을 분석하고 있습니다.",null);return;}
        if("FAILED".equals(event.eventType())) {state(id,Status.FAILED,"TOOL_CALL_FAILED","분석 도구 실행에 실패했습니다.",null);return;}
        conflict("ANALYZED".equals(event.eventType()),"분석 이벤트가 아닙니다.");
        var sources=db.rows("SELECT to_jsonb(r) FROM policy_revisions r WHERE company_id=? ORDER BY revision DESC",uuid(p,"company_id"));
        var citations=event.policyEvidence()==null?List.<PolicyEvidence>of():event.policyEvidence().stream().filter(e->!sources.isEmpty()
            && e.docId().equals(str(sources.getFirst(),"doc_id")) && e.version().equals(str(sources.getFirst(),"revision"))
            && e.sourceHash().equals(str(sources.getFirst(),"source_hash")) && hash(str(sources.getFirst(),"content")).equals(e.sourceHash())
            && e.text().startsWith("## "+e.article()+"\n")
            && str(sources.getFirst(),"content").contains(e.text())).toList();
        db.jdbc.update("UPDATE problems SET evidence=?::jsonb WHERE id=?",db.json.write(citations),id);
        if(event.result().status()==Status.DONE && "RAG_GUIDANCE".equals(event.result().reasonCode())) {
            boolean supported=!citations.isEmpty();
            if(supported) {
                db.jdbc.update("UPDATE problems SET evidence=?::jsonb WHERE id=?",db.json.write(citations),id);
                state(id,Status.DONE,"RAG_GUIDANCE",event.result().message(),"GUIDANCE");
            } else state(id,Status.MANUAL_REVIEW,"MISSING_SOURCE_EVIDENCE","안내에 검증 가능한 정책 근거가 없습니다.",null);
            return;
        }
        UUID ent=event.proposedEntitlementId()==null?uuid(p,"requested_entitlement_id"):UUID.fromString(event.proposedEntitlementId());
        var assessment=planner.assess(p,ent);
        if(event.result().status()==Status.MANUAL_REVIEW || event.result().status()==Status.FAILED) {
            state(id,event.result().status(),event.result().reasonCode(),event.result().message(),null);return;
        }
        if(assessment.plan()==null) {
            state(id,assessment.status(),assessment.reason(),assessment.message(),assessment.status()==Status.DONE?"GUIDANCE":null);return;
        }
        var authoritativeEvidence=assessment.evidence();
        boolean cited=event.policyEvidence()!=null && event.policyEvidence().stream().anyMatch(e->authoritativeEvidence.stream().anyMatch(s->
            s.docId().equals(e.docId()) && s.version().equals(e.version()) && s.sourceHash().equals(e.sourceHash()) && s.text().contains(e.text())));
        if(!cited) {state(id,Status.MANUAL_REVIEW,"MISSING_SOURCE_EVIDENCE","분석 결과에 검증 가능한 정책 근거가 없습니다.",null);return;}
        if(event.result().status()!=Status.WAITING_APPROVAL) {state(id,Status.MANUAL_REVIEW,"ANALYSIS_CONFLICT","분석 결과와 서버 정책 판정이 다릅니다.",null);return;}
        if(!db.codec.planHash(assessment.plan()).equals(event.result().planHash())) {
            state(id,Status.MANUAL_REVIEW,"PLAN_REVIEW_REQUIRED","분석 이후 승인 계획이 변경되었습니다. 최신 조건으로 재분석해 주세요.",null);return;
        }
        if("LEAST_PRIVILEGE_PROPOSED".equals(event.result().reasonCode()))
            assessment=new AccessPlanningService.Assessment(assessment.status(),"LEAST_PRIVILEGE_PROPOSED","서버에서 허용한 최소 권한 제안에 대해 순서대로 승인을 기다립니다.",assessment.plan(),assessment.evidence(),assessment.review_facts());
        assessment=new AccessPlanningService.Assessment(assessment.status(),assessment.reason(),assessment.message(),assessment.plan(),citations,assessment.review_facts());
        install(p,assessment);
        db.jdbc.update("UPDATE problems SET diagnosis=? WHERE id=?",event.result().message(),id);
    }
    private void install(JsonNode p,AccessPlanningService.Assessment a) {
        var plan=a.plan(); UUID id=uuid(p,"id"),company=uuid(p,"company_id");String hash=db.codec.planHash(plan);
        int version=db.jdbc.queryForObject("SELECT coalesce(max(version),0)+1 FROM access_plan_versions WHERE problem_id=?",Integer.class,id);
        db.jdbc.update("""
            INSERT INTO access_plan_versions(problem_id,company_id,version,entitlement_id,entitlement_revision,pricing_id,pricing_revision,
              policy_id,policy_revision,route_id,route_revision,plan,plan_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?::jsonb,?)
            """,id,company,version,UUID.fromString(plan.entitlementId()),plan.entitlementRevision(),UUID.fromString(plan.pricingId()),plan.pricingRevision(),
            UUID.fromString(plan.policyId()),plan.policyRevision(),UUID.fromString(plan.routeId()),plan.routeRevision(),db.json.write(plan),hash);
        for(int i=0;i<plan.approverIds().size();i++) db.jdbc.update("""
            INSERT INTO approval_steps(problem_id,company_id,plan_version,step,approver_id,requester_id,status,plan_hash)
            VALUES(?,?,?,?,?,?,?,?)
            """,id,company,version,i+1,UUID.fromString(plan.approverIds().get(i)),uuid(p,"requester_id"),i==0?"WAITING":"PENDING",hash);
        db.jdbc.update("""
            UPDATE problems SET plan=?::jsonb,plan_hash=?,active_plan_version=?,resource_id=?,requested_entitlement_id=?,
              approver_id=?,evidence=?::jsonb WHERE id=?
            """,db.json.write(plan),hash,version,UUID.fromString(plan.resourceId()),UUID.fromString(plan.entitlementId()),UUID.fromString(plan.approverIds().getFirst()),db.json.write(a.evidence()),id);
        state(id,a.status(),a.reason(),a.message(),null);
    }
    private void abandonSteps(JsonNode p) {
        db.jdbc.update("UPDATE approval_steps SET status='SKIPPED' WHERE problem_id=? AND plan_version=? AND status IN ('PENDING','WAITING')",uuid(p,"id"),p.path("active_plan_version").isNull()?null:p.path("active_plan_version").intValue());
    }
    public void state(UUID id,Status status,String reason,String message,String result) {
        db.jdbc.update("UPDATE problems SET status=?,reason_code=?,proposal=?,result_type=?,verification_ok=NULL,updated_at=now() WHERE id=? AND contract_version=2",status.name(),reason,message,result,id);
    }
    public void audit(UUID id,String kind,JsonNode payload) {
        db.jdbc.update("INSERT INTO problem_events(event_id,problem_id,kind,payload) VALUES(?,?,?,?::jsonb)",UUID.randomUUID(),id,"V2_"+kind,payload.toString());
    }
}
