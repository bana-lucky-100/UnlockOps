package com.unlockops.regression;

import com.unlockops.auth.repository.UserRepository;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

/** Current display names can change without rewriting historical evidence or demo state. */
@Testcontainers
class SeedDisplayNamesIT {
    @Container static final PostgreSQLContainer<?> DB = new PostgreSQLContainer<>("postgres:16-alpine");

    private static final List<String> NAMED_TABLES = List.of("companies", "departments", "tfs", "resources");
    private static final List<String> STATE_TABLES = List.of(
        "users", "department_budgets", "access_assignments", "permissions", "policy_revisions",
        "pricing_revisions", "reclaim_snapshots", "reclaim_snapshot_items", "reclaim_run_items",
        "reclaim_targets", "reclaim_notifications");

    private Map<String, String> state(JdbcTemplate jdbc) {
        var result = new LinkedHashMap<String, String>();
        for (String table : STATE_TABLES) result.put(table, rows(jdbc, table, false));
        for (String table : NAMED_TABLES) result.put(table, rows(jdbc, table, true));
        return result;
    }

    private String rows(JdbcTemplate jdbc, String table, boolean omitName) {
        String row = "to_jsonb(t)" + (omitName ? " - 'name'" : "");
        return jdbc.queryForObject("SELECT COALESCE(jsonb_agg(" + row + " ORDER BY " + row
            + "),'[]'::jsonb)::text FROM " + table + " t", String.class);
    }

    private void assertDefaultNames(JdbcTemplate jdbc) {
        for (String company : List.of("A", "B")) {
            String code = "P2_" + company;
            assertEquals(company + "사 (mock)", jdbc.queryForObject(
                "SELECT name FROM companies WHERE code=?", String.class, code));
            assertEquals(company + "사 업무팀", jdbc.queryForObject(
                "SELECT name FROM departments WHERE code=?", String.class, code + "_DEV"));
            for (String status : List.of("ACTIVE", "ENDED")) assertEquals(company + "사 " + status + " TF",
                jdbc.queryForObject("SELECT name FROM tfs WHERE code=?", String.class, code + "_" + status));
            assertEquals(10, jdbc.queryForObject("""
                SELECT count(*) FROM resources r JOIN companies c ON c.id=r.company_id
                WHERE c.code=? AND r.name=? || ' ' || r.platform
                """, Integer.class, code, company));
            assertEquals(company + " payment repository", jdbc.queryForObject(
                "SELECT name FROM resources WHERE external_id=?", String.class,
                "p2-" + company.toLowerCase() + "-payment-repo"));
        }
        var users = new UserRepository(jdbc);
        UUID requester = jdbc.queryForObject("SELECT id FROM users WHERE login_id='p2_a_requester'", UUID.class);
        assertEquals("A사 업무팀", users.profile(requester).department());
    }

    @Test void freshSeedAndReapplicationRenameOnlyOriginalLabelsAndPreserveState() throws Exception {
        var source = new DriverManagerDataSource(DB.getJdbcUrl(), DB.getUsername(), DB.getPassword());
        var jdbc = new JdbcTemplate(source);
        Flyway.configure().dataSource(source).load().migrate();
        String seed = Files.readString(Path.of("../data/phase2/seed.sql"));
        jdbc.execute(seed);
        assertDefaultNames(jdbc);

        // Simulate an installed demo with the old labels and subsequent human activity.
        for (String table : NAMED_TABLES) jdbc.update("UPDATE " + table
            + " SET name='Phase 2 ' || name WHERE name ~ '^[AB](사| )'");
        jdbc.update("UPDATE companies SET name='고객사 이름' WHERE code='P2_B'");
        jdbc.update("UPDATE departments SET name='고객사 업무팀' WHERE code='P2_B_DEV'");
        jdbc.update("UPDATE tfs SET name='고객사 TF' WHERE code='P2_B_ACTIVE'");
        jdbc.update("UPDATE resources SET name='Phase 1 사용자 지정 자원' WHERE external_id='p2-b-snowflake'");
        jdbc.update("UPDATE department_budgets SET remaining_monthly_amount=123.45 WHERE department_id=(SELECT id FROM departments WHERE code='P2_A_DEV')");
        jdbc.update("UPDATE access_assignments SET status='INACTIVE',ended_at=now() WHERE id=(SELECT id FROM access_assignments ORDER BY id LIMIT 1)");
        jdbc.update("UPDATE reclaim_notifications SET read_at=delivered_at");
        Map<String, String> before = state(jdbc);
        String legacyNames = jdbc.queryForObject("""
            SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id)::text FROM resources r
            WHERE company_id='00000000-0000-0000-0000-000000000000'
            """, String.class);

        jdbc.execute(seed);
        assertEquals("A사 (mock)", jdbc.queryForObject("SELECT name FROM companies WHERE code='P2_A'", String.class));
        assertEquals("A사 업무팀", jdbc.queryForObject("SELECT name FROM departments WHERE code='P2_A_DEV'", String.class));
        assertEquals("A사 ACTIVE TF", jdbc.queryForObject("SELECT name FROM tfs WHERE code='P2_A_ACTIVE'", String.class));
        assertEquals("A GITHUB", jdbc.queryForObject("SELECT name FROM resources WHERE external_id='p2-a-github'", String.class));
        assertEquals("B payment repository", jdbc.queryForObject("SELECT name FROM resources WHERE external_id='p2-b-payment-repo'", String.class));
        assertEquals("고객사 이름", jdbc.queryForObject("SELECT name FROM companies WHERE code='P2_B'", String.class));
        assertEquals("고객사 업무팀", jdbc.queryForObject("SELECT name FROM departments WHERE code='P2_B_DEV'", String.class));
        assertEquals("고객사 TF", jdbc.queryForObject("SELECT name FROM tfs WHERE code='P2_B_ACTIVE'", String.class));
        assertEquals("Phase 1 사용자 지정 자원", jdbc.queryForObject("SELECT name FROM resources WHERE external_id='p2-b-snowflake'", String.class));
        assertEquals(before, state(jdbc));
        assertEquals(legacyNames, jdbc.queryForObject("""
            SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id)::text FROM resources r
            WHERE company_id='00000000-0000-0000-0000-000000000000'
            """, String.class));
        String names = "SELECT name FROM companies UNION ALL SELECT name FROM departments UNION ALL SELECT name FROM tfs UNION ALL SELECT name FROM resources ORDER BY name";
        var after = jdbc.queryForList(names);
        jdbc.execute(seed);
        assertEquals(after, jdbc.queryForList(names));
        assertEquals(before, state(jdbc));
    }
}
