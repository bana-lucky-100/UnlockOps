package com.unlockops.grant.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.unlockops.grant.model.SaasRole;

public final class GrantExecutionResponses {
    private GrantExecutionResponses() {}
    public record Success(boolean ok, boolean changed, SaasRole role) {
        public Success {
            if (!ok || role == null) throw new IllegalArgumentException("Invalid grant receipt");
        }
        public Success(boolean changed, SaasRole role) { this(true, changed, role); }
    }
    public record Failure(boolean ok, Error error) {}
    public record Error(String code, String message, boolean retryable,
                        @JsonInclude(JsonInclude.Include.NON_NULL) String reason) {}
}
