package com.unlockops.regression;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.unlockops.access.repository.AccessContextRepository;
import com.unlockops.access.service.AccessCeilingPolicy;
import com.unlockops.access.service.AccessVerificationService;
import com.unlockops.access.dto.AccessVerificationRequests.Verify;
import com.unlockops.common.json.Jsons;
import com.unlockops.grant.model.*;
import com.unlockops.grant.repository.*;
import com.unlockops.grant.service.*;
import com.unlockops.problem.repository.ProblemRepository;
import java.math.BigDecimal;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.*;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/** 독립 PostgreSQL에서 서비스 프록시의 실제 트랜잭션·잠금·영수증을 검증한다. */
@JdbcTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Import({GrantExecutionIT.JsonConfiguration.class, Jsons.class, ProblemRepository.class, GrantRepository.class,
    GrantExecutionRepository.class, AccessContextRepository.class, AccessCeilingPolicy.class,
    GrantExecutionPolicy.class, GrantExecutionService.class, AccessVerificationService.class})
@Transactional(propagation = Propagation.NOT_SUPPORTED)
@Testcontainers
class GrantExecutionIT {
    @Container static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:16-alpine");
    @DynamicPropertySource static void database(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }
    @TestConfiguration static class JsonConfiguration {
        @Bean ObjectMapper objectMapper() { return new ObjectMapper().findAndRegisterModules(); }
    }

    @Autowired JdbcTemplate jdbc;
    @Autowired GrantExecutionService service;
    @Autowired AccessVerificationService verification;
    @Autowired AccessContextRepository facts;
    @Autowired GrantRepository grants;
    @Autowired AccessCeilingPolicy source;
    @Autowired Jsons json;
    @Autowired ObjectMapper mapper;
    @MockitoSpyBean GrantExecutionRepository executions;
    UUID employee, approver, seat, department;

    @BeforeEach void reset() {
        jdbc.execute("TRUNCATE grant_receipts,problem_events,outbox,inbox_events,problems RESTART IDENTITY");
        employee = user("kim_dev"); approver = user("yoon_head");
        seat = jdbc.queryForObject("SELECT id FROM resources WHERE external_id='copilot-seat'", UUID.class);
        department = facts.profile(employee).departmentId();
        jdbc.update("DELETE FROM permissions WHERE resource_id=?", seat);
        jdbc.update("UPDATE department_budgets SET remaining_monthly_amount=19.00,unit_monthly_price=19.00 WHERE department_id=?", department);
    }

    private UUID user(String login) {
        return jdbc.queryForObject("SELECT id FROM users WHERE login_id=?", UUID.class, login);
    }

    private UUID approved(UUID requester) {
        UUID id = UUID.randomUUID();
        var plan = new GrantPlan(id, requester, Platform.GITHUB, seat, "copilot-seat", SaasRole.SEAT);
        var rules = source.executionRules(facts.profile(requester), grants.resource(seat));
        var evidence = mapper.createArrayNode();
        for (String doc : List.of("A-ACCESS-03", "A-ACCESS-04", "A-ACCESS-07", "POL-03", "POL-06")) {
            String filename = doc.startsWith("A-") ? "company-a-access-matrix.md" : "policy_corpus.md";
            evidence.addObject().put("doc_id", doc).put("source", filename).put("source_hash", rules.sourceHashes().get(filename))
                .put("chunk_id", doc + ":fixture").put("text", "규정 근거");
        }
        String hash = json.planHash(plan);
        jdbc.update("""
            INSERT INTO problems(id,requester_id,approver_id,platform,contents,status,resource_id,requested_role,
                evidence,decision_source,decided_by,decided_at,thread_id,idempotency_key,plan,plan_hash,approved_plan_hash)
            VALUES (?,?,?,'GITHUB','좌석 신청','EXECUTING',?,'Seat',?::jsonb,'HUMAN',?,NOW(),?,?,?::jsonb,?,?)
            """, id, requester, approver, seat, json.write(evidence), approver, id.toString(), id.toString(), json.write(plan), hash, hash);
        return id;
    }

    private BigDecimal balance() {
        return jdbc.queryForObject("SELECT remaining_monthly_amount FROM department_budgets WHERE department_id=?", BigDecimal.class, department);
    }
    private int seats() {
        return jdbc.queryForObject("SELECT count(*) FROM permissions WHERE resource_id=?", Integer.class, seat);
    }

    @Test void concurrentDuplicateDeliveryReturnsOneReceiptAndDebitsOnce() throws Exception {
        UUID id = approved(employee);
        try (var pool = Executors.newFixedThreadPool(4)) {
            var calls = new ArrayList<Callable<Boolean>>();
            for (int i = 0; i < 4; i++) calls.add(() -> service.execute(id, id.toString()).changed());
            for (var future : pool.invokeAll(calls)) assertTrue(future.get(15, TimeUnit.SECONDS));
        }
        assertEquals(0, balance().compareTo(BigDecimal.ZERO));
        assertEquals(1, seats());
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM grant_receipts", Integer.class));
    }

    @Test void twoRequestsForSameEmployeeCannotCreateTwoSeats() throws Exception {
        UUID first = approved(employee), second = approved(employee);
        assertEquals(List.of(true, false), concurrent(first, second).stream().sorted(Comparator.reverseOrder()).toList());
        assertEquals(1, seats());
        assertEquals(0, balance().compareTo(BigDecimal.ZERO));
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM grant_receipts", Integer.class));
    }

    @Test void employeesCompetingForOneSeatBudgetCannotOverspend() throws Exception {
        UUID first = approved(employee), second = approved(user("oh_dev"));
        assertEquals(1, concurrent(first, second).stream().filter(Boolean::booleanValue).count());
        assertEquals(0, balance().compareTo(BigDecimal.ZERO));
        assertEquals(1, seats());
    }

    private List<Boolean> concurrent(UUID first, UUID second) throws Exception {
        try (var pool = Executors.newFixedThreadPool(2)) {
            List<Callable<Boolean>> calls = List.of(() -> executeOrReject(first), () -> executeOrReject(second));
            var results = new ArrayList<Boolean>();
            for (var future : pool.invokeAll(calls)) results.add(future.get(15, TimeUnit.SECONDS));
            return results;
        }
    }
    private boolean executeOrReject(UUID id) {
        try { return service.execute(id, id.toString()).changed(); }
        catch (GrantExecutionException e) { assertEquals("PRECONDITION_CHANGED", e.code()); return false; }
    }

    @Test void receiptFailureRollsBackPermissionAndBudgetAndCanBeRetried() {
        UUID id = approved(employee);
        doThrow(new org.springframework.dao.DataAccessResourceFailureException("receipt outage"))
            .when(executions).saveReceipt(eq(id), anyString(), any());
        assertThrows(org.springframework.dao.DataAccessException.class, () -> service.execute(id, id.toString()));
        assertEquals(0, balance().compareTo(new BigDecimal("19.00")));
        assertEquals(0, seats());
        assertEquals(0, jdbc.queryForObject("SELECT count(*) FROM grant_receipts", Integer.class));
        doCallRealMethod().when(executions).saveReceipt(eq(id), anyString(), any());
        assertTrue(service.execute(id, id.toString()).changed());
    }

    @Test void verificationRereadsCommittedPermissionEvenWhenAReceiptStillExists() {
        UUID id = approved(employee);
        var request = new Verify(employee, seat, Platform.GITHUB, "Seat");
        assertFalse(verification.verify(request).verified());
        service.execute(id, id.toString());
        assertTrue(verification.verify(request).verified());
        jdbc.update("DELETE FROM permissions WHERE user_id=? AND resource_id=?", employee, seat);
        assertFalse(verification.verify(request).verified());
        assertEquals(1, jdbc.queryForObject("SELECT count(*) FROM grant_receipts WHERE problem_id=?", Integer.class, id));
    }
}
