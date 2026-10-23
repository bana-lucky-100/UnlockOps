package com.unlockops.messaging.workflow;

import com.unlockops.common.workflow.WorkflowStore;
import com.unlockops.contracts.v2.WorkflowTypes.*;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class WorkflowJobs {
    private final WorkflowStore db;
    public WorkflowJobs(WorkflowStore db) { this.db=db; }
    public UUID access(UUID id,String type,String hash,String key) {
        UUID event=UUID.randomUUID();
        var job=db.checked(new AccessJob(2,event.toString(),"ACCESS_REQUEST",type,id.toString(),hash,key),AccessJob.class);
        enqueue(event,"EXECUTE".equals(type)?"v2.execution":"v2.analysis",job);
        db.jdbc.update("UPDATE problems SET active_job_event_id=? WHERE id=?",event,id);
        return event;
    }
    public void reclaim(UUID id,String trigger,String scope,String time) {
        UUID event=UUID.randomUUID();
        var job=db.checked(new ReclaimJob(2,event.toString(),"RECLAIM_SCAN","RECLAIM_CHECK",id.toString(),trigger,scope,time),ReclaimJob.class);
        enqueue(event,"v2.analysis",job);
        db.jdbc.update("UPDATE reclaim_runs SET active_job_event_id=? WHERE id=?",event,id);
    }
    private void enqueue(UUID event,String route,Object job) {
        db.jdbc.update("INSERT INTO outbox(event_id,routing_key,payload) VALUES(?,?,?::jsonb)",event,route,db.json.write(job));
    }
}
