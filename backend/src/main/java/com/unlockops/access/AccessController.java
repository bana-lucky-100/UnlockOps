package com.unlockops.access;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.auth.model.AppUser;
import com.unlockops.contracts.v2.WorkflowTypes.*;
import com.unlockops.common.workflow.WorkflowStore;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v2/problems")
public class AccessController {
    private final AccessWorkflowService service;
    private final WorkflowStore db;
    public AccessController(AccessWorkflowService service,WorkflowStore db) {this.service=service;this.db=db;}
    @PostMapping @ResponseStatus(HttpStatus.ACCEPTED)
    public AccessView create(@AuthenticationPrincipal AppUser user,@RequestHeader("Idempotency-Key") String key,@RequestBody JsonNode body) {
        return service.create(user.id(),db.decode(body,AccessRequestInput.class),key);
    }
    @GetMapping public List<AccessView> list(@AuthenticationPrincipal AppUser user) {return service.list(user.id());}
    @GetMapping("/summaries") public List<Map<String,Object>> summaries(@AuthenticationPrincipal AppUser user) {return service.summaries(user.id());}
    @GetMapping("/catalog") public List<JsonNode> catalog(@AuthenticationPrincipal AppUser user) {return service.catalog(user.id());}
    @GetMapping("/{id}") public AccessView get(@AuthenticationPrincipal AppUser user,@PathVariable UUID id) {return service.get(user.id(),id);}
    @GetMapping("/{id}/report") public Map<String,Object> report(@AuthenticationPrincipal AppUser user,@PathVariable UUID id) {return service.report(user.id(),id);}
    @PostMapping("/{id}/decisions") public AccessView decide(@AuthenticationPrincipal AppUser user,@PathVariable UUID id,@RequestBody JsonNode body) {
        return service.decide(user.id(),id,db.decode(body,ApprovalDecisionInput.class));
    }
    @PostMapping("/{id}/resume") @ResponseStatus(HttpStatus.ACCEPTED)
    public AccessView resume(@AuthenticationPrincipal AppUser user,@PathVariable UUID id) {return service.resume(user.id(),id);}
}
