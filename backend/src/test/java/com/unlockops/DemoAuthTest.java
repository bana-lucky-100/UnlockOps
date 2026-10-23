package com.unlockops;

import com.unlockops.auth.controller.AuthController;
import com.unlockops.auth.dto.AuthDtos.DemoLogin;
import com.unlockops.auth.dto.UserProfileResponse;
import com.unlockops.auth.model.AppUser;
import com.unlockops.auth.model.UserRole;
import com.unlockops.auth.repository.UserRepository;
import com.unlockops.auth.service.AuthService;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;

class DemoAuthTest {
    private final AppUser user=new AppUser(UUID.randomUUID(),"p2_a_requester","server-hash",UserRole.REQUESTER);
    private final AtomicReference<Authentication> credentials=new AtomicReference<>();
    private final AuthenticationManager manager=input -> {
        credentials.set(input);
        return UsernamePasswordAuthenticationToken.authenticated(user,null,user.getAuthorities());
    };
    private class Accounts extends UserRepository {
        List<AppUser> accounts=List.of(user);
        Accounts() { super(null); }
        @Override public List<AppUser> phase2DemoAccounts() { return accounts; }
        @Override public UserProfileResponse profile(UUID id) {
            return new UserProfileResponse(id,user.loginId(),"P2-A-0","김개발",UserRole.REQUESTER,null,null,"업무팀",2,false);
        }
    }
    @AfterEach void clearContext() { SecurityContextHolder.clearContext(); }

    @Test void demoLoginIsDisabledOutsideDemoAndCannotSelectOrdinaryAccounts() {
        var accounts=new Accounts();
        assertEquals(404,assertThrows(ResponseStatusException.class,
            () -> new AuthService(manager,accounts,false,"custom-demo-password").authenticateDemo(user.loginId())).getStatusCode().value());
        var service=new AuthService(manager,accounts,true,"custom-demo-password");
        for(String login:List.of("song_ops","admin","p2_a_unknown","p2_c_requester"))
            assertEquals(403,assertThrows(ResponseStatusException.class,() -> service.authenticateDemo(login)).getStatusCode().value());
        assertNull(credentials.get());
    }

    @Test void quickLoginUsesServerPasswordAndNormalAuthentication() {
        var service=new AuthService(manager,new Accounts(),true,"changed-server-password");
        assertEquals(user,service.authenticateDemo(user.loginId()).getPrincipal());
        assertEquals(user.loginId(),credentials.get().getName());
        assertEquals("changed-server-password",credentials.get().getCredentials());
    }

    @Test void missingMockAccountIsReportedAsSetupFailure() {
        var accounts=new Accounts();accounts.accounts=List.of();
        var service=new AuthService(manager,accounts,true,"custom-demo-password");
        assertEquals(503,assertThrows(ResponseStatusException.class,() -> service.authenticateDemo(user.loginId())).getStatusCode().value());
        assertNull(credentials.get());
    }

    @Test void quickLoginRotatesAndPersistsTheNormalAuthenticatedSession() {
        var accounts=new Accounts();
        var controller=new AuthController(new AuthService(manager,accounts,true,"custom-demo-password"),
            new HttpSessionSecurityContextRepository());
        var request=new MockHttpServletRequest();
        String previous=request.getSession(true).getId();
        var profile=controller.demoLogin(new DemoLogin(user.loginId()),request,new MockHttpServletResponse());
        assertEquals(2,profile.workflowVersion());
        assertNotEquals(previous,request.getSession().getId());
        var context=(SecurityContext)request.getSession().getAttribute(HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
        assertEquals(user,context.getAuthentication().getPrincipal());
    }
}
