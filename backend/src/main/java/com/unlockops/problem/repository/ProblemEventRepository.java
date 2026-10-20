package com.unlockops.problem.repository;

import com.unlockops.common.json.Jsons;
import com.unlockops.messaging.model.EventKind;
import com.unlockops.problem.model.ProblemEvent;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProblemEventRepository {
    private final JdbcTemplate jdbc;
    private final Jsons json;
    public ProblemEventRepository(JdbcTemplate jdbc, Jsons json) { this.jdbc = jdbc; this.json = json; }

    public void append(UUID eventId, UUID problemId, EventKind kind, Object payload) {
        jdbc.update("INSERT INTO problem_events(event_id,problem_id,kind,payload) VALUES (?,?,?,?::jsonb)",
            eventId, problemId, kind.name(), json.write(payload));
    }

    public List<ProblemEvent> findByProblem(UUID id) {
        return jdbc.query("SELECT kind,payload::text payload,created_at FROM problem_events WHERE problem_id=? ORDER BY id",
            (rs, n) -> new ProblemEvent(EventKind.valueOf(rs.getString("kind")), json.tree(rs.getString("payload")),
                rs.getObject("created_at", OffsetDateTime.class)), id);
    }
}
