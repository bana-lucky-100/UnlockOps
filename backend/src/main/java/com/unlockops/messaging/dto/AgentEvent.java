package com.unlockops.messaging.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import com.unlockops.messaging.model.*;
import java.util.Objects;
import java.util.UUID;

@JsonIgnoreProperties(ignoreUnknown = true)
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record AgentEvent(UUID eventId, UUID problemId, JobType jobType, EventKind kind,
                         JsonNode result, String errorCode) {
    public AgentEvent {
        Objects.requireNonNull(eventId, "event_id is required");
        Objects.requireNonNull(problemId, "problem_id is required");
        Objects.requireNonNull(jobType, "job_type is required");
        Objects.requireNonNull(kind, "kind is required");
    }
}
