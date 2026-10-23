package com.unlockops.auth.bootstrap;

import com.unlockops.auth.repository.UserRepository;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.support.EncodedResource;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.init.ScriptUtils;

@Component
public class DemoSeed implements ApplicationRunner {
    private final UserRepository users;
    private final PasswordEncoder encoder;
    private final boolean enabled;
    private final String password;
    private final JdbcTemplate jdbc;
    private final String phase2SeedPath;

    public DemoSeed(UserRepository users, PasswordEncoder encoder, @Value("${app.demo-enabled}") boolean enabled,
                    @Value("${app.demo-password}") String password, JdbcTemplate jdbc,
                    @Value("${app.demo-phase2-seed-path:}") String phase2SeedPath) {
        this.users = users;
        this.encoder = encoder;
        this.enabled = enabled;
        this.password = password;
        this.jdbc = jdbc;
        this.phase2SeedPath = phase2SeedPath;
    }

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        if (!enabled) return;
        if (password.length() < 8) throw new IllegalStateException("DEMO_PASSWORD must contain at least eight characters");
        if (!phase2SeedPath.isBlank()) preparePhase2();
        for (var id : users.findWithoutPassword()) users.setPassword(id, encoder.encode(password));
        // Only the twelve synthetic login accounts follow the current demo password on restart.
        for (var user : users.phase2DemoAccounts()) {
            if (!encoder.matches(password,user.passwordHash())) users.setPassword(user.id(),encoder.encode(password));
        }
    }

    private void preparePhase2() {
        try {
            // Spring owns the transaction so seed and password preparation commit together.
            String sql=Files.readString(Path.of(phase2SeedPath),StandardCharsets.UTF_8)
                .replaceAll("(?m)^(BEGIN|COMMIT);[\\t ]*\\r?$","");
            var script=new EncodedResource(new ByteArrayResource(sql.getBytes(StandardCharsets.UTF_8)),StandardCharsets.UTF_8);
            jdbc.execute((ConnectionCallback<Void>) connection -> {
                ScriptUtils.executeSqlScript(connection,script);
                return null;
            });
        } catch (IOException e) {
            throw new IllegalStateException("Cannot read demo seed: " + phase2SeedPath,e);
        }
    }
}
