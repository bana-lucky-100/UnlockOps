package com.unlockops;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.unlockops.common.json.Jsons;
import com.unlockops.problem.model.Problem;
import java.util.UUID;

final class ProblemFixtures {
    static final ObjectMapper MAPPER = new ObjectMapper().findAndRegisterModules();
    static final Jsons JSON = new Jsons(MAPPER);

    static ObjectNode row(UUID id, UUID requester, UUID approver) {
        ObjectNode row = MAPPER.createObjectNode().put("id", id.toString()).put("requester_id", requester.toString())
            .put("approver_id", approver.toString()).put("platform", "GITHUB").put("contents", "payment-core push가 안 됩니다")
            .put("status", "WAITING_APPROVAL").put("plan_hash", "private-hash");
        row.putArray("evidence").add("private-source");
        row.putObject("plan").put("problem_id", id.toString()).put("requester_id", requester.toString()).put("platform", "GITHUB")
            .put("resource_id", UUID.randomUUID().toString()).put("resource_key", "payment-core").put("requested_role", "Write");
        return row;
    }

    static Problem problem(ObjectNode row) { return JSON.read(row, Problem.class); }
}
