package com.unlockops.problem.model;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import com.unlockops.messaging.model.EventKind;
import java.time.OffsetDateTime;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record ProblemEvent(EventKind kind, JsonNode payload, OffsetDateTime createdAt) {}
