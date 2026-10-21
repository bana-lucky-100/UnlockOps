package com.unlockops.grant.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public final class GrantExecutionRequests {
    private GrantExecutionRequests() {}
    public record Execute(@NotBlank @Size(max = 150) String idempotencyKey) {}
}
