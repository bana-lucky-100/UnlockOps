package com.unlockops;

import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import java.util.concurrent.TimeUnit;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

@Component
class OutboxPublisher {
    private final JdbcTemplate jdbc;
    private final RabbitTemplate rabbit;
    private final TransactionTemplate tx;
    private static final Logger log=LoggerFactory.getLogger(OutboxPublisher.class);
    OutboxPublisher(JdbcTemplate jdbc,RabbitTemplate rabbit,org.springframework.transaction.PlatformTransactionManager manager) {
        this.jdbc=jdbc; this.rabbit=rabbit; this.tx=new TransactionTemplate(manager);
    }
    @Scheduled(fixedDelay=500)
    public void publishPending() {
        try {
            tx.executeWithoutResult(status -> {
                var rows=jdbc.queryForList("SELECT event_id,routing_key,payload::text payload FROM outbox WHERE published_at IS NULL ORDER BY created_at LIMIT 20 FOR UPDATE SKIP LOCKED");
                for(var row:rows) {
                    var properties=new MessageProperties();
                    properties.setContentType("application/json");
                    properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                    properties.setMessageId(row.get("event_id").toString());
                    var message=new Message(row.get("payload").toString().getBytes(StandardCharsets.UTF_8),properties);
                    var correlation=new CorrelationData(row.get("event_id").toString());
                    rabbit.send("unlockops",row.get("routing_key").toString(),message,correlation);
                    try {
                        var confirm=correlation.getFuture().get(5,TimeUnit.SECONDS);
                        if(!confirm.isAck() || correlation.getReturned()!=null)
                            throw new IllegalStateException("Broker did not route/confirm the message");
                    } catch(InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException("Outbox delivery interrupted");
                    } catch(Exception e) {
                        throw new IllegalStateException("Outbox delivery unconfirmed");
                    }
                    jdbc.update("UPDATE outbox SET published_at=NOW() WHERE event_id=?",row.get("event_id"));
                }
            });
        } catch(Exception e) {
            // Keep outbox rows pending. Duplicate publication is handled by consumers.
            log.warn("Outbox delivery deferred; exception={}",e.getClass().getSimpleName());
        }
    }
}
