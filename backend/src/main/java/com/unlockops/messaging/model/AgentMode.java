package com.unlockops.messaging.model;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import java.util.Locale;

public enum AgentMode {
    DEMO, LLM;

    @JsonValue public String value() { return name().toLowerCase(Locale.ROOT); }
    @JsonCreator public static AgentMode from(String value) { return valueOf(value.toUpperCase(Locale.ROOT)); }
}
