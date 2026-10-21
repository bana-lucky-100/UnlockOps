package com.unlockops.messaging.listener;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.common.json.Jsons;
import com.unlockops.messaging.dto.AgentEvent;
import com.unlockops.messaging.model.QueueRoute;
import com.unlockops.messaging.service.AgentResultService;
import com.unlockops.messaging.service.InvalidAgentMessageException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class AgentResultsListener {
    private final AgentResultService service;
    private final Jsons json;
    public AgentResultsListener(AgentResultService service, Jsons json) { this.service = service; this.json = json; }

    @RabbitListener(queues = QueueRoute.RESULTS_QUEUE)
    public void consume(JsonNode rawEnvelope) {
        // Keep the full Python envelope for audit, including producer-specific progress/evidence fields.
        AgentEvent event;
        try { event = json.read(rawEnvelope, AgentEvent.class); }
        catch (IllegalArgumentException e) {
            throw new InvalidAgentMessageException(InvalidAgentMessageException.Reason.INVALID_ENVELOPE, e);
        }
        service.apply(event, rawEnvelope);
    }
}
