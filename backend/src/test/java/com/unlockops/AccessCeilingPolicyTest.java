package com.unlockops;

import com.unlockops.access.dto.AccessContextResponses.Profile;
import com.unlockops.access.service.AccessCeilingPolicy;
import com.unlockops.auth.model.*;
import com.unlockops.grant.model.*;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;

class AccessCeilingPolicyTest {
    @TempDir Path temporary;

    private Path source() {
        return Files.exists(Path.of("data/company-a-access-matrix.md")) ? Path.of("data/company-a-access-matrix.md") :
            Path.of("../data/company-a-access-matrix.md");
    }

    private Profile profile(JobGrade grade, JobFamily family) {
        return new Profile(UUID.randomUUID(), "E-001", "직원", UUID.randomUUID(), "개발팀", grade, family, null);
    }

    private Resource resource(Platform platform, AccessScope scope) {
        return new Resource(UUID.randomUUID(), platform, "example", scope, null, null, null, null);
    }

    @ParameterizedTest
    @CsvSource({
        "GITHUB,GENERAL,STAFF,DEV,Read", "GITHUB,GENERAL,ASSISTANT_MANAGER,DEV,Write",
        "GITHUB,TF,STAFF,DEV,Write", "GITHUB,TF,GENERAL_MANAGER,NON_DEV,Read",
        "GITHUB,SEAT,STAFF,DEV,Seat", "JIRA,GENERAL,STAFF,DEV,Viewer",
        "JIRA,GENERAL,MANAGER,DEV,Developer", "JIRA,TF,STAFF,DEV,Developer",
        "JIRA,TF,MANAGER,NON_DEV,Viewer", "SLACK,GENERAL,STAFF,NON_DEV,Member",
        "SLACK,TF,STAFF,DEV,Member", "NOTION,GENERAL,MANAGER,DEV,Can view",
        "NOTION,DEPARTMENT,STAFF,DEV,Can view", "NOTION,DEPARTMENT,ASSISTANT_MANAGER,DEV,Can edit",
        "NOTION,DEPARTMENT,STAFF,NON_DEV,Can view", "NOTION,DEPARTMENT,MANAGER,NON_DEV,Can edit",
        "NOTION,TF,GENERAL_MANAGER,DEV,Can view", "NOTION,CONFIDENTIAL,MANAGER,NON_DEV,Can view"
    })
    void followsTheCurrentDocument(Platform platform, AccessScope scope, JobGrade grade, JobFamily family, String expected) {
        var result = new AccessCeilingPolicy(source().toString()).ceiling(profile(grade, family), resource(platform, scope));
        assertEquals(expected, result.role());
        assertTrue(result.sourceHashes().get("company-a-access-matrix.md").matches("[0-9a-f]{64}"));
    }

    @Test void explicitIneligibilityIsEmptyAndNotUnknown() {
        assertEquals("", new AccessCeilingPolicy(source().toString()).ceiling(
            profile(JobGrade.MANAGER, JobFamily.NON_DEV), resource(Platform.GITHUB, AccessScope.SEAT)).role());
    }

    @Test void changedSourceChangesTheCeilingAndItsHash() throws Exception {
        Path file = temporary.resolve("matrix.md");
        String original = Files.readString(source());
        Files.writeString(file, original);
        var policy = new AccessCeilingPolicy(file.toString());
        var employee = profile(JobGrade.STAFF, JobFamily.DEV);
        var target = resource(Platform.GITHUB, AccessScope.GENERAL);
        var before = policy.ceiling(employee, target);
        Files.writeString(file, original.replace("| GitHub | 일반 저장소 | Read |", "| GitHub | 일반 저장소 | Write |"));
        var after = policy.ceiling(employee, target);
        assertEquals("Write", after.role());
        assertNotEquals(before.sourceHashes(), after.sourceHashes());
    }

    @Test void missingInvalidOrAmbiguousPolicyNeverDefaultsToPermission() throws Exception {
        var employee = profile(JobGrade.STAFF, JobFamily.DEV);
        var target = resource(Platform.GITHUB, AccessScope.GENERAL);
        Path file = temporary.resolve("matrix.md");
        assertEquals(503, assertThrows(ResponseStatusException.class, () ->
            new AccessCeilingPolicy(file.toString()).ceiling(employee, target)).getStatusCode().value());
        String original = Files.readString(source());
        for (String invalid : new String[]{"no table", original.replace("| GitHub | 일반 저장소 | Read |", "| GitHub | 일반 저장소 | Owner |"),
                original.replace("| GitHub | 일반 저장소 | Read | **Write** | Read |",
                    "| GitHub | 일반 저장소 | Read | **Write** | Read |\n| GitHub | 일반 저장소 | Read | **Write** | Read |")}) {
            Files.writeString(file, invalid);
            assertEquals(503, assertThrows(ResponseStatusException.class, () ->
                new AccessCeilingPolicy(file.toString()).ceiling(employee, target)).getStatusCode().value());
        }
        assertThrows(ResponseStatusException.class, () -> new AccessCeilingPolicy(source().toString())
            .ceiling(employee, resource(Platform.SLACK, AccessScope.SEAT)));
    }
}
