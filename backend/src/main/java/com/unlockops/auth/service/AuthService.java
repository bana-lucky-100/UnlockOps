package com.unlockops.auth.service;

import com.unlockops.auth.dto.AuthDtos.Login;
import com.unlockops.auth.dto.UserProfileResponse;
import com.unlockops.auth.model.AppUser;
import com.unlockops.auth.repository.UserRepository;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@Service
public class AuthService {
    private final AuthenticationManager manager;
    private final UserRepository users;
    private final boolean demoEnabled;
    private final String demoPassword;
    public AuthService(AuthenticationManager manager, UserRepository users,
                       @Value("${app.demo-enabled}") boolean demoEnabled,
                       @Value("${app.demo-password}") String demoPassword) {
        this.manager = manager; this.users = users;
        this.demoEnabled = demoEnabled; this.demoPassword = demoPassword;
    }

    public Authentication authenticate(Login request) {
        return manager.authenticate(UsernamePasswordAuthenticationToken.unauthenticated(request.loginId(), request.password()));
    }

    public Authentication authenticateDemo(String loginId) {
        if (!demoEnabled) throw new ResponseStatusException(HttpStatus.NOT_FOUND,"시연 로그인을 사용할 수 없습니다.");
        if (!UserRepository.isPhase2DemoLogin(loginId))
            throw new ResponseStatusException(HttpStatus.FORBIDDEN,"시연용 계정만 선택할 수 있습니다.");
        if (users.phase2DemoAccounts().stream().noneMatch(user -> user.loginId().equals(loginId)))
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"시연 계정이 준비되지 않았습니다. 시연 데이터 설정 후 백엔드를 다시 시작해 주세요.");
        return authenticate(new Login(loginId,demoPassword));
    }

    public UserProfileResponse profile(AppUser user) { return users.profile(user.id()); }
}
