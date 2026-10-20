package com.unlockops.common.json;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.unlockops.grant.model.GrantPlan;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.springframework.stereotype.Component;

@Component
public class Jsons {
    private final ObjectMapper mapper;

    public Jsons(ObjectMapper mapper) { this.mapper = mapper; }

    public String write(Object value) {
        try { return mapper.writeValueAsString(value); }
        catch (Exception e) { throw new IllegalArgumentException("Invalid JSON", e); }
    }

    public JsonNode tree(String value) {
        try { return value == null ? null : mapper.readTree(value); }
        catch (Exception e) { throw new IllegalArgumentException("Invalid JSON", e); }
    }

    public <T> T read(JsonNode value, Class<T> type) {
        try { return mapper.treeToValue(value, type); }
        catch (Exception e) { throw new IllegalArgumentException("Invalid JSON", e); }
    }

    public GrantPlan plan(JsonNode value) {
        try {
            return mapper.readerFor(GrantPlan.class)
                .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                .with(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
                .with(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
                .readValue(value);
        } catch (Exception e) { throw new IllegalArgumentException("Invalid plan", e); }
    }

    public String planHash(GrantPlan plan) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                .digest(write(plan).getBytes(StandardCharsets.UTF_8)));
        } catch (Exception e) { throw new IllegalArgumentException("Invalid plan", e); }
    }
}
