package com.unlockops.auth.service;

import com.unlockops.auth.dto.AuthDtos.Login;
import com.unlockops.auth.dto.UserProfileResponse;
import com.unlockops.auth.model.AppUser;
import com.unlockops.auth.repository.UserRepository;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;

@Service
public class AuthService {
    private final AuthenticationManager manager;
    private final UserRepository users;
    public AuthService(AuthenticationManager manager, UserRepository users) { this.manager = manager; this.users = users; }

    public Authentication authenticate(Login request) {
        return manager.authenticate(UsernamePasswordAuthenticationToken.unauthenticated(request.loginId(), request.password()));
    }

    public UserProfileResponse profile(AppUser user) { return users.profile(user.id()); }
}
