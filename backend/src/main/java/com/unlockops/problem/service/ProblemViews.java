package com.unlockops.problem.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.messaging.model.JobType;
import com.unlockops.problem.dto.ProblemResponses.*;
import com.unlockops.problem.model.*;
import java.util.ArrayList;
import java.util.List;

/** Builds public DTOs without reusing internal JSON or audit payloads. */
public final class ProblemViews {
    private ProblemViews() {}

    public static Requester requester(Problem p, List<PublicEvent> events) {
        return new Requester(p.id(), p.requesterId(), p.approverId(), p.platform(), p.contents(), p.status(),
            p.reasonCode(), p.diagnosis(), p.proposal(), p.resourceId(), p.requestedRole(),
            p.decisionReason(), p.decidedAt(), p.verificationOk(), p.createdAt(), p.updatedAt(),
            p.requesterName(), p.employeeNo(), events);
    }

    public static List<PublicEvent> publicEvents(List<ProblemEvent> events) {
        List<PublicEvent> result = new ArrayList<>();
        String previous = "";
        for (ProblemEvent event : events) {
            JsonNode payload = event.payload();
            if (payload == null || !payload.isObject()) continue;
            String message = switch (event.kind()) {
                case PROGRESS -> JobType.EXECUTE.name().equals(payload.path("job_type").asText())
                    ? "권한 반영을 진행하고 있습니다." : "요청을 분석하고 있습니다.";
                case HUMAN_DECISION -> payload.path("approved").asBoolean(false)
                    ? "담당자가 승인했습니다." : "담당자가 반려했습니다.";
                case ANALYZED, EXECUTED -> statusMessage(payload.path("result").path("status").asText());
                case FAILED -> "처리가 완료되지 않아 담당자 확인이 필요합니다.";
            };
            String key = event.kind() + ":" + message;
            if (message.isEmpty() || key.equals(previous)) continue;
            result.add(new PublicEvent(event.kind(), new Message(message), event.createdAt()));
            previous = key;
        }
        return List.copyOf(result);
    }

    private static String statusMessage(String status) {
        // ON_HOLD can remain in immutable historical audit payloads.
        if ("ON_HOLD".equals(status)) status = ProblemStatus.REJECTED.name();
        ProblemStatus parsed;
        try { parsed = ProblemStatus.valueOf(status); }
        catch (IllegalArgumentException e) { return ""; }
        return switch (parsed) {
            case WAITING_APPROVAL -> "담당자의 승인을 기다리고 있습니다.";
            case MANUAL_REVIEW -> "담당자 검토가 필요합니다.";
            case REJECTED -> "요청이 거절되었습니다. 안내 내용을 확인해 주세요.";
            case DONE -> "필요한 권한의 반영을 확인했습니다.";
            case FAILED -> "처리가 완료되지 않아 담당자 확인이 필요합니다.";
            default -> "";
        };
    }
}
