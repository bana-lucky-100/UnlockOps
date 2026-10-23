package com.unlockops.common.workflow;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.UUID;
import org.springframework.stereotype.Service;
import static com.unlockops.common.workflow.WorkflowStore.*;

@Service
public class WorkflowAccessControl {
    private final WorkflowStore db;
    public WorkflowAccessControl(WorkflowStore db) { this.db=db; }
    public JsonNode actor(UUID user) {
        var u=db.one("SELECT to_jsonb(u) - 'password_hash' FROM users u WHERE id=?",user);
        forbid("ACTIVE".equals(str(u,"employment_status")));
        return u;
    }
    public boolean capability(UUID actor,UUID company,UUID department,String platform,String capability) {
        return db.exists("""
            SELECT EXISTS(SELECT 1 FROM operator_assignments o JOIN users u ON u.id=o.user_id
              WHERE o.user_id=? AND o.company_id=? AND o.department_id=? AND o.platform=? AND o.capability=?
                AND u.employment_status='ACTIVE' AND u.role='APPROVER')
            """,actor,company,department,platform,capability);
    }
    public void problem(UUID actor,JsonNode p) {
        var u=actor(actor); forbid(uuid(u,"company_id").equals(uuid(p,"company_id")));
        forbid(actor.equals(uuid(p,"requester_id")) || db.exists("""
            SELECT EXISTS(SELECT 1 FROM approval_steps WHERE problem_id=? AND approver_id=? AND plan_version=?)
            """,uuid(p,"id"),actor,p.path("active_plan_version").isNull()?null:p.path("active_plan_version").intValue())
            || capability(actor,uuid(p,"company_id"),uuid(db.one("SELECT to_jsonb(u) FROM users u WHERE id=?",uuid(p,"requester_id")),"department_id"),str(p,"platform"),"SAAS_OPERATOR"));
    }
    /** A scope is readable/startable only when the actor covers every included platform. */
    public void scope(UUID actor,JsonNode scope) {
        var u=actor(actor); forbid(uuid(u,"company_id").equals(uuid(scope,"company_id")));
        for(var platform:scope.path("platforms"))
            forbid(capability(actor,uuid(scope,"company_id"),uuid(scope,"department_id"),platform.asText(),"RECLAIM_REVIEWER") || capability(actor,uuid(scope,"company_id"),uuid(scope,"department_id"),platform.asText(),"IT_HEAD"));
    }
    public boolean canScope(UUID actor,JsonNode scope) {
        try { scope(actor,scope); return true; }
        catch(org.springframework.web.server.ResponseStatusException e) { if(e.getStatusCode().value()==403)return false; throw e; }
    }
    public void assignment(UUID actor,UUID id) {
        var a=db.one("""
            SELECT to_jsonb(x) FROM (SELECT a.company_id,u.department_id,r.platform FROM access_assignments a
            JOIN users u ON u.id=a.user_id JOIN resources r ON r.id=a.resource_id WHERE a.id=?) x
            """,id);
        actor(actor); forbid(capability(actor,uuid(a,"company_id"),uuid(a,"department_id"),str(a,"platform"),"RECLAIM_REVIEWER") || capability(actor,uuid(a,"company_id"),uuid(a,"department_id"),str(a,"platform"),"IT_HEAD"));
    }
}
