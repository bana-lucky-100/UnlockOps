package com.unlockops.grant.service;

import com.unlockops.auth.model.*;
import com.unlockops.auth.repository.UserRepository;
import com.unlockops.grant.model.*;
import com.unlockops.grant.repository.GrantRepository;
import com.unlockops.problem.model.Problem;
import java.util.Objects;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class GrantPolicy {
    private final UserRepository users;
    private final GrantRepository grants;

    public GrantPolicy(UserRepository users, GrantRepository grants) {
        this.users = users;
        this.grants = grants;
    }

    public static void check(boolean condition, String message) {
        if (!condition) throw new ResponseStatusException(HttpStatus.CONFLICT, message);
    }

    public boolean operations(AppUser user) { return user.loginId().equals("song_ops"); }

    public UUID reviewer(UUID requester) {
        UUID head = users.employee(requester).headId();
        // This fallback permits visibility only; validatePlan still rejects self-approval.
        return requester.equals(head) ? users.operationsUserId() : head;
    }

    public void requireApprover(AppUser user) {
        if (user.role() != UserRole.APPROVER || !users.employee(user.id()).jobGrade().atLeast(JobGrade.MANAGER))
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "승인 담당자만 접근할 수 있습니다.");
    }

    public UUID validatePlan(Problem problem, GrantPlan plan) {
        check(plan != null, "실행 계획 형식이 유효하지 않습니다.");
        UUID requester = problem.requesterId();
        check(Objects.equals(problem.id(), plan.problemId()), "요청 ID가 다릅니다.");
        check(Objects.equals(requester, plan.requesterId()), "요청자가 다릅니다.");
        check(problem.platform() == plan.platform(), "플랫폼이 다릅니다.");
        Resource resource = grants.resource(plan.resourceId());
        check(resource.platform() == plan.platform() && Objects.equals(resource.externalId(), plan.resourceKey()), "대상 자원이 다릅니다.");
        EmployeeProfile profile = users.employee(requester);
        AccessScope scope = resource.accessScope();
        if (scope == AccessScope.TF)
            check(grants.activeTfMember(requester, resource.tfId()), "현재 TF 구성원이 아닙니다.");
        if (resource.securityGrade() == SecurityGrade.CONFIDENTIAL)
            check(Objects.equals(profile.departmentId(), resource.designatedDepartmentId()), "기밀 지정 부서가 아닙니다.");
        if (scope == AccessScope.DEPARTMENT)
            check(Objects.equals(profile.departmentId(), resource.ownerDepartmentId()), "소유 부서가 아닙니다.");
        check(roleAllowed(resource.platform(), scope, plan.requestedRole(), profile), "자동 부여 가능한 권한의 상한을 초과합니다.");
        if (resource.platform() == Platform.JIRA)
            check(grants.canBrowseJira(resource.id(), plan.requestedRole()), "해당 Jira 역할에 프로젝트 조회 권한이 없습니다.");
        if (scope == AccessScope.SEAT) {
            check(grants.budget(profile.departmentId()).canAffordSeat(), "부서 예산이 부족합니다.");
            check(!grants.hasSeat(requester, resource.id()), "이미 좌석을 보유하고 있습니다.");
        }
        UUID approver = resource.tfId() == null ? profile.headId() : grants.tfLeader(resource.tfId());
        check(approver != null && !requester.equals(approver), "본인 승인은 불가하며 유효한 승인자가 필요합니다.");
        EmployeeProfile actor = users.employee(approver);
        check(actor.role() == UserRole.APPROVER && actor.jobGrade().atLeast(JobGrade.MANAGER), "승인자의 역할 또는 직급이 유효하지 않습니다.");
        return approver;
    }

    private boolean roleAllowed(Platform platform, AccessScope scope, SaasRole role, EmployeeProfile profile) {
        boolean dev = profile.jobFamily() == JobFamily.DEV;
        boolean senior = profile.jobGrade().atLeast(JobGrade.ASSISTANT_MANAGER);
        return switch (platform) {
            case GITHUB -> scope == AccessScope.SEAT ? dev && role == SaasRole.SEAT :
                role == SaasRole.READ || (dev && (scope == AccessScope.TF || senior) && role == SaasRole.WRITE);
            case JIRA -> role == SaasRole.VIEWER || (dev && (scope == AccessScope.TF || senior) && role == SaasRole.DEVELOPER);
            case SLACK -> role == SaasRole.MEMBER;
            case NOTION -> role == SaasRole.CAN_VIEW;
        };
    }
}
