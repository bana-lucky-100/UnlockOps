package com.unlockops.access.dto;

import com.unlockops.grant.model.Platform;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.AssertTrue;
import java.util.UUID;

public final class AccessContextRequests {
    private AccessContextRequests() {}

    public record Lookup(@NotNull UUID employeeId, UUID resourceId, Platform platform, boolean includeBudget) {
        public Lookup(UUID employeeId, UUID resourceId, Platform platform) { this(employeeId, resourceId, platform, false); }

        @AssertTrue(message = "플랫폼 조회에는 자원 ID가 필요합니다.")
        public boolean isScopeValid() { return resourceId != null || platform == null; }
    }
}
