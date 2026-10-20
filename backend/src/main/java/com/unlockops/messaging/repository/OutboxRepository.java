package com.unlockops.messaging.repository;

import com.unlockops.common.json.Jsons;
import com.unlockops.messaging.dto.JobMessage;
import com.unlockops.messaging.model.OutboxMessage;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OutboxRepository {
    private final JdbcTemplate jdbc;
    private final Jsons json;
    public OutboxRepository(JdbcTemplate jdbc, Jsons json) { this.jdbc = jdbc; this.json = json; }

    public void enqueue(JobMessage job) {
        jdbc.update("INSERT INTO outbox(event_id,routing_key,payload) VALUES (?,?,?::jsonb)",
            job.eventId(), job.jobType().routingKey(), json.write(job));
    }

    public List<OutboxMessage> lockPending() {
        return jdbc.query("""
            SELECT event_id,routing_key,payload::text payload FROM outbox
            WHERE published_at IS NULL ORDER BY created_at LIMIT 20 FOR UPDATE SKIP LOCKED
            """, (rs, n) -> new OutboxMessage(rs.getObject("event_id", UUID.class),
                rs.getString("routing_key"), rs.getString("payload")));
    }

    public void markPublished(UUID eventId) {
        jdbc.update("UPDATE outbox SET published_at=NOW() WHERE event_id=?", eventId);
    }
}
