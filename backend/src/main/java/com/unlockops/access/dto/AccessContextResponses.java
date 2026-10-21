package com.unlockops.access.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import com.unlockops.auth.model.JobFamily;
import com.unlockops.auth.model.JobGrade;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public final class AccessContextResponses {
    private AccessContextResponses() {}

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public record Context(Profile profile, UUID resourceId, Membership membership, Current current,
                          String maximumRole, Budget budget, String ruleSource, Map<String, String> sourceHashes) {}

    /** 기존 직원 조회에 필요한 필드만 반환한다. 로그인 정보·이메일·비밀번호는 포함하지 않는다. */
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public record Profile(UUID id, String employeeNo, String name, UUID departmentId, String departmentName,
                          JobGrade jobGrade, JobFamily jobFamily, UUID headId) {}

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public record Membership(UUID tfId, boolean member, UUID leaderId) {}

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public record Current(String role, String source,
                          @JsonInclude(JsonInclude.Include.NON_NULL) List<String> teams,
                          @JsonInclude(JsonInclude.Include.NON_NULL) Boolean canBrowse) {}

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public record Budget(UUID departmentId, String remainingMonthlyAmount, String unitMonthlyPrice,
                         String currency, OffsetDateTime updatedAt) {}
}
