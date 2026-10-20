package com.unlockops.auth.model;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import java.util.Arrays;

public enum JobGrade {
    STAFF("사원", 1), ASSISTANT_MANAGER("대리", 2), MANAGER("과장", 3),
    DEPUTY_GENERAL_MANAGER("차장", 4), GENERAL_MANAGER("부장", 5);

    private final String label;
    private final int rank;

    JobGrade(String label, int rank) { this.label = label; this.rank = rank; }
    @JsonValue public String label() { return label; }
    public boolean atLeast(JobGrade grade) { return rank >= grade.rank; }
    @JsonCreator public static JobGrade from(String value) {
        return Arrays.stream(values()).filter(grade -> grade.label.equals(value)).findFirst()
            .orElseThrow(() -> new IllegalArgumentException("Unknown job grade"));
    }
}
