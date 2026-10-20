package com.unlockops;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;
import java.util.TreeMap;
import org.springframework.stereotype.Component;

@Component
class Jsons {
    private final ObjectMapper mapper;
    Jsons(ObjectMapper mapper) { this.mapper=mapper; }
    String write(Object value) {
        try { return mapper.writeValueAsString(value); }
        catch(Exception e) { throw new IllegalArgumentException("Invalid JSON",e); }
    }
    Map<String,Object> object(String value) {
        try { return mapper.readValue(value,new TypeReference<>(){}); }
        catch(Exception e) { throw new IllegalArgumentException("Invalid JSON",e); }
    }
    Object any(String value) {
        try { return mapper.readValue(value,Object.class); }
        catch(Exception e) { throw new IllegalArgumentException("Invalid JSON",e); }
    }
    String planHash(Map<String,Object> plan) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                .digest(write(new TreeMap<>(plan)).getBytes(StandardCharsets.UTF_8)));
        } catch(Exception e) { throw new IllegalArgumentException("Invalid plan",e); }
    }
}
