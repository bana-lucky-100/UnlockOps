package com.unlockops;

import java.util.ArrayList;
import java.util.List;
import org.springframework.amqp.core.*;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MessagingConfig {
    @Bean Declarables topology() {
        var exchange=new DirectExchange("unlockops",true,false);
        List<Declarable> declarations=new ArrayList<>(); declarations.add(exchange);
        for(String key:List.of("analysis","execution","results","dead")) {
            Queue queue=key.equals("dead")?new Queue("unlockops.dead",true):
                QueueBuilder.durable("unlockops."+key).deadLetterExchange("unlockops").deadLetterRoutingKey("dead").build();
            declarations.add(queue); declarations.add(BindingBuilder.bind(queue).to(exchange).with(key));
        }
        return new Declarables(declarations);
    }
    @Bean Jackson2JsonMessageConverter converter() { return new Jackson2JsonMessageConverter(); }
}
