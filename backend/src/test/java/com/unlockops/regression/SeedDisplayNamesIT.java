package com.unlockops.regression;

import com.unlockops.auth.repository.UserRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.HexFormat;
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
        assertFalse(java.util.regex.Pattern.compile("Phase [12]").matcher(seed).find());
        jdbc.execute(seed);
        assertDefaultNames(jdbc);
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM policy_revisions WHERE content ~ 'Phase [12]'", Integer.class));
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM reclaim_snapshots WHERE context::text ~ 'Phase [12]'", Integer.class));
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM reclaim_snapshot_items WHERE facts::text ~ 'Phase [12]'", Integer.class));

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

    @Test void missingHistoricalReportUsesInstalledPolicyWithoutRewritingIt() throws Exception {
        var source = new DriverManagerDataSource(DB.getJdbcUrl(), DB.getUsername(), DB.getPassword());
        new JdbcTemplate(source).execute("CREATE SCHEMA old_seed");
        source.setSchema("old_seed");
        var jdbc = new JdbcTemplate(source);
        Flyway.configure().dataSource(source).schemas("old_seed").load().migrate();
        var json = new ObjectMapper();
        String content = Files.readString(Path.of("../data/phase2/company-a-policy.md"))
            .replace("# A사 임시 규정", "# A사 Phase 2 임시 규정");
        String hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content.getBytes(StandardCharsets.UTF_8)));
        // An existing installation can contain the old immutable policy but no R-04 report yet.
        jdbc.update("INSERT INTO companies(id,code,name) VALUES('26c56ede-d5bd-5fad-8591-d729af9eaee9','P2_A','Phase 2 A사 (mock)')");
        jdbc.update("""
            INSERT INTO policy_revisions(policy_id,revision,company_id,doc_id,article,source_path,source_hash,content,is_mock)
            VALUES('0673ccd9-4e9b-5e92-bb81-28b949ef5224',1,'26c56ede-d5bd-5fad-8591-d729af9eaee9',
                'P2-A-POLICY','POL-06 제1~5조 / FLOW 제7조','data/phase2/company-a-policy.md',?,?,true)
            """, hash, content);
        String seed = Files.readString(Path.of("../data/phase2/seed.sql"));
        jdbc.execute(seed);
        assertEquals(content, jdbc.queryForObject("SELECT content FROM policy_revisions WHERE doc_id='P2-A-POLICY'", String.class));
        var context = json.readTree(jdbc.queryForObject("SELECT context::text FROM reclaim_snapshots", String.class));
        assertEquals(content, context.path("policy").path("content").asText());
        assertEquals(hash, context.path("policy_hash").asText());
        assertEquals(hash, context.path("policy").path("source_hash").asText());
        var facts = json.readTree(jdbc.queryForObject("SELECT facts::text FROM reclaim_snapshot_items", String.class));
        assertEquals(hash, facts.path("candidate").path("policy_evidence").get(0).path("source_hash").asText());
        var report = json.readTree(jdbc.queryForObject("SELECT report::text FROM reclaim_run_items", String.class));
        assertEquals(hash, report.path("policy_evidence").get(0).path("source_hash").asText());
        var evidence = json.readTree(jdbc.queryForObject("SELECT policy_evidence::text FROM reclaim_run_items", String.class));
        assertEquals(hash, evidence.get(0).path("source_hash").asText());
        // Both the old baseline and the renamed baseline must accept the same later revisions.
        for (String file : List.of("apply.sql", "apply-v4.sql", "apply-costs.sql"))
            jdbc.execute(Files.readString(Path.of("../data/phase2/policies", file)));
        assertEquals(content, jdbc.queryForObject("SELECT content FROM policy_revisions WHERE doc_id='P2-A-POLICY' AND revision=1", String.class));
        assertEquals(8, jdbc.queryForObject("SELECT count(*) FROM policy_revisions WHERE doc_id IN ('P2-A-POLICY','P2-B-POLICY')", Integer.class));
        var installed = state(jdbc);
        jdbc.execute(seed);
        assertEquals(installed, state(jdbc));
    }
}
