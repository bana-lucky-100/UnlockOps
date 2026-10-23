package com.unlockops;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.messaging.dto.AgentResult;
import com.unlockops.messaging.model.EventKind;
import com.unlockops.problem.model.*;
import com.unlockops.problem.service.ProblemViews;
import java.util.*;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ProblemViewsTest {
    @Test void historicalGuidanceIsNormalizedWithoutEditingAudit() {
        var raw = ProblemFixtures.JSON.tree("""
            {"status":"MANUAL_REVIEW","reasonCode":"RAG_GUIDANCE","proposal":"점검 안내"}
            """);
        var normalized = AgentResult.parse(raw, ProblemFixtures.JSON);
        assertEquals(ProblemStatus.DONE, normalized.status());
        assertEquals(ResultType.GUIDANCE, normalized.resultType());
        assertNull(normalized.verificationOk());
        assertEquals("MANUAL_REVIEW", raw.path("status").asText());
        var envelope = ProblemFixtures.MAPPER.createObjectNode();
        envelope.set("result", raw);
        assertEquals("안내가 완료됐어요", ProblemViews.publicEvents(List.of(
            new ProblemEvent(EventKind.ANALYZED, envelope, null))).getFirst().payload().message());
    }

    @Test void emptyGuidanceDoesNotBecomeDone() {
        var raw = ProblemFixtures.JSON.tree("""
            {"status":"MANUAL_REVIEW","reasonCode":"RAG_GUIDANCE","proposal":" "}
            """);
        assertEquals(ProblemStatus.MANUAL_REVIEW, AgentResult.parse(raw, ProblemFixtures.JSON).status());
    }

    @Test void completionCannotMisrepresentPermissionVerification() {
        for (String payload : List.of(
            "{\"status\":\"DONE\",\"result_type\":\"GUIDANCE\",\"verification_ok\":true}",
            "{\"status\":\"DONE\",\"result_type\":\"ACCESS_VERIFIED\",\"verification_ok\":false}",
            "{\"status\":\"MANUAL_REVIEW\",\"result_type\":\"GUIDANCE\"}")) {
            var raw = (com.fasterxml.jackson.databind.node.ObjectNode) ProblemFixtures.JSON.tree(payload);
            raw.put("reasonCode", "TEST").put("proposal", "안내");
            assertThrows(IllegalArgumentException.class, () -> AgentResult.parse(raw, ProblemFixtures.JSON));
        }
    }

    @Test void requesterProjectionUsesAnAllowlistIncludingFutureColumns() {
        var row = ProblemFixtures.row(UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID());
        row.put("thread_id", "private-thread").put("idempotency_key", "private-key").put("approved_plan_hash", "private-hash");
        JsonNode result = ProblemFixtures.MAPPER.valueToTree(ProblemViews.requester(ProblemFixtures.problem(row), null));
        Set<String> fields = StreamSupport.stream(((Iterable<String>) result::fieldNames).spliterator(), false).collect(Collectors.toSet());
        assertEquals(Set.of("id", "requester_id", "approver_id", "platform", "contents", "status", "reason_code", "diagnosis",
            "result_type", "proposal", "resource_id", "requested_role", "decision_reason", "decided_at", "verification_ok",
            "created_at", "updated_at", "requester_name", "employee_no"), fields);
        assertFalse(result.toString().contains("private-"));
    }

    @Test void requesterEventsCannotLeakNestedResultEvidenceOrToolCalls() {
        var events = List.of(
            new ProblemEvent(EventKind.PROGRESS, ProblemFixtures.JSON.tree("""
                {"job_type":"ANALYZE","node":"collect_evidence","details":[{"tools":"private-tool"}]}
                """), null),
            new ProblemEvent(EventKind.ANALYZED, ProblemFixtures.JSON.tree("""
                {"result":{"status":"WAITING_APPROVAL","plan_hash":"private-hash","evidence":["private-source"]}}
                """), null),
            new ProblemEvent(EventKind.HUMAN_DECISION, ProblemFixtures.JSON.tree("""
                {"approved":true,"actor_id":"private-actor"}
                """), null));
        var visible = ProblemViews.publicEvents(events);
        assertEquals(3, visible.size());
        assertFalse(visible.toString().contains("private-"));
        assertEquals("담당자가 승인했습니다.", visible.getLast().payload().message());
    }

    @Test void oldQueueResultIsNormalizedWithoutChangingAuditOrText() {
        var raw = ProblemFixtures.JSON.tree("""
            {"status":"ON_HOLD","reasonCode":"INSUFFICIENT_BUDGET","diagnosis":"original cause","proposal":"original proposal"}
            """);
        var normalized = AgentResult.parse(raw, ProblemFixtures.JSON);
        assertEquals(ProblemStatus.REJECTED, normalized.status());
        assertEquals("BUDGET_INSUFFICIENT", normalized.reasonCode());
        assertEquals("original cause", normalized.diagnosis());
        assertEquals("original proposal", normalized.proposal());
        assertEquals("ON_HOLD", raw.path("status").asText());
    }
}
