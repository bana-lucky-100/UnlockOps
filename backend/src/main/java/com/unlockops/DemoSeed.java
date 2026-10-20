package com.unlockops;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
class DemoSeed implements ApplicationRunner {
    private final JdbcTemplate jdbc;
    private final PasswordEncoder encoder;
    private final boolean enabled;
    private final String password;
    DemoSeed(JdbcTemplate jdbc,PasswordEncoder encoder,@Value("${app.demo-enabled}") boolean enabled,
             @Value("${app.demo-password}") String password) {
        this.jdbc=jdbc; this.encoder=encoder; this.enabled=enabled; this.password=password;
    }
    @Override @Transactional public void run(ApplicationArguments args) {
        if (!enabled) return;
        if (password.length()<8) throw new IllegalStateException("DEMO_PASSWORD must contain at least eight characters");
        // Existing password hashes are preserved on restart.
        for (var row:jdbc.queryForList("SELECT id FROM users WHERE password_hash=''"))
            jdbc.update("UPDATE users SET password_hash=? WHERE id=?",encoder.encode(password),row.get("id"));
    }
}
