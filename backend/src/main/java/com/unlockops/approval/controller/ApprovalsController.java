package com.unlockops.approval.controller;

import com.unlockops.approval.dto.ApprovalSummaryResponse;
import com.unlockops.approval.service.ApprovalService;
import com.unlockops.auth.model.AppUser;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/approvals")
public class ApprovalsController {
    private final ApprovalService service;
    public ApprovalsController(ApprovalService service) { this.service = service; }

    @GetMapping("/summary")
    public ApprovalSummaryResponse summary(@AuthenticationPrincipal AppUser user) { return service.summary(user); }
}
