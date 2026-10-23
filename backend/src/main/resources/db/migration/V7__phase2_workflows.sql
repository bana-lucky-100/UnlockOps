-- Runtime identities: request retry, analysis generation and grant execution are distinct.
ALTER TABLE problems ADD COLUMN request_payload JSONB;
ALTER TABLE problems ADD COLUMN active_job_event_id UUID;
ALTER TABLE problems ADD COLUMN active_plan_version INTEGER;
ALTER TABLE problems ADD COLUMN requested_entitlement_id UUID;
ALTER TABLE problems ADD FOREIGN KEY(requested_entitlement_id,company_id) REFERENCES entitlements(id,company_id);
ALTER TABLE problems ADD FOREIGN KEY(id,active_plan_version) REFERENCES access_plan_versions(problem_id,version);
ALTER TABLE reclaim_runs ADD COLUMN active_job_event_id UUID;
-- Freeze pricing/policy/rules and evaluated rows along with the assignment facts.
ALTER TABLE reclaim_snapshots ADD COLUMN context JSONB NOT NULL DEFAULT '{}';
CREATE TRIGGER immutable_snapshot BEFORE UPDATE OR DELETE ON reclaim_snapshots FOR EACH ROW EXECUTE FUNCTION protect_contract_revision();
CREATE TRIGGER immutable_snapshot_items BEFORE UPDATE OR DELETE ON reclaim_snapshot_items FOR EACH ROW EXECUTE FUNCTION protect_contract_revision();
-- Isolated mock provider state. Existing legacy providers never write v2 company resources.
CREATE TABLE mock_entitlement_memberships (
    assignment_id UUID PRIMARY KEY REFERENCES access_assignments(id),
    company_id UUID NOT NULL, user_id UUID NOT NULL, entitlement_id UUID NOT NULL,
    entitlement_revision INTEGER NOT NULL, mapping JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY(user_id,company_id) REFERENCES users(id,company_id),
    FOREIGN KEY(entitlement_id,entitlement_revision,company_id) REFERENCES entitlement_revisions(entitlement_id,revision,company_id)
);
CREATE TABLE access_execution_receipts (
    problem_id UUID PRIMARY KEY, company_id UUID NOT NULL,
    plan_version INTEGER NOT NULL, plan_hash CHAR(64) NOT NULL,
    idempotency_key VARCHAR(150) NOT NULL UNIQUE, assignment_id UUID NOT NULL,
    result JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY(problem_id,plan_version,plan_hash) REFERENCES access_plan_versions(problem_id,version,plan_hash),
    FOREIGN KEY(problem_id,company_id) REFERENCES problems(id,company_id),
    FOREIGN KEY(assignment_id,company_id) REFERENCES access_assignments(id,company_id)
);
CREATE TRIGGER immutable_execution_receipt BEFORE UPDATE OR DELETE ON access_execution_receipts FOR EACH ROW EXECUTE FUNCTION protect_contract_revision();
CREATE INDEX phase2_problems_requester ON problems(company_id,requester_id,created_at DESC) WHERE contract_version=2;
CREATE INDEX phase2_approvals_actor ON approval_steps(approver_id,problem_id,plan_version);
CREATE INDEX reclaim_items_target ON reclaim_run_items(target_id,run_id);
