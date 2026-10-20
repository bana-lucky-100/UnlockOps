package com.unlockops.messaging.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.unlockops.common.json.Jsons;
import com.unlockops.messaging.model.AgentMode;
import com.unlockops.problem.model.ProblemStatus;
import java.util.Objects;

@JsonIgnoreProperties(ignoreUnknown = true)
public record AgentResult(ProblemStatus status, String reasonCode, String diagnosis, String proposal,
                          JsonNode evidence, JsonNode plan, @JsonProperty("verification_ok") Boolean verificationOk,
                          @JsonProperty("agent_mode") AgentMode agentMode) {
    public AgentResult {
        Objects.requireNonNull(status, "status is required");
        Objects.requireNonNull(reasonCode, "reasonCode is required");
        Objects.requireNonNull(proposal, "proposal is required");
    }

    public static AgentResult parse(JsonNode raw, Jsons json) {
        if (!(raw instanceof ObjectNode object)) throw new IllegalArgumentException("Unknown result event");
        ObjectNode normalized = object.deepCopy();
        // Old queue/checkpoint payloads stay unchanged in the audit log.
        if ("ON_HOLD".equals(normalized.path("status").asText())) normalized.put("status", "REJECTED");
        if ("INSUFFICIENT_BUDGET".equals(normalized.path("reasonCode").asText()))
            normalized.put("reasonCode", "BUDGET_INSUFFICIENT");
        if (!normalized.has("evidence")) normalized.putArray("evidence");
        return json.read(normalized, AgentResult.class);
    }
}
