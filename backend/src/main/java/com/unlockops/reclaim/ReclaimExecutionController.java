package com.unlockops.reclaim;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.auth.model.AppUser;
import com.unlockops.common.workflow.WorkflowStore;
import com.unlockops.contracts.v2.WorkflowTypes.*;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/reclaim")
public class ReclaimExecutionController {
    private final ReclaimExecutionService service;
    private final WorkflowStore db;
    public ReclaimExecutionController(ReclaimExecutionService service,WorkflowStore db) {this.service=service;this.db=db;}
    @GetMapping("/targets/{id}/execution")
    public ReclaimExecutionState state(@AuthenticationPrincipal AppUser user,@PathVariable UUID id) {return service.state(user.id(),id);}
    @PostMapping("/targets/{id}/revoke")
    public ReclaimExecutionReceipt revoke(@AuthenticationPrincipal AppUser user,@PathVariable UUID id,
            @RequestHeader("Idempotency-Key") String key,@RequestBody JsonNode body) {
        return service.revoke(user.id(),id,key,db.decode(body,ReclaimRevokeInput.class));
    }
    @GetMapping("/executions")
    public ReclaimExecutionPage history(@AuthenticationPrincipal AppUser user,@RequestParam(defaultValue="0") int cursor) {return service.history(user.id(),cursor);}
    @ExceptionHandler(ReclaimExecutionService.ExecutionConflict.class)
    public ResponseEntity<ReclaimExecutionError> conflict(ReclaimExecutionService.ExecutionConflict e) {
        return ResponseEntity.status(409).body(db.checked(new ReclaimExecutionError(e.getReason(),e.code(),e.receiptId()),ReclaimExecutionError.class));
    }
}
