package com.unlockops.messaging.service;

import com.unlockops.messaging.dto.JobMessage;
import com.unlockops.messaging.model.JobType;
import com.unlockops.messaging.repository.OutboxRepository;
import com.unlockops.problem.model.Problem;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class JobService {
    private final OutboxRepository outbox;
    public JobService(OutboxRepository outbox) { this.outbox = outbox; }

    /** Joins the caller's create/decision transaction; no broker I/O occurs here. */
    public void enqueue(Problem problem, JobType type, String idempotencyKey) {
        outbox.enqueue(new JobMessage(UUID.randomUUID(), type, problem.id(), problem.requesterId(),
            problem.platform(), problem.contents(), idempotencyKey, problem.planHash()));
    }
}
