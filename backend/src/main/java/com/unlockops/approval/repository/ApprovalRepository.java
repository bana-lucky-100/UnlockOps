package com.unlockops.approval.repository;

import com.unlockops.approval.dto.ApprovalSummaryResponse;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ApprovalRepository {
    private final JdbcTemplate jdbc;
    public ApprovalRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    /** Assignment and request creation time define the KST week; department is profile metadata. */
    public ApprovalSummaryResponse summary(UUID actor) {
        return jdbc.queryForObject("""
            WITH week AS (
                SELECT date_trunc('week',CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul') AS start_local
            )
            SELECT d.name department,
                   (SELECT count(*) FROM users member WHERE member.department_id=d.id) AS "memberCount",
                   count(p.id) AS "weekRequests",
                   count(p.id) FILTER (WHERE p.decision_source='HUMAN' AND p.approved_plan_hash IS NOT NULL
                       AND p.decided_by IS NOT NULL) AS approved,
                   count(p.id) FILTER (WHERE p.status='REJECTED') AS rejected,
                   count(p.id) FILTER (WHERE p.status='FAILED') AS failed
            FROM users actor JOIN departments d ON d.id=actor.department_id
            CROSS JOIN week
            LEFT JOIN problems p ON p.approver_id=actor.id
                AND p.created_at >= (week.start_local AT TIME ZONE 'Asia/Seoul')
                AND p.created_at < ((week.start_local + INTERVAL '7 days') AT TIME ZONE 'Asia/Seoul')
            WHERE actor.id=? GROUP BY d.id,d.name
            """, (rs, n) -> new ApprovalSummaryResponse(rs.getString("department"),
                rs.getLong("memberCount"), rs.getLong("weekRequests"), rs.getLong("approved"),
                rs.getLong("rejected"), rs.getLong("failed")), actor);
    }
}
