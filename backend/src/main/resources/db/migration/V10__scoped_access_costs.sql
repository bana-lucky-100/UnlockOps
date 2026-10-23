-- Product prices are rates, not the incremental cost of every permission grant.
-- Rules are bound to immutable policy/entitlement revisions; observations are scoped.
CREATE TABLE access_cost_rules (
    company_id UUID NOT NULL,
    entitlement_id UUID NOT NULL,
    entitlement_revision INTEGER NOT NULL,
    policy_id UUID NOT NULL,
    policy_revision INTEGER NOT NULL,
    operation VARCHAR(30) NOT NULL CHECK(operation IN ('PERMISSION_ONLY','PURCHASE_SEAT','USAGE_ALLOCATION')),
    billing_scope VARCHAR(200),
    required_license VARCHAR(100),
    PRIMARY KEY(entitlement_id,entitlement_revision,policy_id,policy_revision),
    FOREIGN KEY(entitlement_id,entitlement_revision,company_id) REFERENCES entitlement_revisions(entitlement_id,revision,company_id),
    FOREIGN KEY(policy_id,policy_revision,company_id) REFERENCES policy_revisions(policy_id,revision,company_id),
    CHECK((billing_scope IS NULL)=(required_license IS NULL)),
    CHECK(billing_scope IS NULL OR (btrim(billing_scope)<>'' AND btrim(required_license)<>''))
);
CREATE TABLE saas_license_facts (
    company_id UUID NOT NULL,
    user_id UUID NOT NULL,
    platform VARCHAR(30) NOT NULL,
    billing_scope VARCHAR(200) NOT NULL CHECK(btrim(billing_scope)<>''),
    license_code VARCHAR(100) NOT NULL CHECK(btrim(license_code)<>''),
    coverage VARCHAR(20) NOT NULL CHECK(coverage IN ('COVERED','NOT_COVERED','UNKNOWN')),
    purchase_required BOOLEAN,
    observed_at TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ,
    source_reference TEXT NOT NULL CHECK(btrim(source_reference)<>''),
    PRIMARY KEY(company_id,user_id,platform,billing_scope,license_code),
    FOREIGN KEY(user_id,company_id) REFERENCES users(id,company_id),
    CHECK(valid_until IS NULL OR valid_until>=observed_at),
    CHECK(coverage='NOT_COVERED' OR purchase_required IS DISTINCT FROM true)
);
CREATE TRIGGER access_cost_rules_immutable BEFORE UPDATE OR DELETE ON access_cost_rules
    FOR EACH ROW EXECUTE FUNCTION protect_contract_revision();
