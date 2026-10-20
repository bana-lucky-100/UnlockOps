package com.unlockops.auth.repository;

import com.unlockops.auth.dto.UserProfileResponse;
import com.unlockops.auth.model.*;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class UserRepository {
    private final JdbcTemplate jdbc;
    public UserRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public Optional<AppUser> findByLoginOrEmail(String login) {
        return jdbc.query("SELECT id,login_id,password_hash,role FROM users WHERE login_id=? OR email=?",
            (rs, n) -> new AppUser(rs.getObject("id", UUID.class), rs.getString("login_id"),
                rs.getString("password_hash"), UserRole.valueOf(rs.getString("role"))), login, login)
            .stream().findFirst();
    }

    public UserProfileResponse profile(UUID id) {
        return jdbc.queryForObject("""
            SELECT u.id,u.login_id,u.employee_no,u.name,u.role,u.job_grade,u.job_family,d.name department
            FROM users u JOIN departments d ON d.id=u.department_id WHERE u.id=?
            """, (rs, n) -> new UserProfileResponse(rs.getObject("id", UUID.class), rs.getString("login_id"),
                rs.getString("employee_no"), rs.getString("name"), UserRole.valueOf(rs.getString("role")),
                JobGrade.from(rs.getString("job_grade")), JobFamily.valueOf(rs.getString("job_family")),
                rs.getString("department")), id);
    }

    public EmployeeProfile employee(UUID id) {
        return jdbc.queryForObject("""
            SELECT u.id,u.role,u.department_id,u.job_grade,u.job_family,d.head_id
            FROM users u JOIN departments d ON d.id=u.department_id WHERE u.id=?
            """, (rs, n) -> new EmployeeProfile(rs.getObject("id", UUID.class),
                UserRole.valueOf(rs.getString("role")), rs.getObject("department_id", UUID.class),
                JobGrade.from(rs.getString("job_grade")), JobFamily.valueOf(rs.getString("job_family")),
                rs.getObject("head_id", UUID.class)), id);
    }

    public UUID operationsUserId() {
        return jdbc.queryForObject("SELECT id FROM users WHERE login_id='song_ops'", UUID.class);
    }

    public List<UUID> findWithoutPassword() {
        return jdbc.query("SELECT id FROM users WHERE password_hash=''", (rs, n) -> rs.getObject("id", UUID.class));
    }

    public void setPassword(UUID id, String passwordHash) {
        jdbc.update("UPDATE users SET password_hash=? WHERE id=?", passwordHash, id);
    }
}
