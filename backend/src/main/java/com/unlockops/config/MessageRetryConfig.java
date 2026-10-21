package com.unlockops.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.unlockops.messaging.service.MessageFailureClassifier;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.support.ListenerExecutionFailedException;
import org.springframework.boot.autoconfigure.amqp.RabbitProperties;
import org.springframework.boot.autoconfigure.amqp.RabbitRetryTemplateCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.RetryCallback;
import org.springframework.retry.RetryContext;
import org.springframework.retry.RetryListener;
import org.springframework.retry.policy.SimpleRetryPolicy;

@Configuration
public class MessageRetryConfig {
    private static final Logger log = LoggerFactory.getLogger(MessageRetryConfig.class);
    private record Identity(UUID eventId, UUID problemId) {}

    @Bean MessageFailureClassifier messageFailureClassifier() { return new MessageFailureClassifier(); }

    @Bean RabbitRetryTemplateCustomizer resultRetryPolicy(RabbitProperties properties,
                                                          MessageFailureClassifier classifier, ObjectMapper json) {
        return (target, template) -> {
            if (target != RabbitRetryTemplateCustomizer.Target.LISTENER) return;
            int attempts = properties.getListener().getSimple().getRetry().getMaxAttempts();
            template.setRetryPolicy(new SimpleRetryPolicy(attempts) {
                @Override public boolean canRetry(RetryContext context) {
                    return super.canRetry(context) && (context.getLastThrowable() == null
                        || classifier.classify(context.getLastThrowable()).retryable());
                }
            });
            template.registerListener(new RetryListener() {
                @Override public <T, E extends Throwable> void onError(RetryContext context,
                                                                      RetryCallback<T, E> callback, Throwable error) {
                    Identity identity = identity(error, json);
                    context.setAttribute("resultIdentity", identity);
                    log.warn("RESULT_ATTEMPT_FAILED event_id={} problem_id={} attempt={} classification={}",
                        identity.eventId(), identity.problemId(), context.getRetryCount(), classifier.classify(error));
                }

                @Override public <T, E extends Throwable> void close(RetryContext context,
                                                                    RetryCallback<T, E> callback, Throwable error) {
                    if (context.getRetryCount() == 0) return;
                    Identity identity = (Identity) context.getAttribute("resultIdentity");
                    if (identity == null) return;
                    // Service transactions have finished before a successful listener invocation returns.
                    log.info("RESULT_RETRY_FINISHED event_id={} problem_id={} attempts={} outcome={}",
                        identity.eventId(), identity.problemId(), context.getRetryCount() + (error == null ? 1 : 0),
                        error == null ? "HANDLED" : "REJECTED");
                }
            });
        };
    }

    private Identity identity(Throwable error, ObjectMapper json) {
        // Read only UUIDs from the failed delivery. Never log its body or exception messages.
        for (int depth = 0; error != null && depth < 20; depth++, error = error.getCause()) {
            if (error instanceof ListenerExecutionFailedException failed) {
                Message message = failed.getFailedMessage();
                if (message == null) break;
                try {
                    var envelope = json.readTree(message.getBody());
                    return new Identity(uuid(envelope.path("event_id").asText()), uuid(envelope.path("problem_id").asText()));
                } catch (Exception ignored) { break; }
            }
        }
        return new Identity(null, null);
    }

    private UUID uuid(String value) {
        try { return UUID.fromString(value); }
        catch (IllegalArgumentException e) { return null; }
    }
}
