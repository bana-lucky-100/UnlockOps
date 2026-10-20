package com.unlockops.messaging.service;

import com.unlockops.messaging.publisher.RabbitMessagePublisher;
import com.unlockops.messaging.repository.OutboxRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OutboxService {
    private final OutboxRepository outbox;
    private final RabbitMessagePublisher publisher;
    public OutboxService(OutboxRepository outbox, RabbitMessagePublisher publisher) {
        this.outbox = outbox;
        this.publisher = publisher;
    }

    @Transactional
    public void publishPending() {
        for (var message : outbox.lockPending()) {
            publisher.publish(message);
            outbox.markPublished(message.eventId());
        }
    }
}
