package com.unlockops;

import com.unlockops.access.dto.AccessContextResponses.*;
import com.unlockops.access.service.AccessCeilingPolicy;
import com.unlockops.access.service.AccessCeilingPolicy.ExecutionRules;
import com.unlockops.auth.model.*;
import com.unlockops.grant.model.*;
import com.unlockops.grant.repository.GrantExecutionRepository.Approver;
import com.unlockops.grant.service.*;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class GrantExecutionPolicyTest {
    private final GrantExecutionPolicy policy = new GrantExecutionPolicy();
    private final UUID employee = UUID.randomUUID(), approver = UUID.randomUUID(), department = UUID.randomUUID();
    private final Profile profile = new Profile(employee, "E-001", "직원", department, "개발팀", JobGrade.STAFF, JobFamily.DEV, approver);
    private final ExecutionRules rules = new ExecutionRules("Write", Map.of(), UserRole.APPROVER, JobGrade.MANAGER);

    private Resource resource(AccessScope scope, UUID owner, SecurityGrade security, UUID designated) {
        return new Resource(UUID.randomUUID(), Platform.GITHUB, "target", scope, owner, UUID.randomUUID(), security, designated);
    }
    private GrantPlan plan(Resource resource) {
        return new GrantPlan(UUID.randomUUID(), employee, resource.platform(), resource.id(), resource.externalId(), SaasRole.WRITE);
    }

    @Test void tfAndDepartmentRestrictionsRemainRequiredEvenWhenPermissionIsAlreadyHeld() {
        var current = new Current("Write", "mock", null, null);
        var tf = resource(AccessScope.TF, department, SecurityGrade.INTERNAL, null);
        assertEquals("NOT_TF_MEMBER", assertThrows(GrantExecutionException.class, () ->
            policy.validateEligibility(plan(tf), profile, tf, new Membership(tf.tfId(), false, approver), current, null, rules)).reason());
        var other = resource(AccessScope.DEPARTMENT, UUID.randomUUID(), SecurityGrade.INTERNAL, null);
        assertEquals("DEPARTMENT_MISMATCH", assertThrows(GrantExecutionException.class, () ->
            policy.validateEligibility(plan(other), profile, other, new Membership(null, false, null), current, null, rules)).reason());
        var confidential = resource(AccessScope.CONFIDENTIAL, null, SecurityGrade.CONFIDENTIAL, UUID.randomUUID());
        assertEquals("CONFIDENTIAL_DEPARTMENT", assertThrows(GrantExecutionException.class, () ->
            policy.validateEligibility(plan(confidential), profile, confidential, new Membership(null, false, null), current, null, rules)).reason());
    }

    @Test void ceilingAndRoleFamilyCannotBeBypassedByCurrentPermissions() {
        var resource = resource(AccessScope.GENERAL, department, SecurityGrade.INTERNAL, null);
        var lower = new ExecutionRules("Read", Map.of(), UserRole.APPROVER, JobGrade.MANAGER);
        assertEquals("ABOVE_ACCESS_CEILING", assertThrows(GrantExecutionException.class, () ->
            policy.validateEligibility(plan(resource), profile, resource, new Membership(null, false, null),
                new Current("Write", "mock", null, null), null, lower)).reason());
        assertFalse(policy.validateEligibility(plan(resource), profile, resource, new Membership(null, false, null),
            new Current("Developer", "mock", null, null), null, rules));
    }

    @Test void selfApprovalLowGradeAndWrongAppRoleAreRejected() {
        var resource = resource(AccessScope.GENERAL, department, SecurityGrade.INTERNAL, null);
        var membership = new Membership(null, false, null);
        for (Approver actor : new Approver[]{new Approver(approver, UserRole.REQUESTER, JobGrade.GENERAL_MANAGER),
                new Approver(approver, UserRole.APPROVER, JobGrade.STAFF), new Approver(employee, UserRole.APPROVER, JobGrade.MANAGER)})
            assertThrows(GrantExecutionException.class, () -> policy.validateApprover(employee, approver, approver,
                profile, resource, membership, actor, rules));
    }

    @Test void executionReadsBothCurrentSourceHashesAndApproverRule() {
        var resource = resource(AccessScope.TF, department, SecurityGrade.INTERNAL, null);
        var result = new AccessCeilingPolicy("").executionRules(profile, resource);
        assertEquals("Write", result.role());
        assertEquals(UserRole.APPROVER, result.approverRole());
        assertEquals(JobGrade.MANAGER, result.minimumGrade());
        assertEquals(2, result.sourceHashes().size());
        assertTrue(result.sourceHashes().values().stream().allMatch(hash -> hash.matches("[a-f0-9]{64}")));
    }
}
