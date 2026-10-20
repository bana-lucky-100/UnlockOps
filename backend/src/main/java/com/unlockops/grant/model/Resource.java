package com.unlockops.grant.model;

import java.util.UUID;

public record Resource(UUID id, Platform platform, String externalId, AccessScope accessScope,
                       UUID ownerDepartmentId, UUID tfId, SecurityGrade securityGrade,
                       UUID designatedDepartmentId) {}
