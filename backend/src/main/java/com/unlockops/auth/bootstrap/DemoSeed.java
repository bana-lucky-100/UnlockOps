package com.unlockops.auth.bootstrap;

import com.unlockops.auth.repository.UserRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class DemoSeed implements ApplicationRunner {
    private final UserRepository users;
    private final PasswordEncoder encoder;
    private final boolean enabled;
    private final String password;

    public DemoSeed(UserRepository users, PasswordEncoder encoder, @Value("${app.demo-enabled}") boolean enabled,
                    @Value("${app.demo-password}") String password) {
        this.users = users;
        this.encoder = encoder;
        this.enabled = enabled;
        this.password = password;
    }

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        if (!enabled) return;
        if (password.length() < 8) throw new IllegalStateException("DEMO_PASSWORD must contain at least eight characters");
        for (var id : users.findWithoutPassword()) users.setPassword(id, encoder.encode(password));
    }
}
