package com.unlockops.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.filter.OncePerRequestFilter;

@Configuration
public class InternalApiSecurityConfig {
    /** 내부 호출은 서비스 토큰으로 인증하고 화면용 세션·CSRF 설정과 분리한다. */
    @Bean
    @Order(1)
    SecurityFilterChain internalApiSecurity(HttpSecurity http,
            @Value("${app.internal-api-token:replace-this-local-internal-api-token}") String token) throws Exception {
        return http.securityMatcher("/internal/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .addFilterBefore(new ServiceTokenFilter(token), UsernamePasswordAuthenticationFilter.class)
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .build();
    }

    private static final class ServiceTokenFilter extends OncePerRequestFilter {
        private final String expected;
        private ServiceTokenFilter(String token) { expected = token.isBlank() ? "" : "Bearer " + token; }

        @Override
        protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                        FilterChain chain) throws ServletException, IOException {
            String supplied = request.getHeader("Authorization");
            if (expected.isEmpty() || supplied == null || !MessageDigest.isEqual(
                    expected.getBytes(StandardCharsets.UTF_8), supplied.getBytes(StandardCharsets.UTF_8))) {
                response.setStatus(401);
                response.setContentType("application/json");
                response.setCharacterEncoding("UTF-8");
                response.getWriter().write("{\"message\":\"내부 서비스 인증이 필요합니다.\"}");
                return;
            }
            var context = SecurityContextHolder.createEmptyContext();
            context.setAuthentication(UsernamePasswordAuthenticationToken.authenticated(
                "business-mcp", null, List.of()));
            SecurityContextHolder.setContext(context);
            chain.doFilter(request, response);
        }
    }
}
