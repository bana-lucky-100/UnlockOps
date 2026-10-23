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
    private final com.unlockops.phase2.messaging.Phase2Results phase2;
    @org.springframework.beans.factory.annotation.Autowired
    public AgentResultsListener(AgentResultService service, Jsons json, com.unlockops.phase2.messaging.Phase2Results phase2) {
        this.service=service; this.json=json; this.phase2=phase2;
    }
    public AgentResultsListener(AgentResultService service, Jsons json) { this(service,json,null); }

    @RabbitListener(queues = QueueRoute.RESULTS_QUEUE)
    public void consume(JsonNode rawEnvelope) {
        if (rawEnvelope.has("schema_version")) {
            var version=rawEnvelope.path("schema_version");
            if (!version.isIntegralNumber() || version.intValue()!=2 || phase2==null)
                throw new InvalidAgentMessageException(InvalidAgentMessageException.Reason.INVALID_ENVELOPE);
            phase2.apply(rawEnvelope);
            return;
        }
        // Keep the full Python envelope for audit, including producer-specific progress/evidence fields.
        AgentEvent event;
        try { event = json.read(rawEnvelope, AgentEvent.class); }
        catch (IllegalArgumentException e) {
            throw new InvalidAgentMessageException(InvalidAgentMessageException.Reason.INVALID_ENVELOPE, e);
        }
        service.apply(event, rawEnvelope);
    }
}
