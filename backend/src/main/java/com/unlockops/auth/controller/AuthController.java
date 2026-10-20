package com.unlockops.auth.controller;

import com.unlockops.auth.dto.AuthDtos.*;
import com.unlockops.auth.dto.UserProfileResponse;
import com.unlockops.auth.model.AppUser;
import com.unlockops.auth.service.AuthService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/auth")
public class AuthController {
    private final AuthService service;
    private final HttpSessionSecurityContextRepository contexts;
    public AuthController(AuthService service, HttpSessionSecurityContextRepository contexts) {
        this.service = service;
        this.contexts = contexts;
    }

    @GetMapping("/csrf")
    public CsrfResponse csrf(CsrfToken token) { return new CsrfResponse(token.getToken(), token.getHeaderName()); }

    @PostMapping("/login")
    public UserProfileResponse login(@RequestBody @Valid Login body, HttpServletRequest request, HttpServletResponse response) {
        var auth = service.authenticate(body);
        request.getSession(true);
        request.changeSessionId();
        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(auth);
        SecurityContextHolder.setContext(context);
        contexts.saveContext(context, request, response);
        return service.profile((AppUser) auth.getPrincipal());
    }

    @GetMapping("/me")
    public UserProfileResponse me(@AuthenticationPrincipal AppUser user) { return service.profile(user); }
}
