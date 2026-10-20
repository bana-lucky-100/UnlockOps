package com.unlockops;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.*;

@RestController
public class AuthController {
    private final AuthenticationManager manager;
    private final HttpSessionSecurityContextRepository repository;
    private final JdbcTemplate jdbc;
    AuthController(AuthenticationManager manager, HttpSessionSecurityContextRepository repository, JdbcTemplate jdbc) {
        this.manager=manager; this.repository=repository; this.jdbc=jdbc;
    }
    record Login(@NotBlank @Size(max=255) String loginId, @NotBlank @Size(max=200) String password) {}

    @GetMapping("/api/health") Map<String,Object> health() { return Map.of("status","UP"); }
    @GetMapping("/api/auth/csrf") Map<String,String> csrf(CsrfToken token) {
        return Map.of("token",token.getToken(),"headerName",token.getHeaderName());
    }
    @PostMapping("/api/auth/login") Map<String,Object> login(@RequestBody @Valid Login body,
            HttpServletRequest request, HttpServletResponse response) {
        var auth=manager.authenticate(UsernamePasswordAuthenticationToken.unauthenticated(body.loginId(),body.password()));
        request.getSession(true);
        request.changeSessionId();
        var context=SecurityContextHolder.createEmptyContext();
        context.setAuthentication(auth);
        SecurityContextHolder.setContext(context);
        repository.saveContext(context,request,response);
        return me((AppUser) auth.getPrincipal());
    }
    @GetMapping("/api/auth/me") Map<String,Object> me(@AuthenticationPrincipal AppUser user) {
        return jdbc.queryForMap("""
            SELECT u.id,u.login_id,u.employee_no,u.name,u.role,u.job_grade,u.job_family,d.name department
            FROM users u JOIN departments d ON d.id=u.department_id WHERE u.id=?
            """,user.id());
    }
}
