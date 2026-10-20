package com.unlockops.approval.service;

import com.unlockops.approval.dto.ApprovalSummaryResponse;
import com.unlockops.approval.repository.ApprovalRepository;
import com.unlockops.auth.model.AppUser;
import com.unlockops.grant.service.GrantPolicy;
import org.springframework.stereotype.Service;

@Service
public class ApprovalService {
    private final ApprovalRepository approvals;
    private final GrantPolicy policy;
    public ApprovalService(ApprovalRepository approvals, GrantPolicy policy) {
        this.approvals = approvals;
        this.policy = policy;
    }

    public ApprovalSummaryResponse summary(AppUser user) {
        policy.requireApprover(user);
        return approvals.summary(user.id());
    }
}
