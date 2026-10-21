package com.unlockops.access.service;

import com.unlockops.access.dto.AccessVerificationRequests.Verify;
import com.unlockops.access.dto.AccessVerificationResponses.Verified;
import com.unlockops.access.repository.AccessContextRepository;
import com.unlockops.grant.model.Platform;
import com.unlockops.grant.model.Resource;
import com.unlockops.grant.repository.GrantRepository;
import com.unlockops.grant.service.ResourceRolePolicy;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AccessVerificationService {
    private final AccessContextRepository facts;
    private final GrantRepository grants;

    public AccessVerificationService(AccessContextRepository facts, GrantRepository grants) {
        this.facts = facts; this.grants = grants;
    }

    /** 분석 상태·실행 영수증을 재사용하지 않고 독립된 읽기 트랜잭션에서 다시 조회한다. */
    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ, propagation = Propagation.REQUIRES_NEW)
    public Verified verify(Verify request) {
        Resource resource;
        try {
            resource = grants.resource(request.resourceId());
            if (resource.platform() != request.platform())
                throw new ResponseStatusException(HttpStatus.CONFLICT, "선택한 플랫폼과 대상 자원이 다릅니다.");
            facts.profile(request.employeeId()); // 없는 직원과 권한이 없는 직원을 구분한다.
        } catch (EmptyResultDataAccessException e) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "직원 또는 대상 자원을 찾을 수 없습니다.");
        }
        var current = facts.current(request.employeeId(), resource);
        boolean verified = ResourceRolePolicy.satisfies(resource, current.role(), request.requestedRole());
        if (resource.platform() == Platform.JIRA) verified &= Boolean.TRUE.equals(current.canBrowse());
        return new Verified(true, verified, current);
    }
}
