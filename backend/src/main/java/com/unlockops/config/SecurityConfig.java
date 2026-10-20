package com.unlockops.config;

import com.unlockops.auth.repository.UserRepository;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;

@Configuration
public class SecurityConfig {
    @Bean PasswordEncoder passwordEncoder() { return new BCryptPasswordEncoder(); }

    @Bean UserDetailsService userDetailsService(UserRepository users) {
        return login -> users.findByLoginOrEmail(login)
            .orElseThrow(() -> new UsernameNotFoundException("Invalid credentials"));
    }

    @Bean AuthenticationManager authenticationManager(UserDetailsService users, PasswordEncoder encoder) {
        var provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean HttpSessionSecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean SecurityFilterChain securityFilterChain(HttpSecurity http,
            HttpSessionSecurityContextRepository repository) throws Exception {
        return http
            .csrf(csrf -> csrf.csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
                .csrfTokenRequestHandler(new CsrfTokenRequestAttributeHandler()))
            .securityContext(context -> context.securityContextRepository(repository))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/health","/api/auth/csrf","/api/auth/login").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((req,res,e) -> { res.setStatus(401); res.setContentType("application/json"); res.setCharacterEncoding("UTF-8"); res.getWriter().write("{\"message\":\"로그인이 필요합니다.\"}"); })
                .accessDeniedHandler((req,res,e) -> { res.setStatus(403); res.setContentType("application/json"); res.setCharacterEncoding("UTF-8"); res.getWriter().write("{\"message\":\"접근 권한이 없습니다.\"}"); }))
            .logout(logout -> logout.logoutUrl("/api/auth/logout")
                .logoutSuccessHandler((req,res,auth) -> res.setStatus(204)))
            .build();
    }
}
