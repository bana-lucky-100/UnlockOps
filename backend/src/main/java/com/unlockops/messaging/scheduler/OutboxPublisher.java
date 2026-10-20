package com.unlockops.messaging.scheduler;

import com.unlockops.messaging.service.OutboxService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class OutboxPublisher {
    private static final Logger log = LoggerFactory.getLogger(OutboxPublisher.class);
    private final OutboxService service;
    public OutboxPublisher(OutboxService service) { this.service = service; }

    @Scheduled(fixedDelay = 500)
    public void publishPending() {
        try { service.publishPending(); }
        catch (Exception e) {
            // The batch transaction rolls back; consumers handle duplicate publication on retry.
            log.warn("Outbox delivery deferred; exception={}", e.getClass().getSimpleName());
        }
    }
}
