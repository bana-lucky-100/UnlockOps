package com.unlockops.access.controller;

import com.unlockops.access.dto.AccessVerificationRequests.Verify;
import com.unlockops.access.dto.AccessVerificationResponses.Verified;
import com.unlockops.access.service.AccessVerificationService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/internal/access-verifications")
public class InternalAccessVerificationController {
    private final AccessVerificationService service;
    public InternalAccessVerificationController(AccessVerificationService service) { this.service = service; }

    @PostMapping
    public Verified verify(@RequestBody @Valid Verify request) { return service.verify(request); }
}
