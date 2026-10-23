-- Current candidate lifecycle supports human-confirmed revocation.
-- Existing scan report JSON and immutable snapshots keep their original decisions.
ALTER TABLE reclaim_targets DROP CONSTRAINT reclaim_targets_candidate_status_check;
ALTER TABLE reclaim_targets DROP CONSTRAINT reclaim_targets_check1;
ALTER TABLE reclaim_targets ADD CONSTRAINT reclaim_target_status CHECK(candidate_status IN ('PENDING_REVIEW','RETAINED','EXCLUDED','RECLAIMED'));
ALTER TABLE reclaim_targets ADD CONSTRAINT reclaim_target_reason CHECK(
    (candidate_status IN ('PENDING_REVIEW','RECLAIMED') AND exclusion_reason_code IS NULL)
    OR (candidate_status='RETAINED' AND exclusion_reason_code='RETENTION_APPROVED' AND exclusion_reason_code IS NOT NULL)
    OR (candidate_status='EXCLUDED' AND exclusion_reason_code IN ('ACTIVE_OTHER_TF','USAGE_RESUMED') AND exclusion_reason_code IS NOT NULL)
);
ALTER TABLE reclaim_targets ADD COLUMN reclaimed_at TIMESTAMPTZ;
ALTER TABLE reclaim_targets ADD CONSTRAINT reclaim_target_timestamp CHECK(
    (candidate_status='RECLAIMED')=(reclaimed_at IS NOT NULL)
    AND (reclaimed_at IS NULL OR reclaimed_at=closed_at)
);
ALTER TABLE reclaim_targets ADD UNIQUE(id,episode_id);
ALTER TABLE reclaim_run_items DROP CONSTRAINT reclaim_run_items_candidate_status_check;
ALTER TABLE reclaim_run_items ADD CONSTRAINT reclaim_item_status CHECK(candidate_status IN ('PENDING_REVIEW','RETAINED','EXCLUDED','RECLAIMED'));
ALTER TABLE reclaim_run_items DROP CONSTRAINT reclaim_run_items_action_taken_check;
ALTER TABLE reclaim_run_items ADD CONSTRAINT reclaim_item_action CHECK(action_taken IN ('NONE','REVOKED'));

CREATE TABLE reclaim_execution_receipts (
    id UUID PRIMARY KEY, company_id UUID NOT NULL, assignment_id UUID NOT NULL UNIQUE,
    target_id UUID NOT NULL, episode_id UUID NOT NULL,
    review_run_id UUID NOT NULL, executed_by UUID NOT NULL, executed_at TIMESTAMPTZ NOT NULL,
    reason TEXT NOT NULL CHECK(length(btrim(reason)) BETWEEN 1 AND 2000),
    client_request_key VARCHAR(128) NOT NULL CHECK(length(btrim(client_request_key))>0),
    request_hash CHAR(64) NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
    verification_ok BOOLEAN NOT NULL CHECK(verification_ok), result JSONB NOT NULL,
    UNIQUE(company_id,executed_by,client_request_key),
    FOREIGN KEY(target_id,assignment_id,company_id) REFERENCES reclaim_targets(id,assignment_id,company_id),
    FOREIGN KEY(target_id,episode_id) REFERENCES reclaim_targets(id,episode_id),
    FOREIGN KEY(review_run_id,company_id) REFERENCES reclaim_runs(id,company_id),
    FOREIGN KEY(executed_by,company_id) REFERENCES users(id,company_id),
    CHECK(result @> '{"schema_version":2,"verification_ok":true,"assignment_status_after":"INACTIVE","provider_present_after":false}'::jsonb)
);
CREATE TRIGGER immutable_reclaim_execution_receipt BEFORE UPDATE OR DELETE ON reclaim_execution_receipts
    FOR EACH ROW EXECUTE FUNCTION protect_contract_revision();
CREATE INDEX reclaim_execution_history ON reclaim_execution_receipts(company_id,executed_at DESC,id DESC);

-- A delayed scan keeps its frozen report while explaining why it did not notify.
ALTER TABLE reclaim_run_items ADD COLUMN superseded_by_receipt_id UUID REFERENCES reclaim_execution_receipts(id);
