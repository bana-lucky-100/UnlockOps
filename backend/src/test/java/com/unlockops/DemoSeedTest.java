package com.unlockops;

import com.unlockops.auth.bootstrap.DemoSeed;
import com.unlockops.auth.repository.UserRepository;
import java.nio.file.*;
import java.sql.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.*;
import org.springframework.security.crypto.password.PasswordEncoder;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class DemoSeedTest {
    @TempDir Path directory;
    @Test void postgresReceivesWholeRevisionScriptsAndRestartSkipsInstalledRevisions() throws Exception {
        String block="DO $$ BEGIN PERFORM 1; PERFORM 2; END $$;";
        Files.writeString(directory.resolve("seed.sql"),"BEGIN;\nSELECT 1;\nCOMMIT;\n");
        Files.createDirectories(directory.resolve("policies"));
        Files.writeString(directory.resolve("policies/apply.sql"),"BEGIN;\n"+block+"\nCOMMIT;\n");
        Files.writeString(directory.resolve("policies/apply-v4.sql"),"BEGIN;\n"+block+"\nCOMMIT;\n");
        Files.writeString(directory.resolve("policies/apply-costs.sql"),"BEGIN;\n"+block+"\nCOMMIT;\n");
        var statements=new ArrayList<String>();var connection=mock(Connection.class);var statement=mock(Statement.class);
        when(connection.createStatement()).thenReturn(statement);
        when(statement.execute(anyString())).thenAnswer(call->{statements.add(call.getArgument(0));return true;});
        class Database extends JdbcTemplate {
            boolean installed=false;
            @Override public <T> T execute(ConnectionCallback<T> action) {
                try {return action.doInConnection(connection);} catch(SQLException e) {throw new RuntimeException(e);}
            }
            @Override public <T> T queryForObject(String sql,Class<T> type,Object...args) {
                return type.cast(installed?2:0);
            }
        }
        var db=new Database();var users=mock(UserRepository.class);
        var seed=new DemoSeed(users,mock(PasswordEncoder.class),true,"demo1234",db,directory.resolve("seed.sql").toString());
        seed.run(null);
        assertEquals(4,statements.size());assertEquals(block,statements.get(1).trim());assertEquals(block,statements.get(2).trim());assertEquals(block,statements.get(3).trim());
        db.installed=true;seed.run(null);
        assertEquals(5,statements.size()); // Only idempotent baseline preparation repeats.
    }
    @Test void ordinaryStartupDoesNotPrepareDemoData() {
        var db=mock(JdbcTemplate.class);var users=mock(UserRepository.class);
        new DemoSeed(users,mock(PasswordEncoder.class),false,"",db,"missing").run(null);
        verifyNoInteractions(db,users);
    }
}
