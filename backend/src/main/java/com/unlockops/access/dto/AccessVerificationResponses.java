package com.unlockops.access.dto;

import com.unlockops.access.dto.AccessContextResponses.Current;

public final class AccessVerificationResponses {
    private AccessVerificationResponses() {}
    public record Verified(boolean ok, boolean verified, Current current) {}
}
