package com.unlockops;

import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ProblemViewsTest {
    @Test void requesterProjectionUsesAnAllowlistIncludingFutureColumns() {
        Map<String,Object> row=new LinkedHashMap<>();
        row.put("id",UUID.randomUUID()); row.put("status","WAITING_APPROVAL");
        row.put("proposal","담당자의 승인을 기다립니다."); row.put("decision_reason",null);
        for(String field:List.of("plan_hash","approved_plan_hash","plan","plan_json","evidence",
                "evidence_json","thread_id","idempotency_key","future_internal_field")) row.put(field,"private");
        assertEquals(Set.of("id","status","proposal","decision_reason"),ProblemViews.requester(row).keySet());
    }

    @Test void requesterEventsCannotLeakNestedResultEvidenceOrToolCalls() {
        var events=List.<Map<String,Object>>of(
            Map.of("kind","PROGRESS","created_at","now","payload",Map.of(
                "job_type","ANALYZE","node","collect_evidence","details",List.of(Map.of("tools","private-tool")))),
            Map.of("kind","ANALYZED","created_at","now","payload",Map.of("result",Map.of(
                "status","WAITING_APPROVAL","plan_hash","private-hash","evidence",List.of("private-source")))),
            Map.of("kind","HUMAN_DECISION","created_at","now","payload",Map.of("approved",true,"actor_id","private-actor")));
        var visible=ProblemViews.publicEvents(events);
        assertEquals(3,visible.size());
        for(var event:visible) assertEquals(Set.of("message"),((Map<?,?>)event.get("payload")).keySet());
        assertFalse(visible.toString().contains("private-"));
        assertEquals("담당자가 승인했습니다.",((Map<?,?>)visible.getLast().get("payload")).get("message"));
    }

    @Test void oldQueueResultIsNormalizedWithoutChangingAuditOrText() {
        var raw=Map.<String,Object>of("status","ON_HOLD","reasonCode","INSUFFICIENT_BUDGET",
            "diagnosis","original cause","proposal","original proposal");
        var normalized=AgentResults.normalizeResult(raw);
        assertEquals("REJECTED",normalized.get("status"));
        assertEquals("BUDGET_INSUFFICIENT",normalized.get("reasonCode"));
        assertEquals("original cause",normalized.get("diagnosis"));
        assertEquals("original proposal",normalized.get("proposal"));
        assertEquals("ON_HOLD",raw.get("status"));
    }
}
