package com.unlockops.auth.model;

import java.util.UUID;

public record EmployeeProfile(UUID id, UserRole role, UUID departmentId, JobGrade jobGrade,
                              JobFamily jobFamily, UUID headId) {}
