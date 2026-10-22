package com.unlockops.problem.repository;

import com.unlockops.common.json.Jsons;
import com.unlockops.grant.model.*;
import com.unlockops.messaging.model.AgentMode;
import com.unlockops.problem.model.*;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProblemRepository {
    private static final String SELECT = """
        SELECT p.*,p.evidence::text evidence_json,p.plan::text plan_json,u.name requester_name,u.employee_no
        FROM problems p JOIN users u ON u.id=p.requester_id
        """;
    private final JdbcTemplate jdbc;
    private final Jsons json;

    public ProblemRepository(JdbcTemplate jdbc, Jsons json) { this.jdbc = jdbc; this.json = json; }

    public boolean insertIfNew(UUID id, UUID requester, UUID approver, Platform platform, String contents,
                               boolean simulateFailure, ClientRequestKey key) {
        return jdbc.update("""
            INSERT INTO problems(id,requester_id,approver_id,platform,contents,thread_id,simulate_jira_failure,client_request_key)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT (requester_id,client_request_key) WHERE client_request_key IS NOT NULL DO NOTHING
            """, id, requester, approver, platform.name(), contents, id.toString(), simulateFailure,
            key == null ? null : key.value()) == 1;
    }

    public Optional<Problem> findByClientRequestKey(UUID requester, ClientRequestKey key) {
        return jdbc.query(SELECT + " WHERE p.requester_id=? AND p.client_request_key=?", this::map,
            requester, key.value()).stream().findFirst();
    }

    public Optional<Problem> find(UUID id) {
        return jdbc.query(SELECT + " WHERE p.id=?", this::map, id).stream().findFirst();
    }

    public Optional<Problem> lock(UUID id) {
        return jdbc.query(SELECT + " WHERE p.id=? FOR UPDATE OF p", this::map, id).stream().findFirst();
    }

    public List<Problem> findMine(UUID requester) {
        return jdbc.query(SELECT + " WHERE p.requester_id=? ORDER BY p.created_at DESC LIMIT 100", this::map, requester);
    }

    public List<Problem> findAssigned(UUID approver, boolean operations) {
        String filter = operations ? "" : " WHERE p.approver_id=?";
        Object[] parameters = operations ? new Object[]{} : new Object[]{approver};
        return jdbc.query(SELECT + filter + " ORDER BY p.created_at DESC LIMIT 100", this::map, parameters);
    }

    public record DecisionUpdate(ProblemStatus status, String reason, UUID actor, String approvedPlanHash,
                                 String idempotencyKey, ServerReason reasonCode, String proposal) {}

    public void decide(UUID id, DecisionUpdate update) {
        jdbc.update("""
            UPDATE problems SET status=?,decision_reason=?,decision_source='HUMAN',decided_by=?,decided_at=NOW(),
              approved_plan_hash=?,idempotency_key=?,reason_code=?,proposal=?,updated_at=NOW() WHERE id=?
            """, update.status().name(), update.reason(), update.actor(), update.approvedPlanHash(),
            update.idempotencyKey(), update.reasonCode().name(), update.proposal(), id);
    }

    public void markDiagnosing(UUID id) {
        jdbc.update("UPDATE problems SET status='DIAGNOSING',updated_at=NOW() WHERE id=?", id);
    }

    public boolean startExecution(UUID id) {
        return jdbc.update("""
            UPDATE problems SET status='EXECUTING',proposal='승인이 기록되어 권한 부여를 진행하고 있습니다.',updated_at=NOW()
            WHERE id=? AND status='WAITING_APPROVAL'
            """, id) == 1;
    }

    public void markFailed(UUID id, String errorCode, String proposal) {
        jdbc.update("UPDATE problems SET status='FAILED',reason_code=?,proposal=?,updated_at=NOW() WHERE id=?",
            errorCode, proposal, id);
    }

    public record ExecutionUpdate(ProblemStatus status, String diagnosis, String proposal, String reasonCode,
                                  Boolean verificationOk, AgentMode agentMode, ResultType resultType) {}

    public void applyExecution(UUID id, ExecutionUpdate update) {
        jdbc.update("""
            UPDATE problems SET status=?,diagnosis=?,proposal=?,reason_code=?,verification_ok=?,
              agent_mode=?,result_type=?,updated_at=NOW() WHERE id=?
            """, update.status().name(), update.diagnosis(), update.proposal(), update.reasonCode(),
            update.verificationOk(), update.agentMode() == null ? null : update.agentMode().value(), update.resultType() == null ? null : update.resultType().name(), id);
    }

    public record AnalysisUpdate(ExecutionUpdate result, UUID approverId, UUID resourceId, SaasRole requestedRole,
                                 com.fasterxml.jackson.databind.JsonNode evidence, GrantPlan plan, String planHash) {}

    public void applyAnalysis(UUID id, AnalysisUpdate update) {
        ExecutionUpdate result = update.result();
        jdbc.update("""
            UPDATE problems SET status=?,approver_id=?,diagnosis=?,proposal=?,resource_id=?,requested_role=?,
              evidence=?::jsonb,reason_code=?,plan=?::jsonb,plan_hash=?,verification_ok=?,agent_mode=?,
              decision_source='AGENT',result_type=?,updated_at=NOW() WHERE id=?
            """, result.status().name(), update.approverId(), result.diagnosis(), result.proposal(),
            update.resourceId(), update.requestedRole() == null ? null : update.requestedRole().value(),
            json.write(update.evidence()), result.reasonCode(), update.plan() == null ? null : json.write(update.plan()),
            update.planHash(), result.verificationOk(), result.agentMode() == null ? null : result.agentMode().value(), result.resultType() == null ? null : result.resultType().name(), id);
    }

    private Problem map(ResultSet rs, int row) throws SQLException {
        String role = rs.getString("requested_role");
        String source = rs.getString("decision_source");
        String plan = rs.getString("plan_json");
        return new Problem(rs.getObject("id", UUID.class), rs.getObject("requester_id", UUID.class),
            rs.getObject("approver_id", UUID.class), Platform.valueOf(rs.getString("platform")),
            rs.getString("contents"), ProblemStatus.valueOf(rs.getString("status")),
            rs.getString("result_type") == null ? null : ResultType.valueOf(rs.getString("result_type")), rs.getString("diagnosis"),
            rs.getString("proposal"), rs.getObject("resource_id", UUID.class), role == null ? null : SaasRole.from(role),
            json.tree(rs.getString("evidence_json")), rs.getString("reason_code"), rs.getString("decision_reason"),
            source == null ? null : DecisionSource.valueOf(source), rs.getObject("decided_by", UUID.class),
            rs.getObject("decided_at", OffsetDateTime.class), rs.getString("thread_id"), rs.getString("idempotency_key"),
            plan == null ? null : json.plan(json.tree(plan)), rs.getString("plan_hash"), rs.getString("approved_plan_hash"),
            rs.getObject("verification_ok", Boolean.class), rs.getString("agent_mode") == null ? null : AgentMode.from(rs.getString("agent_mode")), rs.getBoolean("simulate_jira_failure"),
            rs.getObject("created_at", OffsetDateTime.class), rs.getObject("updated_at", OffsetDateTime.class),
            rs.getString("requester_name"), rs.getString("employee_no"));
    }
}
