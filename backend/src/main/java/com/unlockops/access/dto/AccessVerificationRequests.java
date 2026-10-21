package com.unlockops.access.dto;

import com.unlockops.grant.model.Platform;
import jakarta.validation.constraints.*;
import java.util.UUID;

public final class AccessVerificationRequests {
    private AccessVerificationRequests() {}

    // Can edit는 기존 모의 DB 보유 권한도 검증하기 위한 값이며 자동 부여 범위를 늘리지 않는다.
    public record Verify(@NotNull UUID employeeId, @NotNull UUID resourceId, @NotNull Platform platform,
                         @NotBlank @Pattern(regexp = "Read|Write|Viewer|Developer|Can view|Can edit|Member|Seat") String requestedRole) {}
}
