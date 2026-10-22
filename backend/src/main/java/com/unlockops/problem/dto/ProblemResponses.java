package com.unlockops.problem.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonUnwrapped;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import com.unlockops.grant.model.*;
import com.unlockops.messaging.model.AgentMode;
import com.unlockops.messaging.model.EventKind;
import com.unlockops.problem.model.*;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

public final class ProblemResponses {
    private ProblemResponses() {}

    public sealed interface View permits Requester, Assigned, Detail {}

    public record Status(UUID id, ProblemStatus status) {}

    /** An explicit public allowlist, independent of database/internal model fields. */
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public record Requester(
        UUID id, UUID requesterId, UUID approverId, Platform platform, String contents, ProblemStatus status, ResultType resultType,
        String reasonCode, String diagnosis, String proposal, UUID resourceId, SaasRole requestedRole,
        String decisionReason, OffsetDateTime decidedAt, Boolean verificationOk,
        OffsetDateTime createdAt, OffsetDateTime updatedAt, String requesterName, String employeeNo,
        @JsonInclude(JsonInclude.Include.NON_NULL) List<PublicEvent> events) implements View {}

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public record Assigned(
        UUID id, Platform platform, String contents, ProblemStatus status, ResultType resultType, String reasonCode,
        String diagnosis, String proposal, UUID approverId, SaasRole requestedRole, String planHash,
        Boolean verificationOk, AgentMode agentMode, OffsetDateTime createdAt, OffsetDateTime updatedAt,
        String requesterName, String employeeNo) implements View {
        public static Assigned from(Problem p) {
            return new Assigned(p.id(), p.platform(), p.contents(), p.status(), p.resultType(), p.reasonCode(),
                p.diagnosis(), p.proposal(), p.approverId(), p.requestedRole(), p.planHash(),
                p.verificationOk(), p.agentMode(), p.createdAt(), p.updatedAt(), p.requesterName(), p.employeeNo());
        }
    }

    public record Detail(@JsonUnwrapped Problem problem, List<ProblemEvent> events) implements View {}

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public record PublicEvent(EventKind kind, Message payload, OffsetDateTime createdAt) {}
    public record Message(String message) {}
}
