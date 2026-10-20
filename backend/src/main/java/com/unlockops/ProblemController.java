package com.unlockops;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/problems")
class ProblemController {
    private final ProblemService service;
    ProblemController(ProblemService service) { this.service=service; }
    record Create(@NotBlank String platform,@NotBlank @Size(max=5000) String contents,boolean simulateJiraFailure) {}
    record Decision(boolean approved,@NotBlank @Size(max=64) String expectedPlanHash,@Size(max=1000) String reason) {}
    @PostMapping @ResponseStatus(HttpStatus.ACCEPTED)
    Map<String,Object> create(@AuthenticationPrincipal AppUser user,@RequestBody @Valid Create body) {
        return service.create(user,body.platform(),body.contents(),body.simulateJiraFailure());
    }
    @GetMapping List<Map<String,Object>> list(@AuthenticationPrincipal AppUser user,
            @RequestParam(defaultValue="false") boolean mine) { return service.list(user,mine); }
    @GetMapping("/{id}") Map<String,Object> detail(@AuthenticationPrincipal AppUser user,@PathVariable UUID id) { return service.detail(user,id); }
    @PostMapping("/{id}/decision") Map<String,Object> decide(@AuthenticationPrincipal AppUser user,@PathVariable UUID id,@RequestBody @Valid Decision body) {
        return service.decide(user,id,body.approved(),body.expectedPlanHash(),body.reason()==null?"":body.reason().strip());
    }
}
