package com.unlockops.phase2.reclaim;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.auth.model.AppUser;
import com.unlockops.contracts.v2.Phase2Types.*;
import com.unlockops.phase2.common.Phase2Store;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/reclaim")
public class ReclaimController {
    private final ReclaimWorkflowService service;
    private final Phase2Store db;
    public ReclaimController(ReclaimWorkflowService service,Phase2Store db) {this.service=service;this.db=db;}
    @GetMapping("/scopes") public List<JsonNode> scopes(@AuthenticationPrincipal AppUser user) {return service.scopes(user.id());}
    @GetMapping("/overview") public Map<String,Object> overview(@AuthenticationPrincipal AppUser user) {return service.overview(user.id());}
    @PostMapping("/runs") @ResponseStatus(HttpStatus.ACCEPTED)
    public ReclaimRunView start(@AuthenticationPrincipal AppUser user,@RequestHeader("Idempotency-Key") String key,@RequestBody JsonNode body) {
        return service.start(user.id(),UUID.fromString(db.decode(body,ReclaimStartInput.class).scopeId()),key);
    }
    @GetMapping("/runs/{id}") public ReclaimRunView run(@AuthenticationPrincipal AppUser user,@PathVariable UUID id) {return service.get(user.id(),id);}
    @GetMapping("/runs/{id}/items") public List<JsonNode> items(@AuthenticationPrincipal AppUser user,@PathVariable UUID id) {return service.items(user.id(),id);}
    @GetMapping("/targets/{id}") public ReclaimCandidate target(@AuthenticationPrincipal AppUser user,@PathVariable UUID id) {return service.target(user.id(),id);}
    @GetMapping("/notifications") public List<JsonNode> notifications(@AuthenticationPrincipal AppUser user) {return service.notifications(user.id());}
    @PatchMapping("/notifications/{id}/read") public Map<String,String> read(@AuthenticationPrincipal AppUser user,@PathVariable UUID id) {return service.read(user.id(),id);}
}
