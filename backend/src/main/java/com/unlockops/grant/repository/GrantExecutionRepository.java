package com.unlockops.grant.repository;

import com.unlockops.access.dto.AccessContextResponses.Budget;
import com.unlockops.auth.model.*;
import com.unlockops.common.json.Jsons;
import com.unlockops.grant.dto.GrantExecutionResponses.Success;
import com.unlockops.grant.model.GrantPlan;
import com.unlockops.grant.service.GrantExecutionException;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class GrantExecutionRepository {
    private final JdbcTemplate jdbc;
    private final Jsons json;
    public GrantExecutionRepository(JdbcTemplate jdbc, Jsons json) { this.jdbc = jdbc; this.json = json; }

    public Optional<Success> receipt(UUID problemId, String key) {
        return jdbc.query("SELECT result::text FROM grant_receipts WHERE problem_id=? AND idempotency_key=?",
            (rs, n) -> json.read(json.tree(rs.getString(1)), Success.class), problemId, key).stream().findFirst();
    }

    public void lockEmployeeResource(GrantPlan plan) {
        // Python MCP와 같은 키·해시를 사용하므로 전환 기간의 동시 실행도 직렬화한다.
        jdbc.query("SELECT pg_advisory_xact_lock(hashtextextended(?,0))", rs -> {},
            plan.requesterId() + ":" + plan.resourceId());
    }

    public Optional<Approver> approver(UUID employeeId) {
        return jdbc.query("SELECT id,role,job_grade FROM users WHERE id=?", (rs, n) ->
            new Approver(rs.getObject("id", UUID.class), UserRole.valueOf(rs.getString("role")),
                JobGrade.from(rs.getString("job_grade"))), employeeId).stream().findFirst();
    }

    public Optional<Budget> lockBudget(UUID departmentId) {
        return jdbc.query("SELECT * FROM department_budgets WHERE department_id=? FOR UPDATE", (rs, n) ->
            new Budget(rs.getObject("department_id", UUID.class), rs.getBigDecimal("remaining_monthly_amount").toPlainString(),
                rs.getBigDecimal("unit_monthly_price").toPlainString(), rs.getString("currency"),
                rs.getObject("updated_at", java.time.OffsetDateTime.class)), departmentId).stream().findFirst();
    }

    public boolean canBrowse(UUID resourceId, String role) {
        return jdbc.query("SELECT can_browse FROM jira_role_permissions WHERE resource_id=? AND saas_role=?",
            (rs, n) -> rs.getBoolean("can_browse"), resourceId, role).stream().anyMatch(Boolean.TRUE::equals);
    }

    public void debitBudget(UUID departmentId) {
        int changed = jdbc.update("""
            UPDATE department_budgets SET remaining_monthly_amount=remaining_monthly_amount-unit_monthly_price,
                updated_at=NOW() WHERE department_id=? AND remaining_monthly_amount>=unit_monthly_price
            """, departmentId);
        if (changed != 1) throw GrantExecutionException.precondition("BUDGET_INSUFFICIENT");
    }

    public void joinGithubTeam(GrantPlan plan) {
        var teams = jdbc.query("SELECT id FROM github_teams WHERE resource_id=? AND saas_role=?",
            (rs, n) -> rs.getString("id"), plan.resourceId(), plan.requestedRole().value());
        if (teams.size() != 1) throw GrantExecutionException.precondition("GITHUB_TEAM_UNAVAILABLE");
        jdbc.update("INSERT INTO github_team_members(team_id,user_id) VALUES (?,?) ON CONFLICT DO NOTHING",
            teams.getFirst(), plan.requesterId());
    }

    public void grant(GrantPlan plan) {
        jdbc.update("""
            INSERT INTO permissions(user_id,resource_id,saas_role) VALUES (?,?,?)
            ON CONFLICT(user_id,resource_id) DO UPDATE SET saas_role=excluded.saas_role,granted_at=NOW()
            """, plan.requesterId(), plan.resourceId(), plan.requestedRole().value());
    }

    public void saveReceipt(UUID problemId, String key, Success result) {
        jdbc.update("INSERT INTO grant_receipts(idempotency_key,problem_id,result) VALUES (?,?,?::jsonb)",
            key, problemId, json.write(result));
    }

    public record Approver(UUID id, UserRole role, JobGrade grade) {}
}
