package com.unlockops.reclaim;

import com.fasterxml.jackson.databind.JsonNode;
import com.unlockops.common.workflow.WorkflowAccessControl;
import com.unlockops.common.workflow.WorkflowStore;
import com.unlockops.contracts.v2.WorkflowTypes.*;
import java.time.*;
import java.time.temporal.ChronoUnit;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import static com.unlockops.common.workflow.WorkflowStore.*;
import static com.unlockops.contracts.v2.WorkflowTypes.ReclaimExecutionBlockReason.*;

@Service
public class ReclaimExecutionService {
    public static final class ExecutionConflict extends ResponseStatusException {
        private final String code;
        private final String receiptId;
        public ExecutionConflict(String code,String message,String receiptId) {
            super(HttpStatus.CONFLICT,message);this.code=code;this.receiptId=receiptId;
        }
        public String code() { return code; }
        public String receiptId() { return receiptId; }
    }
    private record Check(UUID review,ReclaimExecutionBlockReason blocked,ReclaimFactsRepository.PolicyContext policy,JsonNode facts) {}
    private final ReclaimExecutionRepository repository;
    private final ReclaimFactsRepository facts;
    private final WorkflowAccessControl acl;
    private final WorkflowStore db;
    private final boolean demo;

    public ReclaimExecutionService(ReclaimExecutionRepository repository,ReclaimFactsRepository facts,
            WorkflowAccessControl acl,WorkflowStore db,@Value("${app.demo-enabled:false}") boolean demo) {
        this.repository=repository;this.facts=facts;this.acl=acl;this.db=db;this.demo=demo;
    }
    private static OffsetDateTime now() {
        return OffsetDateTime.now(ZoneId.of("Asia/Seoul")).truncatedTo(ChronoUnit.MICROS);
    }
    @Transactional(readOnly=true)
    public ReclaimExecutionState state(UUID actor,UUID id) {
        var t=repository.target(id,false);acl.assignment(actor,t.assignmentId());
        var receipt=repository.receipt(t.assignmentId()).orElse(null);
        var check=check(actor,t,receipt,now());
        return db.checked(new ReclaimExecutionState(2,id.toString(),t.assignmentId().toString(),t.episodeId().toString(),
            check.review()==null?null:check.review().toString(),t.employeeName(),t.resourceName(),AssignmentStatus.valueOf(t.assignmentStatus()),
            check.blocked()==null,check.blocked(),receipt==null?ReclaimExecutionStatus.NOT_EXECUTED:ReclaimExecutionStatus.SUCCEEDED,receipt),ReclaimExecutionState.class);
    }
    private Check check(UUID actor,ReclaimExecutionRepository.Target t,ReclaimExecutionReceipt receipt,OffsetDateTime time) {
        var review=repository.latestReview(t.assignmentId(),t.id()).orElse(null);
        UUID run=review==null?null:review.runId();
        if(!acl.canExecuteReclaim(actor,t.assignmentId())) return new Check(run,EXECUTION_FORBIDDEN,null,null);
        if(!demo || !t.mock()) return new Check(run,MOCK_ONLY,null,null);
        if(receipt!=null) return new Check(run,ALREADY_REVOKED,null,null);
        if(!t.open() || !"ACTIVE".equals(t.assignmentStatus())) return new Check(run,CANDIDATE_CHANGED,null,null);
        if(review==null || !review.confirmed()) return new Check(run,RECHECK_REQUIRED,null,null);
        var policy=facts.policy(t.companyId()).orElse(null);
        if(policy==null) return new Check(run,RECHECK_REQUIRED,null,null);
        var current=facts.assignment(t.assignmentId(),policy,time).orElse(null);
        if(current==null) return new Check(run,CANDIDATE_CHANGED,null,null);
        var decision=ReclaimPolicy.evaluate(current,policy.policy(),policy.rules(),time);
        var blocked=Boolean.TRUE.equals(decision.reviewRequired())?RECHECK_REQUIRED:
            decision.candidateStatus()==CandidateStatus.PENDING_REVIEW && t.ruleCode().equals(decision.candidateReasonCode())?null:CANDIDATE_CHANGED;
        return new Check(run,blocked,policy,current);
    }
    @Transactional
    public ReclaimExecutionReceipt revoke(UUID actor,UUID id,String key,ReclaimRevokeInput input) {
        key(key);if(input==null)throw new IllegalArgumentException("JSON body {} required");
        var initial=repository.target(id,false);acl.assignment(actor,initial.assignmentId());
        forbid(demo && initial.mock() && acl.canExecuteReclaim(actor,initial.assignmentId()));
        repository.lockCompany(initial.companyId());
        var t=repository.target(id,true);
        // Recheck authorization after waiting for the execution/candidate locks.
        acl.assignment(actor,t.assignmentId());forbid(acl.canExecuteReclaim(actor,t.assignmentId()));
        String requestHash=hash(id+"|{}");
        var saved=repository.request(t.companyId(),actor,key).orElse(null);
        if(saved!=null) {
            if(!saved.requestHash().equals(requestHash)) throw new ExecutionConflict("IDEMPOTENCY_CONFLICT","같은 요청 키에 다른 회수 입력이 사용되었습니다.",null);
            throw new ExecutionConflict("ALREADY_REVOKED","이미 모의 회수가 완료되었습니다. 완료 이력을 확인해 주세요.",saved.receipt().id());
        }
        var prior=repository.receipt(t.assignmentId()).orElse(null);
        if(prior!=null) throw new ExecutionConflict("ALREADY_REVOKED","이미 모의 회수가 완료되었습니다. 완료 이력을 확인해 주세요.",prior.id());
        var time=now();var check=check(actor,t,null,time);
        if(check.blocked()!=null) throw new ExecutionConflict(check.blocked().name(),"회수 조건이 변경되었거나 확인이 필요합니다. 최신 근거를 다시 점검해 주세요.",null);
        boolean providerBefore=repository.providerPresent(t.assignmentId());
        repository.revoke(t.assignmentId(),check.review(),time);
        if(!repository.verified(t.assignmentId())) throw new IllegalStateException("Mock revoke postconditions did not hold");
        var user=acl.actor(actor);
        var receipt=db.checked(new ReclaimExecutionReceipt(2,UUID.randomUUID().toString(),id.toString(),t.assignmentId().toString(),
            t.episodeId().toString(),check.review().toString(),t.employeeName(),t.resourceName(),actor.toString(),str(user,"name"),time.toString(),"담당자 확정으로 모의 권한 회수",true,
            "ACTIVE","INACTIVE",providerBefore,false,check.policy().policy().path("revision").intValue(),str(check.policy().policy(),"source_hash"),check.facts()),ReclaimExecutionReceipt.class);
        repository.save(t.companyId(),actor,key,requestHash,receipt);
        return receipt;
    }
    @Transactional(readOnly=true)
    public ReclaimExecutionPage history(UUID actor,int offset) {
        if(offset<0)throw new IllegalArgumentException("Invalid cursor");
        var user=acl.actor(actor);forbid("APPROVER".equals(str(user,"role")));
        var all=repository.history(uuid(user,"company_id"),actor,offset);
        return db.checked(new ReclaimExecutionPage(2,all.stream().limit(50).toList(),all.size()>50?Math.addExact(offset,50):null),ReclaimExecutionPage.class);
    }
}
