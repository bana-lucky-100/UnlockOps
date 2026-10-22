package com.unlockops.messaging.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.unlockops.common.json.Jsons;
import com.unlockops.messaging.model.AgentMode;
import com.unlockops.problem.model.ProblemStatus;
import com.unlockops.problem.model.ResultType;
import java.util.Objects;

@JsonIgnoreProperties(ignoreUnknown = true)
public record AgentResult(ProblemStatus status, @JsonProperty("result_type") ResultType resultType,
                          String reasonCode, String diagnosis, String proposal,
                          JsonNode evidence, JsonNode plan, @JsonProperty("verification_ok") Boolean verificationOk,
                          @JsonProperty("agent_mode") AgentMode agentMode) {
    public AgentResult {
        Objects.requireNonNull(status, "status is required");
        Objects.requireNonNull(reasonCode, "reasonCode is required");
        Objects.requireNonNull(proposal, "proposal is required");
        if (status != ProblemStatus.DONE && resultType != null)
            throw new IllegalArgumentException("Only DONE can have a result_type");
        if (status == ProblemStatus.DONE) {
            if (resultType == ResultType.GUIDANCE) {
                if (proposal.isBlank() || (plan != null && !plan.isNull()) || verificationOk != null)
                    throw new IllegalArgumentException("Guidance cannot claim a grant or verification");
            } else if (resultType != ResultType.ACCESS_VERIFIED || !Boolean.TRUE.equals(verificationOk)) {
                throw new IllegalArgumentException("Access completion requires verification");
            }
        }
    }

    public static AgentResult parse(JsonNode raw, Jsons json) {
        if (!(raw instanceof ObjectNode object)) throw new IllegalArgumentException("Unknown result event");
        ObjectNode normalized = object.deepCopy();
        // Old queue/checkpoint payloads stay unchanged in the audit log.
        if ("ON_HOLD".equals(normalized.path("status").asText())) normalized.put("status", "REJECTED");
        if ("INSUFFICIENT_BUDGET".equals(normalized.path("reasonCode").asText()))
            normalized.put("reasonCode", "BUDGET_INSUFFICIENT");
        if (!normalized.has("evidence")) normalized.putArray("evidence");
        if (!normalized.has("result_type")) {
            if ("MANUAL_REVIEW".equals(normalized.path("status").asText())
                    && "RAG_GUIDANCE".equals(normalized.path("reasonCode").asText())
                    && normalized.path("proposal").isTextual() && !normalized.path("proposal").asText().isBlank()
                    && !normalized.hasNonNull("plan") && !normalized.hasNonNull("verification_ok")) {
                normalized.put("status", "DONE").put("result_type", "GUIDANCE");
            } else if ("DONE".equals(normalized.path("status").asText())
                    && normalized.path("verification_ok").isBoolean() && normalized.path("verification_ok").booleanValue()) {
                normalized.put("result_type", "ACCESS_VERIFIED");
            }
        }
        return json.read(normalized, AgentResult.class);
    }
}
