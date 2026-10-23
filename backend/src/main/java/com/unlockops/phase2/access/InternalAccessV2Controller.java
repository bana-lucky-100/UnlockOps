package com.unlockops.phase2.access;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/internal/v2/problems")
public class InternalAccessV2Controller {
    private final AccessWorkflowService workflow;
    private final AccessExecutionService execution;
    public InternalAccessV2Controller(AccessWorkflowService workflow,AccessExecutionService execution) {this.workflow=workflow;this.execution=execution;}
    @GetMapping("/{id}/context") public Map<String,Object> context(@PathVariable UUID id) {return workflow.context(id);}
    @PostMapping("/{id}/assessment") public AccessPlanningService.Assessment assessment(@PathVariable UUID id,@RequestBody AccessWorkflowService.AssessmentInput input) {return workflow.assessment(id,input);}
    @PostMapping("/{id}/execute") public JsonNode execute(@PathVariable UUID id,@RequestBody AccessExecutionService.ExecutionInput input) {return execution.execute(id,input);}
    @PostMapping("/{id}/verify") public Map<String,Object> verify(@PathVariable UUID id,@RequestBody AccessExecutionService.ExecutionInput input) {return execution.verify(id,input);}
}
