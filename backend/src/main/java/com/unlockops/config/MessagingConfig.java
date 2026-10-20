package com.unlockops.config;

import com.unlockops.messaging.model.QueueRoute;
import java.util.ArrayList;
import java.util.List;
import org.springframework.amqp.core.*;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MessagingConfig {
    @Bean Declarables topology() {
        var exchange = new DirectExchange(QueueRoute.EXCHANGE, true, false);
        List<Declarable> declarations = new ArrayList<>();
        declarations.add(exchange);
        for (QueueRoute route : QueueRoute.values()) {
            Queue queue = route == QueueRoute.DEAD ? new Queue(route.queue(), true) :
                QueueBuilder.durable(route.queue()).deadLetterExchange(QueueRoute.EXCHANGE)
                    .deadLetterRoutingKey(QueueRoute.DEAD.key()).build();
            declarations.add(queue);
            declarations.add(BindingBuilder.bind(queue).to(exchange).with(route.key()));
        }
        return new Declarables(declarations);
    }

    @Bean Jackson2JsonMessageConverter converter() { return new Jackson2JsonMessageConverter(); }
}
