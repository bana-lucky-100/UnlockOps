package com.unlockops.messaging.workflow;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.contracts.v2.WorkflowTypes.*;
import com.unlockops.common.workflow.WorkflowStore;
import com.unlockops.access.*;
import com.unlockops.reclaim.ReclaimResultService;
import com.unlockops.messaging.service.InvalidAgentMessageException;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import static com.unlockops.common.workflow.WorkflowStore.*;

@Service
public class WorkflowResults {
    private final WorkflowStore db;
    private final AccessWorkflowService access;
    private final AccessExecutionService execution;
    private final ReclaimResultService reclaim;
    public WorkflowResults(WorkflowStore db,AccessWorkflowService access,AccessExecutionService execution,ReclaimResultService reclaim) {
        this.db=db;this.access=access;this.execution=execution;this.reclaim=reclaim;
    }
    @Transactional
    public void apply(JsonNode raw) {
        try {
            if("ACCESS_REQUEST".equals(raw.path("task_type").asText())) {
                var event=db.decode(raw,AccessEvent.class);UUID id=UUID.fromString(event.problemId());
                var p=db.problem(id,true);
                if(!record(UUID.fromString(event.eventId())))return;
                db.jdbc.update("INSERT INTO problem_events(event_id,problem_id,kind,payload) VALUES(?,?,?,?::jsonb)",UUID.fromString(event.eventId()),id,"V2_"+event.eventType(),raw.toString());
                if(!UUID.fromString(event.jobEventId()).equals(uuid(p,"active_job_event_id")))return; // Audit stale generation, never apply it.
                var job=db.one("SELECT payload FROM outbox WHERE event_id=?",UUID.fromString(event.jobEventId()));
                conflict(event.jobType().equals(job.path("job_type").asText()),"작업 종류가 다릅니다.");
                if("ANALYZE".equals(event.jobType()))access.analysis(p,event);else execution.result(p,event);
            } else if("RECLAIM_SCAN".equals(raw.path("task_type").asText())) {
                var event=db.decode(raw,ReclaimEvent.class);UUID id=UUID.fromString(event.runId());
                var run=db.run(id,true);
                if(!record(UUID.fromString(event.eventId())))return;
                db.jdbc.update("INSERT INTO reclaim_events(event_id,run_id,event_type,payload) VALUES(?,?,?,?::jsonb)",UUID.fromString(event.eventId()),id,event.eventType(),raw.toString());
                if(!UUID.fromString(event.jobEventId()).equals(uuid(run,"active_job_event_id")))return;
                reclaim.apply(run,event);
            } else throw new IllegalArgumentException("Unsupported v2 task_type");
        } catch(IllegalArgumentException | org.springframework.web.server.ResponseStatusException e) {
            throw new InvalidAgentMessageException(InvalidAgentMessageException.Reason.INVALID_RESULT,e);
        }
    }
    private boolean record(UUID event) {return db.jdbc.update("INSERT INTO inbox_events(event_id) VALUES(?) ON CONFLICT DO NOTHING",event)==1;}
}
