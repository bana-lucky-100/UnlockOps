package com.unlockops.grant.controller;

import com.unlockops.grant.dto.GrantExecutionRequests.Execute;
import com.unlockops.grant.dto.GrantExecutionResponses.Success;
import com.unlockops.grant.service.GrantExecutionService;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/internal/problems")
public class InternalGrantController {
    private final GrantExecutionService service;
    public InternalGrantController(GrantExecutionService service) { this.service = service; }

    @PostMapping("/{id}/grant")
    public Success execute(@PathVariable UUID id, @RequestBody @Valid Execute request) {
        return service.execute(id, request.idempotencyKey());
    }
}
