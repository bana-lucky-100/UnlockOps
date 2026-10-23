package com.unlockops;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.unlockops.messaging.listener.AgentResultsListener;
import com.unlockops.messaging.workflow.WorkflowResults;
import com.unlockops.messaging.service.InvalidAgentMessageException;
import org.junit.jupiter.api.Test;
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;

class WorkflowListenerTest {
    @Test void oldOrUnknownEnvelopesNeverReachBusinessResults() throws Exception {
        var service=mock(WorkflowResults.class);var listener=new AgentResultsListener(service);var json=new ObjectMapper();
        for(String raw:new String[]{"{}","{\"schema_version\":1}","{\"schema_version\":3}","{\"schema_version\":\"2\"}"})
            assertThrows(InvalidAgentMessageException.class,()->listener.consume(json.readTree(raw)));
        verifyNoInteractions(service);
    }
    @Test void currentEnvelopeHasOneResultPath() throws Exception {
        var service=mock(WorkflowResults.class);var event=new ObjectMapper().readTree("{\"schema_version\":2}");
        new AgentResultsListener(service).consume(event);
        verify(service).apply(event);verifyNoMoreInteractions(service);
    }
}
