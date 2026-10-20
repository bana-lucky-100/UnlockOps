package com.unlockops.problem.dto;

import com.unlockops.grant.model.Platform;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public final class ProblemRequests {
    private ProblemRequests() {}

    public record Create(@NotNull Platform platform, @NotBlank @Size(max = 5000) String contents,
                         boolean simulateJiraFailure) {}

    public record Decision(boolean approved, @NotBlank @Size(max = 64) String expectedPlanHash,
                           @Size(max = 1000) String reason) {
        public String normalizedReason() { return reason == null ? "" : reason.strip(); }
    }
}
