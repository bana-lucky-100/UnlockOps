package com.unlockops.messaging.dto;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import com.unlockops.grant.model.Platform;
import com.unlockops.messaging.model.JobType;
import java.util.UUID;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record JobMessage(UUID eventId, JobType jobType, UUID problemId, UUID requesterId,
                         Platform platform, String contents, String idempotencyKey, String planHash) {}
