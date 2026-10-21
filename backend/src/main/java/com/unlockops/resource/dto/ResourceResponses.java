package com.unlockops.resource.dto;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import com.unlockops.grant.model.*;
import com.unlockops.resource.model.ResourceCandidate;
import java.util.List;
import java.util.UUID;

public final class ResourceResponses {
    private ResourceResponses() {}

    public record Resolved(List<Match> matches, boolean ambiguous) {}

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public record Match(UUID id, Platform platform, String externalId, String name, List<String> aliases,
                        AccessScope accessScope, UUID ownerDepartmentId, UUID tfId,
                        SecurityGrade securityGrade, UUID designatedDepartmentId) {
        public static Match from(ResourceCandidate resource) {
            return new Match(resource.id(), resource.platform(), resource.externalId(), resource.name(),
                resource.aliases(), resource.accessScope(), resource.ownerDepartmentId(), resource.tfId(),
                resource.securityGrade(), resource.designatedDepartmentId());
        }
    }
}
