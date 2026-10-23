package com.unlockops.regression;

import java.sql.DriverManager;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import static org.junit.jupiter.api.Assertions.*;

/** Upgrade an actual V4 database, including successful and empty legacy guidance. */
@Testcontainers
class CompletionMigrationIT {
    @Container static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:16-alpine");

    @Test void upgradePreservesHistoryAndEnforcesCompletionMeaning() throws Exception {
        Flyway.configure().dataSource(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword())
            .target("4").load().migrate();
        try (var connection = DriverManager.getConnection(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
             var sql = connection.createStatement()) {
            sql.executeUpdate("""
                INSERT INTO problems(id,requester_id,platform,contents,status,reason_code,proposal,thread_id,verification_ok)
                VALUES
                ('40000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001',
                 'GITHUB','guide','MANUAL_REVIEW','RAG_GUIDANCE','점검 안내','migration-guide',NULL),
                ('40000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000001',
                 'GITHUB','empty','MANUAL_REVIEW','RAG_GUIDANCE','  ','migration-empty',NULL),
                ('40000000-0000-0000-0000-000000000003','10000000-0000-0000-0000-000000000001',
                 'GITHUB','grant','DONE','VERIFIED','반영 완료','migration-grant',true)
                """);
            sql.executeUpdate("""
                INSERT INTO problem_events(event_id,problem_id,kind,payload)
                VALUES ('50000000-0000-0000-0000-000000000001','40000000-0000-0000-0000-000000000001',
                    'ANALYZED','{"result":{"status":"MANUAL_REVIEW","reasonCode":"RAG_GUIDANCE","proposal":"점검 안내"}}')
                """);
            Flyway.configure().dataSource(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword()).load().migrate();
            try (var rows = sql.executeQuery("SELECT status,result_type FROM problems ORDER BY id")) {
                assertTrue(rows.next()); assertEquals("DONE", rows.getString(1)); assertEquals("GUIDANCE", rows.getString(2));
                assertTrue(rows.next()); assertEquals("MANUAL_REVIEW", rows.getString(1)); assertNull(rows.getString(2));
                assertTrue(rows.next()); assertEquals("DONE", rows.getString(1)); assertEquals("ACCESS_VERIFIED", rows.getString(2));
            }
            try (var audit = sql.executeQuery("SELECT payload->'result'->>'status' FROM problem_events")) {
                assertTrue(audit.next()); assertEquals("MANUAL_REVIEW", audit.getString(1));
            }
            assertThrows(java.sql.SQLException.class, () -> sql.executeUpdate(
                "UPDATE problems SET verification_ok=true WHERE result_type='GUIDANCE'"));
            assertThrows(java.sql.SQLException.class, () -> sql.executeUpdate(
                "UPDATE problems SET verification_ok=false WHERE result_type='ACCESS_VERIFIED'"));
        }
    }
}
