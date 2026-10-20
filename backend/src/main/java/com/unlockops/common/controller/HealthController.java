package com.unlockops.common.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {
    public record HealthResponse(String status) {}

    @GetMapping("/api/health")
    public HealthResponse health() { return new HealthResponse("UP"); }
}
