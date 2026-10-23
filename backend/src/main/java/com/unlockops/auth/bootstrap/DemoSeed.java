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
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;

@Component
public class DemoSeed implements ApplicationRunner {
    private final UserRepository users;
    private final PasswordEncoder encoder;
    private final boolean enabled;
    private final String password;
    private final JdbcTemplate jdbc;
    private final String seedPath;

    public DemoSeed(UserRepository users, PasswordEncoder encoder, @Value("${app.demo-enabled}") boolean enabled,
                    @Value("${app.demo-password}") String password, JdbcTemplate jdbc,
                    @Value("${app.demo-seed-path:}") String seedPath) {
        this.users = users;
        this.encoder = encoder;
        this.enabled = enabled;
        this.password = password;
        this.jdbc = jdbc;
        this.seedPath = seedPath;
    }

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        if (!enabled) return;
        if (password.length() < 8) throw new IllegalStateException("DEMO_PASSWORD must contain at least eight characters");
        if (!seedPath.isBlank()) prepareData();
        for (var id : users.findWithoutPassword()) users.setPassword(id, encoder.encode(password));
        // Only the twelve synthetic login accounts follow the current demo password on restart.
        for (var user : users.demoAccounts()) {
            if (!encoder.matches(password,user.passwordHash())) users.setPassword(user.id(),encoder.encode(password));
        }
    }

    private void prepareData() {
        try {
            // Spring owns the transaction so seed and password preparation commit together.
            executeScript(Path.of(seedPath));
            var directory=Path.of(seedPath).toAbsolutePath().getParent().resolve("policies");
            for(int revision=2;revision<=4;revision++) {
                Integer ready=jdbc.queryForObject("SELECT count(DISTINCT p.company_id) FROM policy_revisions p JOIN companies c ON c.id=p.company_id WHERE c.code IN ('P2_A','P2_B') AND p.revision>=?",Integer.class,revision);
                if(ready!=null && ready==2)continue;
                executeScript(directory.resolve(revision==2 ? "apply.sql" : revision==3 ? "apply-v4.sql" : "apply-costs.sql"));
            }
        } catch (IOException e) {
            throw new IllegalStateException("Cannot read demo seed: " + seedPath,e);
        }
    }
    private void executeScript(Path path) throws IOException {
        String sql=Files.readString(path,StandardCharsets.UTF_8)
            .replaceAll("(?m)^(BEGIN|COMMIT);[\\t ]*\\r?$","");
        jdbc.execute((ConnectionCallback<Void>) connection -> {
            // PostgreSQL parses the entire script, including dollar-quoted DO blocks.
            // Splitting on semicolons would corrupt immutable revision imports.
            try(var statement=connection.createStatement()) { statement.execute(sql); }
            return null;
        });
    }
}
