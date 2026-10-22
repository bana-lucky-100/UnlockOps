package com.unlockops.problem.controller;

import com.unlockops.auth.model.AppUser;
import com.unlockops.problem.dto.ProblemRequests.*;
import com.unlockops.problem.dto.ProblemResponses.*;
import com.unlockops.problem.service.ProblemService;
import com.unlockops.approval.service.ApprovalDecisionService;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/problems")
public class ProblemController {
    private final ProblemService service;
    private final ApprovalDecisionService decisions;
    public ProblemController(ProblemService service, ApprovalDecisionService decisions) {
        this.service = service;
        this.decisions = decisions;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.ACCEPTED)
    public Status create(@AuthenticationPrincipal AppUser user, @RequestBody @Valid Create request,
                         @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey) {
        return service.create(user, request, idempotencyKey);
    }

    @GetMapping
    public List<? extends View> list(@AuthenticationPrincipal AppUser user,
                                    @RequestParam(defaultValue = "false") boolean mine) {
        return service.list(user, mine);
    }

    @GetMapping("/{id}")
    public View detail(@AuthenticationPrincipal AppUser user, @PathVariable UUID id) { return service.detail(user, id); }

    @PostMapping("/{id}/decision")
    public Status decide(@AuthenticationPrincipal AppUser user, @PathVariable UUID id, @RequestBody @Valid Decision request) {
        return decisions.decide(user, id, request);
    }
}
