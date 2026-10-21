package com.unlockops.resource.controller;

import com.unlockops.resource.dto.ResourceRequests.Resolve;
import com.unlockops.resource.dto.ResourceResponses.Resolved;
import com.unlockops.resource.service.ResourceService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/internal/resources")
public class InternalResourceController {
    private final ResourceService service;
    public InternalResourceController(ResourceService service) { this.service = service; }

    @PostMapping("/resolve")
    public Resolved resolve(@RequestBody @Valid Resolve request) { return service.resolve(request); }
}
