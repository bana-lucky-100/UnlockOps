package com.unlockops.regression;

import java.sql.*;
import java.nio.file.*;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import static org.junit.jupiter.api.Assertions.*;

/** Real PostgreSQL: upgrade legacy data, seed twice, verify constraints and isolation. */
@Testcontainers
class Phase2FoundationIT {
    @Container static final PostgreSQLContainer<?> DB=new PostgreSQLContainer<>("postgres:16-alpine");
    private long number(Statement sql,String query) throws Exception {
        try(var rs=sql.executeQuery(query)) { assertTrue(rs.next());return rs.getLong(1); }
    }
    private void rejected(Statement sql,String command) {
        assertThrows(SQLException.class,()->sql.executeUpdate(command));
    }
    @Test void upgradeAndOptInSeedPreserveLegacyAndEnforceV2() throws Exception {
        Flyway.configure().dataSource(DB.getJdbcUrl(),DB.getUsername(),DB.getPassword()).target("5").load().migrate();
        try(var connection=DriverManager.getConnection(DB.getJdbcUrl(),DB.getUsername(),DB.getPassword());var sql=connection.createStatement()) {
            long permissions=number(sql,"SELECT count(*) FROM permissions");
            long members=number(sql,"SELECT count(*) FROM github_team_members");
            Flyway.configure().dataSource(DB.getJdbcUrl(),DB.getUsername(),DB.getPassword()).load().migrate();
            assertEquals(permissions,number(sql,"SELECT count(*) FROM permissions"));
            assertEquals(members,number(sql,"SELECT count(*) FROM github_team_members"));
            assertEquals(0,number(sql,"SELECT count(*) FROM access_assignments"));
            String seed=Files.readString(Path.of("../data/phase2/seed.sql"));
            sql.execute(seed); sql.execute(seed);
            assertEquals(permissions,number(sql,"SELECT count(*) FROM permissions"));
            assertEquals(10,number(sql,"SELECT count(DISTINCT platform) FROM resources WHERE company_id<>'00000000-0000-0000-0000-000000000000'"));
            assertEquals(8,number(sql,"SELECT count(*) FROM access_assignments"));
            assertEquals(1,number(sql,"SELECT count(*) FROM reclaim_notifications WHERE delivery_status='DELIVERED'"));
            assertEquals(0,number(sql,"SELECT count(*) FROM reclaim_scopes WHERE enabled"));
            rejected(sql,"UPDATE pricing_revisions SET monthly_amount=999");
            rejected(sql,"UPDATE entitlement_revisions SET external_role='ADMIN'");
            rejected(sql,"UPDATE access_assignments SET company_id=(SELECT id FROM companies WHERE code='P2_B')");
            rejected(sql,"UPDATE access_assignments SET resource_id=(SELECT id FROM resources WHERE external_id='p2-a-snowflake')");
            rejected(sql,"UPDATE reclaim_notifications SET read_at=now(),delivered_at=NULL");
            rejected(sql,"UPDATE reclaim_targets SET candidate_status='RECLAIMED'");
            rejected(sql,"INSERT INTO access_assignments SELECT gen_random_uuid(),company_id,user_id,resource_id,entitlement_id,entitlement_revision,status,origin_tf_id,granted_at,ended_at,source_problem_id FROM access_assignments LIMIT 1");
            sql.executeUpdate("""
                INSERT INTO reclaim_runs(id,company_id,scope_id,trigger,scheduled_for,schedule_date,request_hash,status,message)
                SELECT '90000000-0000-0000-0000-000000000001',company_id,id,'DAILY_SCHEDULE',
                    '2026-10-22T09:00:00+09:00','2026-10-22',repeat('a',64),'RECEIVED','test'
                FROM reclaim_scopes LIMIT 1
                """);
            rejected(sql,"UPDATE reclaim_runs SET status='DONE',reason_code='NO_NEW_CANDIDATES'");
            rejected(sql,"UPDATE reclaim_runs SET status='WAITING_APPROVAL'");
            rejected(sql,"INSERT INTO reclaim_runs(id,company_id,scope_id,task_type,contract_version,trigger,scheduled_for,schedule_date,requested_by,client_request_key,request_hash,status,reason_code,message,snapshot_id,as_of,scan_complete,needs_review_count,new_candidate_count,pending_notification_count,created_at,updated_at) SELECT '90000000-0000-0000-0000-000000000002',company_id,scope_id,task_type,contract_version,trigger,scheduled_for,schedule_date,requested_by,client_request_key,request_hash,status,reason_code,message,snapshot_id,as_of,scan_complete,needs_review_count,new_candidate_count,pending_notification_count,created_at,updated_at FROM reclaim_runs");
        }
    }
}
