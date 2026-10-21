package com.unlockops.resource.model;

import com.unlockops.grant.model.*;
import java.util.List;
import java.util.UUID;

public record ResourceCandidate(UUID id, Platform platform, String externalId, String name,
                                List<String> aliases, AccessScope accessScope, UUID ownerDepartmentId,
                                UUID tfId, SecurityGrade securityGrade, UUID designatedDepartmentId) {}
