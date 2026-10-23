package com.unlockops.messaging.listener;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.messaging.model.QueueRoute;
import com.unlockops.messaging.workflow.WorkflowResults;
import com.unlockops.messaging.service.InvalidAgentMessageException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class AgentResultsListener {
    private final WorkflowResults results;
    public AgentResultsListener(WorkflowResults results) { this.results=results; }

    @RabbitListener(queues = QueueRoute.RESULTS_QUEUE)
    public void consume(JsonNode envelope) {
        var version=envelope.path("schema_version");
        if (!version.isIntegralNumber() || version.intValue()!=2)
            throw new InvalidAgentMessageException(InvalidAgentMessageException.Reason.INVALID_ENVELOPE);
        results.apply(envelope);
    }
}
