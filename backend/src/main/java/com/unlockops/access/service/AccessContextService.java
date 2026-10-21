package com.unlockops.access.service;

import com.unlockops.access.dto.AccessContextRequests.Lookup;
import com.unlockops.access.dto.AccessContextResponses.*;
import com.unlockops.access.repository.AccessContextRepository;
import com.unlockops.grant.model.AccessScope;
import com.unlockops.grant.model.Resource;
import com.unlockops.grant.repository.GrantRepository;
import java.util.Map;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AccessContextService {
    private final AccessContextRepository facts;
    private final GrantRepository grants;
    private final AccessCeilingPolicy policy;

    public AccessContextService(AccessContextRepository facts, GrantRepository grants, AccessCeilingPolicy policy) {
        this.facts = facts;
        this.grants = grants;
        this.policy = policy;
    }

    /** DB 조회는 같은 스냅샷에서 수행한다. 승인·권한·예산을 변경하지 않는다. */
    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
    public Context lookup(Lookup request) {
        if (request.resourceId() == null) {
            try {
                Profile profile = facts.profile(request.employeeId());
                Budget budget = request.includeBudget() ? facts.budget(profile.departmentId()) : null;
                return new Context(profile, null, null, null, null, budget, null, Map.of());
            } catch (EmptyResultDataAccessException e) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND, "직원을 찾을 수 없습니다.");
            }
        }
        Resource resource;
        Profile profile;
        try {
            resource = grants.resource(request.resourceId());
            if (request.platform() != null && resource.platform() != request.platform())
                throw new ResponseStatusException(HttpStatus.CONFLICT, "선택한 플랫폼과 대상 자원이 다릅니다.");
            profile = facts.profile(request.employeeId());
        } catch (EmptyResultDataAccessException e) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "직원 또는 대상 자원을 찾을 수 없습니다.");
        }
        Membership membership = facts.membership(profile.id(), resource.id());
        Current current = facts.current(profile.id(), resource);
        Budget budget = resource.accessScope() == AccessScope.SEAT ? facts.budget(profile.departmentId()) : null;
        var ceiling = policy.ceiling(profile, resource);
        return new Context(profile, resource.id(), membership, current, ceiling.role(), budget,
            "A-ACCESS-03", ceiling.sourceHashes());
    }
}
