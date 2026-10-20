package com.unlockops;

import java.math.BigDecimal;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
class GrantRules {
    static final Map<String,Integer> GRADES=Map.of("사원",1,"대리",2,"과장",3,"차장",4,"부장",5);
    static final Set<String> PLAN_KEYS=Set.of("problem_id","requester_id","platform","resource_id","resource_key","requested_role");
    private final JdbcTemplate jdbc;
    GrantRules(JdbcTemplate jdbc) { this.jdbc=jdbc; }
    static void check(boolean condition,String message) {
        if (!condition) throw new ResponseStatusException(HttpStatus.CONFLICT,message);
    }
    Map<String,Object> employee(UUID id) {
        return jdbc.queryForMap("SELECT u.id,u.role,u.department_id,u.job_grade,u.job_family,d.head_id FROM users u JOIN departments d ON d.id=u.department_id WHERE u.id=?",id);
    }
    UUID assigned(UUID requester, UUID resourceId) {
        var u=employee(requester);
        if (resourceId!=null) {
            var r=jdbc.queryForMap("SELECT tf_id FROM resources WHERE id=?",resourceId);
            if (r.get("tf_id")!=null)
                return jdbc.queryForObject("SELECT leader_id FROM tfs WHERE id=?",UUID.class,r.get("tf_id"));
        }
        return (UUID)u.get("head_id");
    }
    UUID reviewer(UUID requester) {
        UUID head=assigned(requester,null);
        // Operational visibility only; the unchecked fallback never authorizes a grant.
        return requester.equals(head) ? jdbc.queryForObject("SELECT id FROM users WHERE login_id='song_ops'",UUID.class) : head;
    }
    void requireApprover(AppUser user) {
        if (!"APPROVER".equals(user.role()) || GRADES.getOrDefault(employee(user.id()).get("job_grade"),0)<3)
            throw new ResponseStatusException(HttpStatus.FORBIDDEN,"승인 담당자만 접근할 수 있습니다.");
    }
    UUID validatePlan(Map<String,Object> problem, Map<String,Object> plan) {
        check(plan!=null && plan.keySet().equals(PLAN_KEYS),"실행 계획 형식이 유효하지 않습니다.");
        UUID requester=(UUID)problem.get("requester_id");
        check(Objects.equals(problem.get("id").toString(),plan.get("problem_id")),"요청 ID가 다릅니다.");
        check(Objects.equals(requester.toString(),plan.get("requester_id")),"요청자가 다릅니다.");
        check(Objects.equals(problem.get("platform"),plan.get("platform")),"플랫폼이 다릅니다.");
        UUID resourceId=UUID.fromString(plan.get("resource_id").toString());
        var resource=jdbc.queryForMap("SELECT * FROM resources WHERE id=?",resourceId);
        check(Objects.equals(resource.get("platform"),plan.get("platform")) &&
              Objects.equals(resource.get("external_id"),plan.get("resource_key")),"대상 자원이 다릅니다.");
        var profile=employee(requester);
        String platform=resource.get("platform").toString(),scope=resource.get("access_scope").toString();
        String role=plan.get("requested_role").toString();
        boolean dev="DEV".equals(profile.get("job_family"));
        boolean senior=GRADES.getOrDefault(profile.get("job_grade"),0)>=2;
        if ("TF".equals(scope)) {
            Integer count=jdbc.queryForObject("""
                SELECT count(*) FROM tf_members m JOIN tfs t ON t.id=m.tf_id
                WHERE m.user_id=? AND m.tf_id=? AND m.active AND t.starts_on<=CURRENT_DATE
                AND (t.ends_on IS NULL OR t.ends_on>=CURRENT_DATE)
                """,Integer.class,requester,resource.get("tf_id"));
            check(count!=null && count==1,"현재 TF 구성원이 아닙니다.");
        }
        if ("CONFIDENTIAL".equals(resource.get("security_grade")))
            check(Objects.equals(profile.get("department_id"),resource.get("designated_department_id")),"기밀 지정 부서가 아닙니다.");
        if ("DEPARTMENT".equals(scope))
            check(Objects.equals(profile.get("department_id"),resource.get("owner_department_id")),"소유 부서가 아닙니다.");
        boolean allowed=switch(platform) {
            case "GITHUB" -> "SEAT".equals(scope) ? dev && "Seat".equals(role) :
                "Read".equals(role) || (dev && ("TF".equals(scope)||senior) && "Write".equals(role));
            case "JIRA" -> "Viewer".equals(role) || (dev && ("TF".equals(scope)||senior) && "Developer".equals(role));
            case "SLACK" -> "Member".equals(role);
            case "NOTION" -> "Can view".equals(role); // Editing is explicitly outside this demo.
            default -> false;
        };
        check(allowed,"자동 부여 가능한 권한의 상한을 초과합니다.");
        if("JIRA".equals(platform)) {
            Boolean browse=jdbc.queryForObject("SELECT can_browse FROM jira_role_permissions WHERE resource_id=? AND saas_role=?",
                Boolean.class,resourceId,role);
            check(Boolean.TRUE.equals(browse),"해당 Jira 역할에 프로젝트 조회 권한이 없습니다.");
        }
        if ("SEAT".equals(scope)) {
            var b=jdbc.queryForMap("SELECT * FROM department_budgets WHERE department_id=?",profile.get("department_id"));
            check(((BigDecimal)b.get("remaining_monthly_amount")).compareTo((BigDecimal)b.get("unit_monthly_price"))>=0,"부서 예산이 부족합니다.");
            Integer seats=jdbc.queryForObject("SELECT count(*) FROM permissions WHERE user_id=? AND resource_id=?",Integer.class,requester,resourceId);
            check(seats!=null && seats==0,"이미 좌석을 보유하고 있습니다.");
        }
        UUID approver=assigned(requester,resourceId);
        check(approver!=null && !requester.equals(approver),"본인 승인은 불가하며 유효한 승인자가 필요합니다.");
        var a=employee(approver);
        check("APPROVER".equals(a.get("role")) && GRADES.getOrDefault(a.get("job_grade"),0)>=3,"승인자의 역할 또는 직급이 유효하지 않습니다.");
        return approver;
    }
}
