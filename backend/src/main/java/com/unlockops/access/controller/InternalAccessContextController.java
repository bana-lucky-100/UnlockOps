package com.unlockops.access.controller;

import com.unlockops.access.dto.AccessContextRequests.Lookup;
import com.unlockops.access.dto.AccessContextResponses.Context;
import com.unlockops.access.service.AccessContextService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/internal/access-context")
public class InternalAccessContextController {
    private final AccessContextService service;
    public InternalAccessContextController(AccessContextService service) { this.service = service; }

    @PostMapping
    public Context lookup(@RequestBody @Valid Lookup request) { return service.lookup(request); }
}
