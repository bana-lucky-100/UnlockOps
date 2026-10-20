package com.unlockops.grant.model;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import java.util.Arrays;

public enum SaasRole {
    READ("Read"), WRITE("Write"), SEAT("Seat"), VIEWER("Viewer"), DEVELOPER("Developer"),
    MEMBER("Member"), CAN_VIEW("Can view");

    private final String value;
    SaasRole(String value) { this.value = value; }
    @JsonValue public String value() { return value; }
    @JsonCreator public static SaasRole from(String value) {
        return Arrays.stream(values()).filter(role -> role.value.equals(value)).findFirst()
            .orElseThrow(() -> new IllegalArgumentException("Unsupported SaaS role"));
    }
}
