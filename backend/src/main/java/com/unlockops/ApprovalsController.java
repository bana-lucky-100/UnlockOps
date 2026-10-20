package com.unlockops;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/approvals")
class ApprovalsController {
    private final ProblemService service;
    ApprovalsController(ProblemService service) { this.service=service; }

    @GetMapping("/summary")
    Map<String,Object> summary(@AuthenticationPrincipal AppUser user) {
        return service.approvalSummary(user);
    }
}
