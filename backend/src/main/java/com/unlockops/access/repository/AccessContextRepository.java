package com.unlockops.access.repository;

import com.unlockops.access.dto.AccessContextResponses.*;
import com.unlockops.auth.model.*;
import com.unlockops.grant.model.*;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AccessContextRepository {
    private final JdbcTemplate jdbc;
    public AccessContextRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public Profile profile(UUID employeeId) {
        return jdbc.queryForObject("""
            SELECT u.id,u.employee_no,u.name,u.department_id,u.job_grade,u.job_family,
                   d.name department_name,d.head_id
            FROM users u JOIN departments d ON d.id=u.department_id WHERE u.id=?
            """, (rs, n) -> new Profile(rs.getObject("id", UUID.class), rs.getString("employee_no"),
                rs.getString("name"), rs.getObject("department_id", UUID.class), rs.getString("department_name"),
                JobGrade.from(rs.getString("job_grade")), JobFamily.valueOf(rs.getString("job_family")),
                rs.getObject("head_id", UUID.class)), employeeId);
    }

    public Membership membership(UUID employeeId, UUID resourceId) {
        return jdbc.queryForObject("""
            SELECT r.tf_id,t.leader_id,
                   COALESCE(m.active,FALSE) AND t.starts_on<=CURRENT_DATE
                   AND (t.ends_on IS NULL OR t.ends_on>=CURRENT_DATE) AS member
            FROM resources r LEFT JOIN tfs t ON t.id=r.tf_id
            LEFT JOIN tf_members m ON m.tf_id=t.id AND m.user_id=? WHERE r.id=?
            """, (rs, n) -> new Membership(rs.getObject("tf_id", UUID.class), rs.getBoolean("member"),
                rs.getObject("leader_id", UUID.class)), employeeId, resourceId);
    }

    public Current current(UUID employeeId, Resource resource) {
        if (resource.platform() == Platform.GITHUB && resource.accessScope() != AccessScope.SEAT) {
            List<Team> teams = jdbc.query("""
                SELECT t.id,t.saas_role FROM github_team_members m JOIN github_teams t ON t.id=m.team_id
                WHERE m.user_id=? AND t.resource_id=? ORDER BY t.id
                """, (rs, n) -> new Team(rs.getString("id"), rs.getString("saas_role")), employeeId, resource.id());
            String role = teams.stream().anyMatch(team -> "Write".equals(team.role())) ? "Write" :
                teams.stream().anyMatch(team -> "Read".equals(team.role())) ? "Read" : null;
            return new Current(role, "github-team-membership", teams.stream().map(Team::id).toList(), null);
        }
        List<String> roles = jdbc.query("SELECT saas_role FROM permissions WHERE user_id=? AND resource_id=?",
            (rs, n) -> rs.getString("saas_role"), employeeId, resource.id());
        String role = roles.isEmpty() ? null : roles.getFirst();
        if (resource.platform() == Platform.JIRA) {
            List<Boolean> permissions = role == null ? List.of() : jdbc.query("""
                SELECT can_browse FROM jira_role_permissions WHERE resource_id=? AND saas_role=?
                """, (rs, n) -> rs.getBoolean("can_browse"), resource.id(), role);
            return new Current(role, "jira-role-and-scheme", null,
                !permissions.isEmpty() && Boolean.TRUE.equals(permissions.getFirst()));
        }
        return new Current(role, "mock-saas-permissions", null, null);
    }

    public Budget budget(UUID departmentId) {
        List<Budget> rows = jdbc.query("SELECT * FROM department_budgets WHERE department_id=?", (rs, n) ->
            new Budget(rs.getObject("department_id", UUID.class), rs.getBigDecimal("remaining_monthly_amount").toPlainString(),
                rs.getBigDecimal("unit_monthly_price").toPlainString(), rs.getString("currency"),
                rs.getObject("updated_at", java.time.OffsetDateTime.class)), departmentId);
        return rows.isEmpty() ? null : rows.getFirst();
    }

    private record Team(String id, String role) {}
}
