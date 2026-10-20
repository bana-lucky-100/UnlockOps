-- Preserve applied V1/V2 checksums and all raw audit events.
ALTER TABLE problems DROP CONSTRAINT problems_status_check;

UPDATE problems
SET status='REJECTED',
    reason_code=CASE WHEN reason_code='INSUFFICIENT_BUDGET' OR reason_code IS NULL
                     THEN 'BUDGET_INSUFFICIENT' ELSE reason_code END
WHERE status='ON_HOLD';

UPDATE problems SET reason_code='BUDGET_INSUFFICIENT'
WHERE reason_code='INSUFFICIENT_BUDGET';

ALTER TABLE problems ADD CONSTRAINT problems_status_check CHECK(status IN (
    'RECEIVED','DIAGNOSING','WAITING_APPROVAL','EXECUTING','DONE',
    'REJECTED','MANUAL_REVIEW','FAILED'));

CREATE INDEX problems_requester_created ON problems(requester_id,created_at DESC);
