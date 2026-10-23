-- Additive v2 foundation. V1 plans/messages and the legacy grant writer stay unchanged.
CREATE TABLE companies (
    id UUID PRIMARY KEY, code VARCHAR(30) NOT NULL UNIQUE, name VARCHAR(100) NOT NULL,
    timezone VARCHAR(60) NOT NULL DEFAULT 'Asia/Seoul', is_mock BOOLEAN NOT NULL DEFAULT TRUE
);
INSERT INTO companies VALUES ('00000000-0000-0000-0000-000000000000','LEGACY','기존 시연 조직','Asia/Seoul',TRUE);
ALTER TABLE departments ADD COLUMN company_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000' REFERENCES companies(id);
ALTER TABLE departments ADD UNIQUE(id,company_id);
ALTER TABLE users ADD COLUMN company_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000' REFERENCES companies(id);
ALTER TABLE users ADD COLUMN employment_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK(employment_status IN ('ACTIVE','LEFT','UNKNOWN'));
ALTER TABLE users ADD UNIQUE(id,company_id);
ALTER TABLE users ADD FOREIGN KEY(department_id,company_id) REFERENCES departments(id,company_id);
ALTER TABLE tfs ADD COLUMN company_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000' REFERENCES companies(id);
ALTER TABLE tfs ADD UNIQUE(id,company_id);
ALTER TABLE tfs ADD FOREIGN KEY(leader_id,company_id) REFERENCES users(id,company_id);
ALTER TABLE tf_members ADD COLUMN company_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000' REFERENCES companies(id);
ALTER TABLE tf_members ADD FOREIGN KEY(tf_id,company_id) REFERENCES tfs(id,company_id);
ALTER TABLE tf_members ADD FOREIGN KEY(user_id,company_id) REFERENCES users(id,company_id);
ALTER TABLE resources DROP CONSTRAINT resources_platform_check;
ALTER TABLE resources ADD CONSTRAINT resources_platform_check CHECK(platform IN (
    'SNOWFLAKE','DATABRICKS','SALESFORCE','DATADOG','TABLEAU_CLOUD','FIGMA','GITHUB','JIRA','SLACK','NOTION'));
ALTER TABLE resources ADD COLUMN company_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000' REFERENCES companies(id);
ALTER TABLE resources ADD COLUMN resource_type VARCHAR(40) NOT NULL DEFAULT 'LEGACY';
ALTER TABLE resources ADD UNIQUE(id,company_id);
ALTER TABLE resources ADD FOREIGN KEY(tf_id,company_id) REFERENCES tfs(id,company_id);
ALTER TABLE resources ADD FOREIGN KEY(owner_department_id,company_id) REFERENCES departments(id,company_id);
ALTER TABLE resources ADD FOREIGN KEY(designated_department_id,company_id) REFERENCES departments(id,company_id);
-- Keep legacy global external_id uniqueness until the v2 resource resolver owns scoped reads.
ALTER TABLE problems ADD COLUMN contract_version INTEGER NOT NULL DEFAULT 1 CHECK(contract_version IN (1,2));
ALTER TABLE problems ADD COLUMN task_type VARCHAR(30) NOT NULL DEFAULT 'ACCESS_REQUEST' CHECK(task_type='ACCESS_REQUEST');
ALTER TABLE problems ADD COLUMN company_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000' REFERENCES companies(id);
ALTER TABLE problems ADD UNIQUE(id,company_id);
ALTER TABLE problems ADD FOREIGN KEY(requester_id,company_id) REFERENCES users(id,company_id);
ALTER TABLE problems ADD FOREIGN KEY(resource_id,company_id) REFERENCES resources(id,company_id);
ALTER TABLE problems DROP CONSTRAINT problems_platform_check;
ALTER TABLE problems ADD CONSTRAINT problems_platform_check CHECK(platform IN (
    'SNOWFLAKE','DATABRICKS','SALESFORCE','DATADOG','TABLEAU_CLOUD','FIGMA','GITHUB','JIRA','SLACK','NOTION'));
ALTER TABLE problems DROP CONSTRAINT problems_status_check;
ALTER TABLE problems ADD CONSTRAINT problems_status_check CHECK(status IN (
    'RECEIVED','DIAGNOSING','WAITING_APPROVAL','ON_HOLD','EXECUTING','DONE','REJECTED','MANUAL_REVIEW','FAILED'));
ALTER TABLE problems ADD CHECK(contract_version=2 OR (status<>'ON_HOLD' AND platform IN ('GITHUB','JIRA','SLACK','NOTION')));

CREATE TABLE policy_revisions (
    policy_id UUID NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), company_id UUID NOT NULL REFERENCES companies(id),
    doc_id VARCHAR(100) NOT NULL, article VARCHAR(100) NOT NULL, source_path TEXT NOT NULL,
    source_hash CHAR(64) NOT NULL CHECK(source_hash ~ '^[0-9a-f]{64}$'), content TEXT NOT NULL,
    is_mock BOOLEAN NOT NULL, PRIMARY KEY(policy_id,revision), UNIQUE(policy_id,revision,company_id)
);
CREATE TABLE entitlements (
    id UUID PRIMARY KEY, company_id UUID NOT NULL REFERENCES companies(id), resource_id UUID NOT NULL,
    code VARCHAR(100) NOT NULL, kind VARCHAR(30) NOT NULL CHECK(kind IN ('ROLE','PERMISSION_SET','MEMBERSHIP','SEAT')),
    UNIQUE(resource_id,code), UNIQUE(id,company_id), UNIQUE(id,resource_id,company_id),
    FOREIGN KEY(resource_id,company_id) REFERENCES resources(id,company_id)
);
CREATE TABLE entitlement_revisions (
    entitlement_id UUID NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), company_id UUID NOT NULL,
    external_role VARCHAR(100) NOT NULL, mapping JSONB NOT NULL CHECK(jsonb_typeof(mapping)='object'),
    PRIMARY KEY(entitlement_id,revision), UNIQUE(entitlement_id,revision,company_id),
    FOREIGN KEY(entitlement_id,company_id) REFERENCES entitlements(id,company_id)
);
CREATE TABLE pricing_revisions (
    pricing_id UUID NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), company_id UUID NOT NULL,
    entitlement_id UUID NOT NULL, entitlement_revision INTEGER NOT NULL,
    monthly_amount NUMERIC(12,2) NOT NULL CHECK(monthly_amount>=0), currency CHAR(3) NOT NULL CHECK(currency ~ '^[A-Z]{3}$'),
    cost_basis VARCHAR(30) NOT NULL CHECK(cost_basis IN ('SEAT_MONTHLY','USAGE_ESTIMATE','NO_ADDITIONAL_COST')),
    source_kind VARCHAR(30) NOT NULL CHECK(source_kind IN ('SYNTHETIC_CONTRACT','CONTRACT','PUBLIC_LIST_PRICE')),
    source_reference TEXT NOT NULL, effective_from DATE NOT NULL, effective_until DATE,
    policy_id UUID NOT NULL, policy_revision INTEGER NOT NULL,
    PRIMARY KEY(pricing_id,revision), UNIQUE(pricing_id,revision,company_id),
    FOREIGN KEY(entitlement_id,entitlement_revision,company_id) REFERENCES entitlement_revisions(entitlement_id,revision,company_id),
    FOREIGN KEY(policy_id,policy_revision,company_id) REFERENCES policy_revisions(policy_id,revision,company_id),
    CHECK(effective_until IS NULL OR effective_until>=effective_from),
    CHECK(cost_basis<>'NO_ADDITIONAL_COST' OR monthly_amount=0)
);
CREATE TABLE approval_route_revisions (
    route_id UUID NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), company_id UUID NOT NULL,
    code VARCHAR(100) NOT NULL, policy_id UUID NOT NULL, policy_revision INTEGER NOT NULL,
    steps JSONB NOT NULL CHECK(jsonb_typeof(steps)='array' AND jsonb_array_length(steps)>0),
    extra_step_threshold NUMERIC(12,2) CHECK(extra_step_threshold>=0), currency CHAR(3),
    PRIMARY KEY(route_id,revision), UNIQUE(route_id,revision,company_id),
    FOREIGN KEY(policy_id,policy_revision,company_id) REFERENCES policy_revisions(policy_id,revision,company_id),
    CHECK((extra_step_threshold IS NULL) = (currency IS NULL))
);
CREATE TABLE operator_assignments (
    company_id UUID NOT NULL REFERENCES companies(id), user_id UUID NOT NULL,
    department_id UUID NOT NULL, platform VARCHAR(20) NOT NULL,
    capability VARCHAR(30) NOT NULL CHECK(capability IN ('TEAM_LEAD','DEPARTMENT_HEAD','SAAS_OPERATOR','IT_HEAD','RECLAIM_REVIEWER')),
    PRIMARY KEY(company_id,user_id,department_id,platform,capability),
    FOREIGN KEY(user_id,company_id) REFERENCES users(id,company_id),
    FOREIGN KEY(department_id,company_id) REFERENCES departments(id,company_id),
    CHECK(platform IN ('SNOWFLAKE','DATABRICKS','SALESFORCE','DATADOG','TABLEAU_CLOUD','FIGMA','GITHUB','JIRA','SLACK','NOTION'))
);
CREATE TABLE approval_steps (
    problem_id UUID NOT NULL, company_id UUID NOT NULL, plan_version INTEGER NOT NULL CHECK(plan_version>0),
    step INTEGER NOT NULL CHECK(step>0), approver_id UUID NOT NULL, requester_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL CHECK(status IN ('PENDING','WAITING','APPROVED','REJECTED','ON_HOLD','SKIPPED')),
    reason TEXT, acted_at TIMESTAMPTZ, plan_hash CHAR(64) NOT NULL CHECK(plan_hash ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY(problem_id,plan_version,step), UNIQUE(problem_id,plan_version,approver_id),
    FOREIGN KEY(problem_id,company_id) REFERENCES problems(id,company_id),
    FOREIGN KEY(approver_id,company_id) REFERENCES users(id,company_id),
    FOREIGN KEY(requester_id,company_id) REFERENCES users(id,company_id),
    CHECK(approver_id<>requester_id),
    CHECK((status IN ('APPROVED','REJECTED','ON_HOLD'))=(acted_at IS NOT NULL)),
    CHECK(status NOT IN ('REJECTED','ON_HOLD') OR (reason IS NOT NULL AND btrim(reason)<>'')),
    CHECK(status NOT IN ('PENDING','WAITING') OR reason IS NULL)
);
CREATE UNIQUE INDEX approval_one_waiting_step ON approval_steps(problem_id,plan_version) WHERE status='WAITING';
CREATE TABLE access_assignments (
    id UUID PRIMARY KEY, company_id UUID NOT NULL, user_id UUID NOT NULL, resource_id UUID NOT NULL,
    entitlement_id UUID NOT NULL, entitlement_revision INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','INACTIVE')),
    origin_tf_id UUID, granted_at TIMESTAMPTZ NOT NULL, ended_at TIMESTAMPTZ,
    source_problem_id UUID, UNIQUE(id,company_id),
    FOREIGN KEY(user_id,company_id) REFERENCES users(id,company_id),
    FOREIGN KEY(entitlement_id,resource_id,company_id) REFERENCES entitlements(id,resource_id,company_id),
    FOREIGN KEY(entitlement_id,entitlement_revision,company_id) REFERENCES entitlement_revisions(entitlement_id,revision,company_id),
    FOREIGN KEY(origin_tf_id,company_id) REFERENCES tfs(id,company_id),
    FOREIGN KEY(source_problem_id,company_id) REFERENCES problems(id,company_id),
    CHECK((status='INACTIVE')=(ended_at IS NOT NULL)), CHECK(ended_at IS NULL OR ended_at>=granted_at)
);
CREATE UNIQUE INDEX one_active_assignment ON access_assignments(user_id,entitlement_id) WHERE status='ACTIVE';
CREATE TABLE assignment_usage (
    assignment_id UUID PRIMARY KEY, company_id UUID NOT NULL, last_used_at TIMESTAMPTZ,
    observation_status VARCHAR(20) NOT NULL CHECK(observation_status IN ('KNOWN','NEVER_USED','UNKNOWN')),
    observed_at TIMESTAMPTZ NOT NULL, source_reference TEXT NOT NULL,
    FOREIGN KEY(assignment_id,company_id) REFERENCES access_assignments(id,company_id),
    CHECK((observation_status='KNOWN')=(last_used_at IS NOT NULL)),
    CHECK(last_used_at IS NULL OR last_used_at<=observed_at)
);
CREATE TABLE retention_exceptions (
    id UUID PRIMARY KEY, company_id UUID NOT NULL, assignment_id UUID NOT NULL, approved_by UUID NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL, valid_until TIMESTAMPTZ NOT NULL, reason TEXT NOT NULL CHECK(btrim(reason)<>''),
    FOREIGN KEY(assignment_id,company_id) REFERENCES access_assignments(id,company_id),
    FOREIGN KEY(approved_by,company_id) REFERENCES users(id,company_id), CHECK(valid_until>valid_from)
);
CREATE TABLE reclaim_rules (
    rule_id UUID NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), company_id UUID NOT NULL,
    policy_id UUID NOT NULL, policy_revision INTEGER NOT NULL,
    code VARCHAR(50) NOT NULL CHECK(code IN ('TF_ENDED_UNUSED_30D','EMPLOYEE_LEFT')),
    idle_days INTEGER CHECK(idle_days>=0), exclude_other_active_tf BOOLEAN NOT NULL,
    exclude_retention BOOLEAN NOT NULL, PRIMARY KEY(rule_id,revision),
    FOREIGN KEY(policy_id,policy_revision,company_id) REFERENCES policy_revisions(policy_id,revision,company_id),
    CHECK(code<>'TF_ENDED_UNUSED_30D' OR idle_days IS NOT NULL)
);
CREATE TABLE reclaim_scopes (
    id UUID PRIMARY KEY, company_id UUID NOT NULL, department_id UUID NOT NULL,
    scope_key VARCHAR(200) NOT NULL UNIQUE, platforms JSONB NOT NULL CHECK(jsonb_typeof(platforms)='array'),
    enabled BOOLEAN NOT NULL DEFAULT FALSE, UNIQUE(id,company_id),
    FOREIGN KEY(department_id,company_id) REFERENCES departments(id,company_id)
);
CREATE TABLE reclaim_runs (
    id UUID PRIMARY KEY, company_id UUID NOT NULL, scope_id UUID NOT NULL,
    task_type VARCHAR(30) NOT NULL DEFAULT 'RECLAIM_SCAN' CHECK(task_type='RECLAIM_SCAN'),
    contract_version INTEGER NOT NULL DEFAULT 2 CHECK(contract_version=2),
    trigger VARCHAR(30) NOT NULL CHECK(trigger IN ('DAILY_SCHEDULE','MANUAL_DEMO')),
    scheduled_for TIMESTAMPTZ NOT NULL, schedule_date DATE NOT NULL, requested_by UUID, client_request_key VARCHAR(128),
    request_hash CHAR(64) NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
    status VARCHAR(30) NOT NULL CHECK(status IN ('RECEIVED','DIAGNOSING','EXECUTING','DONE','MANUAL_REVIEW','FAILED')),
    reason_code VARCHAR(100), message TEXT NOT NULL,
    snapshot_id UUID, as_of TIMESTAMPTZ, scan_complete BOOLEAN NOT NULL DEFAULT FALSE,
    needs_review_count INTEGER NOT NULL DEFAULT 0 CHECK(needs_review_count>=0),
    new_candidate_count INTEGER NOT NULL DEFAULT 0 CHECK(new_candidate_count>=0),
    pending_notification_count INTEGER NOT NULL DEFAULT 0 CHECK(pending_notification_count>=0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(id,company_id), FOREIGN KEY(scope_id,company_id) REFERENCES reclaim_scopes(id,company_id),
    FOREIGN KEY(requested_by,company_id) REFERENCES users(id,company_id),
    CHECK((snapshot_id IS NULL)=(as_of IS NULL)), CHECK(NOT scan_complete OR snapshot_id IS NOT NULL),
    CHECK(status IN ('RECEIVED','DIAGNOSING') OR reason_code IS NOT NULL),
    CHECK(trigger<>'MANUAL_DEMO' OR (requested_by IS NOT NULL AND client_request_key IS NOT NULL)),
    CHECK(status<>'DONE' OR (scan_complete AND needs_review_count=0 AND pending_notification_count=0
        AND reason_code IN ('SCAN_COMPLETED','NO_NEW_CANDIDATES'))),
    CHECK(reason_code IS DISTINCT FROM 'NO_NEW_CANDIDATES' OR (status='DONE' AND new_candidate_count=0))
);
CREATE UNIQUE INDEX reclaim_one_active_run ON reclaim_runs(scope_id) WHERE status IN ('RECEIVED','DIAGNOSING','EXECUTING');
CREATE UNIQUE INDEX reclaim_daily_run ON reclaim_runs(scope_id,schedule_date) WHERE trigger='DAILY_SCHEDULE';
CREATE UNIQUE INDEX reclaim_client_request ON reclaim_runs(company_id,requested_by,client_request_key) WHERE client_request_key IS NOT NULL;
CREATE TABLE reclaim_snapshots (
    id UUID PRIMARY KEY, company_id UUID NOT NULL, run_id UUID NOT NULL UNIQUE, as_of TIMESTAMPTZ NOT NULL,
    policy_id UUID NOT NULL, policy_revision INTEGER NOT NULL, expected_count INTEGER NOT NULL CHECK(expected_count>=0),
    UNIQUE(id,company_id), FOREIGN KEY(run_id,company_id) REFERENCES reclaim_runs(id,company_id),
    FOREIGN KEY(policy_id,policy_revision,company_id) REFERENCES policy_revisions(policy_id,revision,company_id)
);
ALTER TABLE reclaim_runs ADD FOREIGN KEY(snapshot_id) REFERENCES reclaim_snapshots(id) DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE reclaim_snapshot_items (
    snapshot_id UUID NOT NULL, company_id UUID NOT NULL, ordinal BIGINT NOT NULL CHECK(ordinal>0),
    assignment_id UUID NOT NULL, facts JSONB NOT NULL CHECK(jsonb_typeof(facts)='object'),
    PRIMARY KEY(snapshot_id,ordinal), UNIQUE(snapshot_id,assignment_id),
    FOREIGN KEY(snapshot_id,company_id) REFERENCES reclaim_snapshots(id,company_id),
    FOREIGN KEY(assignment_id,company_id) REFERENCES access_assignments(id,company_id)
);
CREATE TABLE reclaim_targets (
    id UUID PRIMARY KEY, company_id UUID NOT NULL, assignment_id UUID NOT NULL, episode_id UUID NOT NULL UNIQUE,
    rule_code VARCHAR(50) NOT NULL CHECK(rule_code IN ('TF_ENDED_UNUSED_30D','EMPLOYEE_LEFT')),
    candidate_status VARCHAR(30) NOT NULL CHECK(candidate_status IN ('PENDING_REVIEW','RETAINED','EXCLUDED')),
    exclusion_reason_code VARCHAR(50), opened_at TIMESTAMPTZ NOT NULL, closed_at TIMESTAMPTZ, notified_at TIMESTAMPTZ,
    UNIQUE(id,company_id), FOREIGN KEY(assignment_id,company_id) REFERENCES access_assignments(id,company_id),
    CHECK((candidate_status='PENDING_REVIEW')=(closed_at IS NULL)),
    CHECK((candidate_status='PENDING_REVIEW' AND exclusion_reason_code IS NULL)
       OR (candidate_status='RETAINED' AND exclusion_reason_code IS NOT NULL AND exclusion_reason_code='RETENTION_APPROVED')
       OR (candidate_status='EXCLUDED' AND exclusion_reason_code IS NOT NULL AND exclusion_reason_code IN ('ACTIVE_OTHER_TF','USAGE_RESUMED')))
);
CREATE UNIQUE INDEX reclaim_active_episode ON reclaim_targets(assignment_id,rule_code) WHERE closed_at IS NULL;
CREATE TABLE reclaim_run_items (
    run_id UUID NOT NULL, company_id UUID NOT NULL, assignment_id UUID NOT NULL, target_id UUID,
    candidate_status VARCHAR(30) CHECK(candidate_status IN ('PENDING_REVIEW','RETAINED','EXCLUDED')),
    candidate_reason_code VARCHAR(50) CHECK(candidate_reason_code IN ('TF_ENDED_UNUSED_30D','EMPLOYEE_LEFT')),
    exclusion_reason_code VARCHAR(50) CHECK(exclusion_reason_code IN ('ACTIVE_OTHER_TF','RETENTION_APPROVED','USAGE_RESUMED')),
    skip_reason_code VARCHAR(30) CHECK(skip_reason_code='ALREADY_NOTIFIED'), review_required BOOLEAN NOT NULL,
    report JSONB NOT NULL, policy_evidence JSONB NOT NULL, fact_evidence JSONB NOT NULL,
    generation_mode VARCHAR(20) NOT NULL CHECK(generation_mode IN ('template','llm')),
    cost_status VARCHAR(20) NOT NULL CHECK(cost_status IN ('ESTIMATED','UNKNOWN')),
    monthly_amount NUMERIC(12,2) CHECK(monthly_amount>=0), currency CHAR(3),
    action_taken VARCHAR(20) NOT NULL DEFAULT 'NONE' CHECK(action_taken='NONE'),
    PRIMARY KEY(run_id,assignment_id), FOREIGN KEY(run_id,company_id) REFERENCES reclaim_runs(id,company_id),
    FOREIGN KEY(assignment_id,company_id) REFERENCES access_assignments(id,company_id),
    FOREIGN KEY(target_id,company_id) REFERENCES reclaim_targets(id,company_id),
    CHECK(review_required=(candidate_status IS NULL)),
    CHECK((cost_status='UNKNOWN' AND monthly_amount IS NULL) OR (cost_status='ESTIMATED' AND monthly_amount IS NOT NULL AND currency IS NOT NULL)),
    CHECK(skip_reason_code IS NULL OR (target_id IS NOT NULL AND candidate_status='PENDING_REVIEW'))
);
CREATE TABLE reclaim_notifications (
    id UUID PRIMARY KEY, company_id UUID NOT NULL, target_id UUID NOT NULL, recipient_id UUID NOT NULL,
    channel VARCHAR(20) NOT NULL DEFAULT 'IN_APP' CHECK(channel IN ('IN_APP','SLACK','EMAIL')),
    required BOOLEAN NOT NULL DEFAULT TRUE, delivery_status VARCHAR(20) NOT NULL CHECK(delivery_status IN ('PENDING','DELIVERED','FAILED')),
    delivered_at TIMESTAMPTZ, read_at TIMESTAMPTZ, attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts>=0), last_error_code VARCHAR(100),
    UNIQUE(target_id,recipient_id,channel), FOREIGN KEY(target_id,company_id) REFERENCES reclaim_targets(id,company_id),
    FOREIGN KEY(recipient_id,company_id) REFERENCES users(id,company_id),
    CHECK((delivery_status='DELIVERED')=(delivered_at IS NOT NULL)),
    CHECK(read_at IS NULL OR (delivered_at IS NOT NULL AND read_at>=delivered_at))
);
CREATE INDEX reclaim_notifications_unread ON reclaim_notifications(recipient_id,delivered_at DESC) WHERE read_at IS NULL;
CREATE TABLE reclaim_events (
    event_id UUID PRIMARY KEY, run_id UUID NOT NULL REFERENCES reclaim_runs(id), event_type VARCHAR(50) NOT NULL,
    payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Bound revisions are append-only: a policy/price/mapping change creates a new revision.
CREATE FUNCTION protect_contract_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Contract revisions are immutable; insert a new revision' USING ERRCODE='23514'; END $$;
CREATE TRIGGER immutable_policy BEFORE UPDATE OR DELETE ON policy_revisions FOR EACH ROW EXECUTE FUNCTION protect_contract_revision();
CREATE TRIGGER immutable_entitlement BEFORE UPDATE OR DELETE ON entitlement_revisions FOR EACH ROW EXECUTE FUNCTION protect_contract_revision();
CREATE TRIGGER immutable_pricing BEFORE UPDATE OR DELETE ON pricing_revisions FOR EACH ROW EXECUTE FUNCTION protect_contract_revision();
CREATE TRIGGER immutable_route BEFORE UPDATE OR DELETE ON approval_route_revisions FOR EACH ROW EXECUTE FUNCTION protect_contract_revision();
CREATE TRIGGER immutable_reclaim_rule BEFORE UPDATE OR DELETE ON reclaim_rules FOR EACH ROW EXECUTE FUNCTION protect_contract_revision();

-- Historical plan versions remain queryable after re-review. No approved payload is overwritten.
CREATE TABLE access_plan_versions (
    problem_id UUID NOT NULL, company_id UUID NOT NULL, version INTEGER NOT NULL CHECK(version>0),
    entitlement_id UUID NOT NULL, entitlement_revision INTEGER NOT NULL,
    pricing_id UUID NOT NULL, pricing_revision INTEGER NOT NULL,
    policy_id UUID NOT NULL, policy_revision INTEGER NOT NULL, route_id UUID NOT NULL, route_revision INTEGER NOT NULL,
    plan JSONB NOT NULL CHECK(jsonb_typeof(plan)='object' AND plan ? 'schema_version' AND plan->'schema_version'='2'::jsonb),
    plan_hash CHAR(64) NOT NULL CHECK(plan_hash ~ '^[0-9a-f]{64}$'), created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(problem_id,version), UNIQUE(problem_id,version,plan_hash),
    FOREIGN KEY(problem_id,company_id) REFERENCES problems(id,company_id),
    FOREIGN KEY(entitlement_id,entitlement_revision,company_id) REFERENCES entitlement_revisions(entitlement_id,revision,company_id),
    FOREIGN KEY(pricing_id,pricing_revision,company_id) REFERENCES pricing_revisions(pricing_id,revision,company_id),
    FOREIGN KEY(policy_id,policy_revision,company_id) REFERENCES policy_revisions(policy_id,revision,company_id),
    FOREIGN KEY(route_id,route_revision,company_id) REFERENCES approval_route_revisions(route_id,revision,company_id)
);
ALTER TABLE approval_steps ADD FOREIGN KEY(problem_id,plan_version,plan_hash) REFERENCES access_plan_versions(problem_id,version,plan_hash);
ALTER TABLE problems ADD UNIQUE(id,company_id,requester_id);
ALTER TABLE approval_steps ADD FOREIGN KEY(problem_id,company_id,requester_id) REFERENCES problems(id,company_id,requester_id);
ALTER TABLE reclaim_targets ADD UNIQUE(id,assignment_id,company_id);
ALTER TABLE reclaim_run_items ADD FOREIGN KEY(target_id,assignment_id,company_id) REFERENCES reclaim_targets(id,assignment_id,company_id);
CREATE TRIGGER immutable_plan BEFORE UPDATE OR DELETE ON access_plan_versions FOR EACH ROW EXECUTE FUNCTION protect_contract_revision();

CREATE TABLE saas_context_facts (
    company_id UUID NOT NULL, user_id UUID NOT NULL, platform VARCHAR(20) NOT NULL,
    account_exists BOOLEAN, license_active BOOLEAN, data_access BOOLEAN, work_scope_assigned BOOLEAN,
    job_function VARCHAR(30) NOT NULL CHECK(job_function IN ('DEV','ANALYST','SALES','OPS','DESIGN','HR','UNKNOWN')),
    observed_at TIMESTAMPTZ NOT NULL, source_reference TEXT NOT NULL,
    PRIMARY KEY(company_id,user_id,platform), FOREIGN KEY(user_id,company_id) REFERENCES users(id,company_id),
    CHECK(platform IN ('SNOWFLAKE','DATABRICKS','SALESFORCE','DATADOG','TABLEAU_CLOUD','FIGMA','GITHUB','JIRA','SLACK','NOTION'))
);
ALTER TABLE pricing_revisions ADD UNIQUE(pricing_id,revision,company_id,entitlement_id,entitlement_revision);
ALTER TABLE access_plan_versions ADD FOREIGN KEY(pricing_id,pricing_revision,company_id,entitlement_id,entitlement_revision)
    REFERENCES pricing_revisions(pricing_id,revision,company_id,entitlement_id,entitlement_revision);
-- A run may only point to its own snapshot, never another run's result set.
ALTER TABLE reclaim_snapshots ADD UNIQUE(id,run_id);
ALTER TABLE reclaim_runs ADD FOREIGN KEY(snapshot_id,id) REFERENCES reclaim_snapshots(id,run_id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE departments ADD FOREIGN KEY(head_id,company_id) REFERENCES users(id,company_id);
ALTER TABLE reclaim_scopes ADD CHECK(jsonb_array_length(platforms)>0 AND platforms <@ '["SNOWFLAKE","DATABRICKS","SALESFORCE","DATADOG","TABLEAU_CLOUD","FIGMA","GITHUB","JIRA","SLACK","NOTION"]'::jsonb);
ALTER TABLE reclaim_run_items ADD CHECK(jsonb_typeof(report)='object' AND jsonb_typeof(policy_evidence)='array' AND jsonb_typeof(fact_evidence)='array');
ALTER TABLE reclaim_run_items ADD CHECK(review_required OR (jsonb_array_length(policy_evidence)>0 AND jsonb_array_length(fact_evidence)>0));
ALTER TABLE reclaim_run_items ADD CHECK(candidate_status IS DISTINCT FROM 'PENDING_REVIEW' OR (candidate_reason_code IS NOT NULL AND exclusion_reason_code IS NULL));
ALTER TABLE reclaim_run_items ADD CHECK(candidate_status IS DISTINCT FROM 'RETAINED' OR (exclusion_reason_code IS NOT NULL AND exclusion_reason_code='RETENTION_APPROVED'));
ALTER TABLE reclaim_run_items ADD CHECK(candidate_status IS DISTINCT FROM 'EXCLUDED' OR (exclusion_reason_code IS NOT NULL AND exclusion_reason_code IN ('ACTIVE_OTHER_TF','USAGE_RESUMED')));

-- Explicitly scoped mock scans: a scenario never accidentally scans UNKNOWN fixtures from another case.
ALTER TABLE reclaim_scopes ADD COLUMN selection_mode VARCHAR(20) NOT NULL DEFAULT 'DEPARTMENT'
    CHECK(selection_mode IN ('DEPARTMENT','ASSIGNMENTS'));
CREATE TABLE reclaim_scope_assignments (
    scope_id UUID NOT NULL, company_id UUID NOT NULL, assignment_id UUID NOT NULL,
    PRIMARY KEY(scope_id,assignment_id),
    FOREIGN KEY(scope_id,company_id) REFERENCES reclaim_scopes(id,company_id),
    FOREIGN KEY(assignment_id,company_id) REFERENCES access_assignments(id,company_id)
);
