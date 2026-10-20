package com.unlockops.grant.model;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import com.fasterxml.jackson.annotation.JsonPropertyOrder;
import java.util.UUID;

/** The six-field wire contract is also the canonical input to the Python plan digest. */
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
@JsonPropertyOrder(alphabetic = true)
public record GrantPlan(UUID problemId, UUID requesterId, Platform platform, UUID resourceId,
                        String resourceKey, SaasRole requestedRole) {}
