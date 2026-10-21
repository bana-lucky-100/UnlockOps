package com.unlockops.grant.service;

import com.unlockops.grant.model.*;
import java.util.Set;

/** 같은 자원 역할군 안에서만 포함 관계를 비교한다. 저장소 권한과 좌석은 분리한다. */
public final class ResourceRolePolicy {
    private ResourceRolePolicy() {}

    public static boolean supports(Resource resource, String role) {
        return role != null && family(resource).contains(role);
    }

    public static boolean satisfies(Resource resource, String held, String requested) {
        return supports(resource, held) && supports(resource, requested) && rank(held) >= rank(requested);
    }

    private static Set<String> family(Resource resource) {
        if (resource.accessScope() == AccessScope.SEAT) return Set.of("Seat");
        return switch (resource.platform()) {
            case GITHUB -> Set.of("Read", "Write"); case JIRA -> Set.of("Viewer", "Developer");
            case SLACK -> Set.of("Member"); case NOTION -> Set.of("Can view", "Can edit");
        };
    }

    private static int rank(String role) {
        return switch (role) {
            case "Read", "Viewer", "Can view", "Member", "Seat" -> 1;
            case "Write", "Developer", "Can edit" -> 2;
            default -> 0;
        };
    }
}
