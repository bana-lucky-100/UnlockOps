package com.unlockops;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Requester responses never reuse the internal row or raw audit envelope. */
final class ProblemViews {
    private static final List<String> PUBLIC_FIELDS=List.of(
        "id","requester_id","approver_id","platform","contents","status","reason_code",
        "diagnosis","proposal","resource_id","requested_role","decision_reason","decided_at",
        "verification_ok","created_at","updated_at","requester_name","employee_no");

    private ProblemViews() {}

    static Map<String,Object> requester(Map<String,Object> row) {
        Map<String,Object> result=new LinkedHashMap<>();
        for(String field:PUBLIC_FIELDS) if(row.containsKey(field)) result.put(field,row.get(field));
        return result;
    }

    static List<Map<String,Object>> publicEvents(List<Map<String,Object>> events) {
        List<Map<String,Object>> result=new ArrayList<>();
        String previous="";
        for(var event:events) {
            if(!(event.get("payload") instanceof Map<?,?> payload)) continue;
            String kind=String.valueOf(event.get("kind"));
            String message=switch(kind) {
                case "PROGRESS" -> "EXECUTE".equals(payload.get("job_type"))
                    ? "권한 반영을 진행하고 있습니다." : "요청을 분석하고 있습니다.";
                case "HUMAN_DECISION" -> Boolean.TRUE.equals(payload.get("approved"))
                    ? "담당자가 승인했습니다." : "담당자가 반려했습니다.";
                case "ANALYZED","EXECUTED" -> payload.get("result") instanceof Map<?,?> outcome
                    ? statusMessage(String.valueOf(outcome.get("status"))) : "";
                case "FAILED" -> "처리가 완료되지 않아 담당자 확인이 필요합니다.";
                default -> "";
            };
            String key=kind+":"+message;
            if(message.isEmpty() || key.equals(previous)) continue;
            Map<String,Object> item=new LinkedHashMap<>();
            item.put("kind",kind); item.put("payload",Map.of("message",message));
            item.put("created_at",event.get("created_at")); result.add(item); previous=key;
        }
        return result;
    }

    private static String statusMessage(String status) {
        return switch(status) {
            case "WAITING_APPROVAL" -> "담당자의 승인을 기다리고 있습니다.";
            case "MANUAL_REVIEW" -> "담당자 검토가 필요합니다.";
            case "REJECTED","ON_HOLD" -> "요청이 거절되었습니다. 안내 내용을 확인해 주세요.";
            case "DONE" -> "필요한 권한의 반영을 확인했습니다.";
            case "FAILED" -> "처리가 완료되지 않아 담당자 확인이 필요합니다.";
            default -> "";
        };
    }
}
