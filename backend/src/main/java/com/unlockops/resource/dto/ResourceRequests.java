package com.unlockops.resource.dto;

import com.unlockops.grant.model.Platform;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public final class ResourceRequests {
    private ResourceRequests() {}

    public record Resolve(@NotNull Platform platform, @NotNull @Size(max = 5000) String hint) {}
}
