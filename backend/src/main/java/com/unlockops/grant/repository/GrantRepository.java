package com.unlockops.grant.repository;

import com.unlockops.grant.model.*;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class GrantRepository {
    private final JdbcTemplate jdbc;
    public GrantRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public Resource resource(UUID id) {
        return jdbc.queryForObject("SELECT * FROM resources WHERE id=?", (rs, n) -> new Resource(
            rs.getObject("id", UUID.class), Platform.valueOf(rs.getString("platform")), rs.getString("external_id"),
            AccessScope.valueOf(rs.getString("access_scope")), rs.getObject("owner_department_id", UUID.class),
            rs.getObject("tf_id", UUID.class), rs.getString("security_grade") == null ? null :
                SecurityGrade.valueOf(rs.getString("security_grade")), rs.getObject("designated_department_id", UUID.class)), id);
    }

    public UUID tfLeader(UUID tfId) {
        return jdbc.queryForObject("SELECT leader_id FROM tfs WHERE id=?", UUID.class, tfId);
    }

    public boolean activeTfMember(UUID requester, UUID tfId) {
        Integer count = jdbc.queryForObject("""
            SELECT count(*) FROM tf_members m JOIN tfs t ON t.id=m.tf_id
            WHERE m.user_id=? AND m.tf_id=? AND m.active AND t.starts_on<=CURRENT_DATE
            AND (t.ends_on IS NULL OR t.ends_on>=CURRENT_DATE)
            """, Integer.class, requester, tfId);
        return count != null && count == 1;
    }

    public boolean canBrowseJira(UUID resourceId, SaasRole role) {
        return Boolean.TRUE.equals(jdbc.queryForObject(
            "SELECT can_browse FROM jira_role_permissions WHERE resource_id=? AND saas_role=?",
            Boolean.class, resourceId, role.value()));
    }

    public DepartmentBudget budget(UUID departmentId) {
        return jdbc.queryForObject("SELECT * FROM department_budgets WHERE department_id=?", (rs, n) ->
            new DepartmentBudget(rs.getBigDecimal("remaining_monthly_amount"), rs.getBigDecimal("unit_monthly_price")), departmentId);
    }

    public boolean hasSeat(UUID requester, UUID resourceId) {
        Integer count = jdbc.queryForObject("SELECT count(*) FROM permissions WHERE user_id=? AND resource_id=?",
            Integer.class, requester, resourceId);
        return count == null || count != 0;
    }

    public boolean hasReceipt(UUID problemId, String key) {
        Integer count = jdbc.queryForObject("SELECT count(*) FROM grant_receipts WHERE problem_id=? AND idempotency_key=?",
            Integer.class, problemId, key);
        return count != null && count == 1;
    }
}
