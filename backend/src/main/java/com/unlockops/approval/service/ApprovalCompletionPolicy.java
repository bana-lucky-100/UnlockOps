package com.unlockops.approval.service;

import com.unlockops.problem.model.DecisionSource;
import com.unlockops.problem.model.Problem;
import org.springframework.stereotype.Component;

/** Current workflow requires one human approval. Extend this boundary with persisted steps in Phase 2. */
@Component
public class ApprovalCompletionPolicy {
    public boolean isComplete(Problem problem) {
        return problem.decisionSource() == DecisionSource.HUMAN
            && problem.decidedAt() != null && problem.decidedBy() != null
            && problem.approvedPlanHash() != null;
    }
}
