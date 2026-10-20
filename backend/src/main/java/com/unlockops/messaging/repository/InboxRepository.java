package com.unlockops.messaging.repository;

import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class InboxRepository {
    private final JdbcTemplate jdbc;
    public InboxRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public boolean recordIfNew(UUID eventId) {
        return jdbc.update("INSERT INTO inbox_events(event_id) VALUES (?) ON CONFLICT DO NOTHING", eventId) != 0;
    }
}
