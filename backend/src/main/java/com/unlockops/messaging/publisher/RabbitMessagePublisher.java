package com.unlockops.messaging.publisher;

import com.unlockops.messaging.model.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;
import org.springframework.amqp.core.*;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class RabbitMessagePublisher {
    private final RabbitTemplate rabbit;
    public RabbitMessagePublisher(RabbitTemplate rabbit) { this.rabbit = rabbit; }

    public void publish(OutboxMessage row) {
        var properties = new MessageProperties();
        properties.setContentType("application/json");
        properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
        properties.setMessageId(row.eventId().toString());
        var message = new Message(row.payload().getBytes(StandardCharsets.UTF_8), properties);
        var correlation = new CorrelationData(row.eventId().toString());
        rabbit.send(QueueRoute.EXCHANGE, row.routingKey(), message, correlation);
        try {
            var confirm = correlation.getFuture().get(5, TimeUnit.SECONDS);
            if (!confirm.isAck() || correlation.getReturned() != null)
                throw new IllegalStateException("Broker did not route/confirm the message");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Outbox delivery interrupted", e);
        } catch (Exception e) {
            throw new IllegalStateException("Outbox delivery unconfirmed", e);
        }
    }
}
