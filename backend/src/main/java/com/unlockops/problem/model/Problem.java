package com.unlockops.problem.model;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import com.unlockops.grant.model.*;
import com.unlockops.messaging.model.AgentMode;
import java.time.OffsetDateTime;
import java.util.UUID;

/** A persisted snapshot; never returned directly to a requester. */
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record Problem(
    UUID id, UUID requesterId, UUID approverId, Platform platform, String contents, ProblemStatus status, ResultType resultType,
    String diagnosis, String proposal, UUID resourceId, SaasRole requestedRole, JsonNode evidence,
    String reasonCode, String decisionReason, DecisionSource decisionSource, UUID decidedBy,
    OffsetDateTime decidedAt, String threadId, String idempotencyKey, GrantPlan plan, String planHash,
    String approvedPlanHash, Boolean verificationOk, AgentMode agentMode, boolean simulateJiraFailure,
    OffsetDateTime createdAt, OffsetDateTime updatedAt, String requesterName, String employeeNo) {}
