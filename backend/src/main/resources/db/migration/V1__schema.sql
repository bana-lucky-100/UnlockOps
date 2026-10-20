CREATE TABLE departments (
    id UUID PRIMARY KEY,
    code VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL UNIQUE,
    head_id UUID
);
CREATE TABLE users (
    id UUID PRIMARY KEY,
    employee_no VARCHAR(20) NOT NULL UNIQUE,
    login_id VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    password_hash TEXT NOT NULL DEFAULT '',
    role VARCHAR(20) NOT NULL CHECK (role IN ('REQUESTER','APPROVER')),
    department_id UUID NOT NULL REFERENCES departments(id),
    job_grade VARCHAR(50) NOT NULL CHECK (job_grade IN ('사원','대리','과장','차장','부장')),
    job_family VARCHAR(20) NOT NULL CHECK (job_family IN ('DEV','NON_DEV')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE departments ADD CONSTRAINT department_head_fk FOREIGN KEY(head_id) REFERENCES users(id);
CREATE TABLE tfs (
    id UUID PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    leader_id UUID NOT NULL REFERENCES users(id),
    starts_on DATE NOT NULL,
    ends_on DATE,
    CHECK (ends_on IS NULL OR ends_on >= starts_on)
);
CREATE TABLE tf_members (
    tf_id UUID NOT NULL REFERENCES tfs(id),
    user_id UUID NOT NULL REFERENCES users(id),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(tf_id,user_id)
);
CREATE TABLE resources (
    id UUID PRIMARY KEY,
    platform VARCHAR(20) NOT NULL CHECK(platform IN ('GITHUB','JIRA','SLACK','NOTION')),
    external_id VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    aliases JSONB NOT NULL DEFAULT '[]',
    access_scope VARCHAR(30) NOT NULL CHECK(access_scope IN ('GENERAL','TF','DEPARTMENT','CONFIDENTIAL','SEAT')),
    owner_department_id UUID REFERENCES departments(id),
    tf_id UUID REFERENCES tfs(id),
    security_grade VARCHAR(20) CHECK(security_grade IN ('GENERAL','INTERNAL','CONFIDENTIAL')),
    designated_department_id UUID REFERENCES departments(id),
    UNIQUE(platform,external_id),
    CHECK ((access_scope='TF') = (tf_id IS NOT NULL)),
    CHECK (security_grade IS DISTINCT FROM 'CONFIDENTIAL' OR designated_department_id IS NOT NULL)
);
CREATE TABLE permissions (
    user_id UUID NOT NULL REFERENCES users(id),
    resource_id UUID NOT NULL REFERENCES resources(id),
    saas_role VARCHAR(50) NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(user_id,resource_id)
);
CREATE TABLE github_teams (
    id VARCHAR(200) PRIMARY KEY,
    resource_id UUID NOT NULL REFERENCES resources(id),
    saas_role VARCHAR(20) NOT NULL CHECK(saas_role IN ('Read','Write')),
    UNIQUE(resource_id,saas_role)
);
CREATE TABLE github_team_members (
    team_id VARCHAR(200) NOT NULL REFERENCES github_teams(id),
    user_id UUID NOT NULL REFERENCES users(id),
    PRIMARY KEY(team_id,user_id)
);
CREATE TABLE jira_role_permissions (
    resource_id UUID NOT NULL REFERENCES resources(id),
    saas_role VARCHAR(50) NOT NULL CHECK(saas_role IN ('Viewer','Developer')),
    can_browse BOOLEAN NOT NULL,
    PRIMARY KEY(resource_id,saas_role)
);
CREATE TABLE department_budgets (
    department_id UUID PRIMARY KEY REFERENCES departments(id),
    remaining_monthly_amount NUMERIC(12,2) NOT NULL CHECK(remaining_monthly_amount >= 0),
    unit_monthly_price NUMERIC(12,2) NOT NULL CHECK(unit_monthly_price > 0),
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE problems (
    id UUID PRIMARY KEY,
    requester_id UUID NOT NULL REFERENCES users(id),
    approver_id UUID REFERENCES users(id),
    platform VARCHAR(20) NOT NULL CHECK(platform IN ('GITHUB','JIRA','SLACK','NOTION')),
    contents TEXT NOT NULL CHECK(char_length(contents) BETWEEN 1 AND 5000),
    status VARCHAR(30) NOT NULL DEFAULT 'RECEIVED' CHECK(status IN (
      'RECEIVED','DIAGNOSING','WAITING_APPROVAL','EXECUTING','DONE',
      'REJECTED','ON_HOLD','MANUAL_REVIEW','FAILED')),
    diagnosis TEXT,
    proposal TEXT,
    resource_id UUID REFERENCES resources(id),
    requested_role VARCHAR(100),
    evidence JSONB NOT NULL DEFAULT '[]',
    reason_code VARCHAR(100),
    decision_reason TEXT,
    decision_source VARCHAR(20) CHECK(decision_source IN ('AGENT','HUMAN')),
    decided_by UUID REFERENCES users(id),
    decided_at TIMESTAMPTZ,
    thread_id VARCHAR(100) NOT NULL UNIQUE,
    idempotency_key VARCHAR(150) UNIQUE,
    plan JSONB,
    plan_hash CHAR(64),
    approved_plan_hash CHAR(64),
    verification_ok BOOLEAN,
    agent_mode VARCHAR(10),
    simulate_jira_failure BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (decided_by IS NULL OR decided_by <> requester_id)
);
CREATE INDEX problems_approver_created ON problems(approver_id,created_at DESC);
CREATE TABLE problem_events (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    problem_id UUID NOT NULL REFERENCES problems(id),
    kind VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE outbox (
    event_id UUID PRIMARY KEY,
    routing_key VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX outbox_pending ON outbox(created_at) WHERE published_at IS NULL;
CREATE TABLE inbox_events (
    event_id UUID PRIMARY KEY,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE grant_receipts (
    idempotency_key VARCHAR(150) PRIMARY KEY,
    problem_id UUID NOT NULL UNIQUE REFERENCES problems(id),
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
