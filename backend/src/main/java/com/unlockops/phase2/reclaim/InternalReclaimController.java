package com.unlockops.phase2.reclaim;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.contracts.v2.Phase2Types.*;
import com.unlockops.phase2.common.Phase2Store;
import java.util.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/internal/v2/reclaim")
public class InternalReclaimController {
    private final ReclaimSnapshotService snapshots;
    private final Phase2Store db;
    public InternalReclaimController(ReclaimSnapshotService snapshots,Phase2Store db) {this.snapshots=snapshots;this.db=db;}
    @PostMapping("/context") public Map<String,Object> context(@RequestBody JsonNode body) {return snapshots.context(UUID.fromString(db.decode(body,ReclaimContextRequest.class).runId()));}
    @PostMapping("/candidates") public CandidatePage candidates(@RequestBody JsonNode body) {return snapshots.page(db.decode(body,CandidatePageRequest.class));}
    @PostMapping("/notification-history") public List<JsonNode> history(@RequestBody JsonNode body) {return snapshots.history(db.decode(body,NotificationHistoryRequest.class));}
}
