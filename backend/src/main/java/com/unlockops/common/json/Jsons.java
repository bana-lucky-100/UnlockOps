package com.unlockops.common.json;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
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

}
