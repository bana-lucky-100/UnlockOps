package com.unlockops;

import com.fasterxml.jackson.databind.*;
import com.unlockops.contracts.v2.*;
import com.unlockops.contracts.v2.WorkflowTypes.*;
import java.nio.file.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class WorkflowContractTest {
    private final ObjectMapper mapper=new ObjectMapper();
    private final WorkflowCodec codec=new WorkflowCodec();
    private JsonNode vectors() throws Exception {
        return mapper.readTree(Files.readString(Path.of("../contracts/phase2/examples/vectors.json")));
    }
    private Class<?> model(String name) throws Exception {
        return Class.forName("com.unlockops.contracts.v2.WorkflowTypes$"+name);
    }
    @Test void sharedValidAndInvalidVectors() throws Exception {
        for (var v:vectors().get("valid"))
            assertDoesNotThrow(()->codec.read(v.get("payload").toString(),model(v.get("model").asText())),v.get("name").asText());
        for (var v:vectors().get("invalid"))
            assertThrows(IllegalArgumentException.class,()->codec.read(v.get("payload").toString(),model(v.get("model").asText())),v.get("name").asText());
    }
    @Test void canonicalHashMatchesPythonAndBindsRevisions() throws Exception {
        var v=vectors(); var raw=v.get("valid").get(0).get("payload");
        var plan=codec.read(raw.toString(),GrantPlanV2.class);
        assertEquals(v.get("plan_canonical_json").asText(),codec.canonicalPlan(plan));
        assertEquals(v.get("plan_sha256").asText(),codec.planHash(plan));
        for (String field:new String[]{"entitlement_revision","pricing_revision","policy_revision","route_revision"}) {
            var changed=((com.fasterxml.jackson.databind.node.ObjectNode)raw).deepCopy().put(field,2);
            assertNotEquals(codec.planHash(plan),codec.planHash(codec.read(changed.toString(),GrantPlanV2.class)));
        }
    }
}
