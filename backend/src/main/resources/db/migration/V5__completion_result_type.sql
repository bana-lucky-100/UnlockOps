-- Workflow state, successful outcome and reason are separate contracts.
ALTER TABLE problems ADD COLUMN result_type VARCHAR(30);

UPDATE problems SET status='DONE', result_type='GUIDANCE'
WHERE status='MANUAL_REVIEW' AND reason_code='RAG_GUIDANCE'
  AND proposal ~ '[^[:space:]]' AND (plan IS NULL OR plan='null'::jsonb)
  AND verification_ok IS NULL;

UPDATE problems SET result_type='ACCESS_VERIFIED' WHERE status='DONE' AND result_type IS NULL;

ALTER TABLE problems ADD CONSTRAINT problems_result_type_check
    CHECK (result_type IN ('GUIDANCE','ACCESS_VERIFIED'));
ALTER TABLE problems ADD CONSTRAINT problems_completion_type_check
    CHECK ((status='DONE') = (result_type IS NOT NULL));
ALTER TABLE problems ADD CONSTRAINT problems_completion_evidence_check CHECK (
    result_type IS NULL
    OR (result_type='GUIDANCE' AND proposal IS NOT NULL AND proposal ~ '[^[:space:]]'
        AND (plan IS NULL OR plan='null'::jsonb) AND verification_ok IS NULL)
    OR (result_type='ACCESS_VERIFIED' AND verification_ok IS TRUE)
);
