package com.unlockops.auth.dto;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import com.unlockops.auth.model.*;
import java.util.UUID;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record UserProfileResponse(UUID id, String loginId, String employeeNo, String name,
                                  UserRole role, JobGrade jobGrade, JobFamily jobFamily, String department) {}
