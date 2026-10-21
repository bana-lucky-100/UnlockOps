package com.unlockops;

import com.unlockops.access.repository.AccessContextRepository;
import com.unlockops.grant.model.*;
import java.math.BigDecimal;
import java.sql.ResultSet;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class AccessContextRepositoryTest {
    private final JdbcTemplate jdbc = mock(JdbcTemplate.class);
    private final AccessContextRepository repository = new AccessContextRepository(jdbc);
    private final UUID employee = UUID.randomUUID(), id = UUID.randomUUID();

    private Resource resource(Platform platform, AccessScope scope) {
        return new Resource(id, platform, "example", scope, null, null, null, null);
    }

    @Test void githubUsesTeamMembershipAndChoosesWriteOverRead() throws Exception {
        ResultSet read = mock(ResultSet.class), write = mock(ResultSet.class);
        when(read.getString("id")).thenReturn("read-team"); when(read.getString("saas_role")).thenReturn("Read");
        when(write.getString("id")).thenReturn("write-team"); when(write.getString("saas_role")).thenReturn("Write");
        doAnswer(call -> {
            RowMapper<?> mapper = call.getArgument(1);
            return List.of(mapper.mapRow(read, 0), mapper.mapRow(write, 1));
        }).when(jdbc).query(contains("github_team_members"), any(RowMapper.class), eq(employee), eq(id));
        var current = repository.current(employee, resource(Platform.GITHUB, AccessScope.GENERAL));
        assertEquals("Write", current.role());
        assertEquals(List.of("read-team", "write-team"), current.teams());
        assertEquals("github-team-membership", current.source());
        assertNull(current.canBrowse());
        verify(jdbc).query(contains("github_team_members"), any(RowMapper.class), eq(employee), eq(id));
        verifyNoMoreInteractions(jdbc);
    }

    @Test void jiraRoleWithoutBrowseSchemeIsNotReportedAsBrowsable() {
        doReturn(List.of("Developer")).when(jdbc).query(contains("FROM permissions"), any(RowMapper.class), eq(employee), eq(id));
        doReturn(List.of()).when(jdbc).query(contains("jira_role_permissions"), any(RowMapper.class), eq(id), eq("Developer"));
        var current = repository.current(employee, resource(Platform.JIRA, AccessScope.GENERAL));
        assertEquals("Developer", current.role());
        assertEquals(false, current.canBrowse());
        assertEquals("jira-role-and-scheme", current.source());
    }

    @Test void missingJiraRoleDoesNotLookupSchemeAndSeatDoesNotUseGithubTeams() {
        doReturn(List.of()).when(jdbc).query(contains("FROM permissions"), any(RowMapper.class), eq(employee), eq(id));
        assertEquals(false, repository.current(employee, resource(Platform.JIRA, AccessScope.GENERAL)).canBrowse());
        verify(jdbc, never()).query(contains("jira_role_permissions"), any(RowMapper.class), any(), any());
        var seat = repository.current(employee, resource(Platform.GITHUB, AccessScope.SEAT));
        assertNull(seat.role());
        assertEquals("mock-saas-permissions", seat.source());
        verify(jdbc, never()).query(contains("github_team_members"), any(RowMapper.class), any(), any());
    }

    @Test void budgetPreservesDecimalAmountsAndMissingRowStaysNull() throws Exception {
        ResultSet row = mock(ResultSet.class);
        when(row.getObject("department_id", UUID.class)).thenReturn(id);
        when(row.getBigDecimal("remaining_monthly_amount")).thenReturn(new BigDecimal("1234567890.12"));
        when(row.getBigDecimal("unit_monthly_price")).thenReturn(new BigDecimal("19.00"));
        when(row.getString("currency")).thenReturn("USD");
        when(row.getObject("updated_at", OffsetDateTime.class)).thenReturn(OffsetDateTime.parse("2026-10-21T00:00:00Z"));
        doAnswer(call -> List.of(((RowMapper<?>) call.getArgument(1)).mapRow(row, 0)))
            .when(jdbc).query(contains("department_budgets"), any(RowMapper.class), eq(id));
        var budget = repository.budget(id);
        assertEquals("1234567890.12", budget.remainingMonthlyAmount());
        assertEquals("19.00", budget.unitMonthlyPrice());
        doReturn(List.of()).when(jdbc).query(contains("department_budgets"), any(RowMapper.class), eq(id));
        assertNull(repository.budget(id));
    }
}
