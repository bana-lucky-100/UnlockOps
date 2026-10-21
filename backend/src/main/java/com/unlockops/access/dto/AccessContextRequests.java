package com.unlockops.access.dto;

import com.unlockops.grant.model.Platform;
import jakarta.validation.constraints.NotNull;
import java.util.UUID;

public final class AccessContextRequests {
    private AccessContextRequests() {}

    public record Lookup(@NotNull UUID employeeId, @NotNull UUID resourceId, @NotNull Platform platform) {}
}
