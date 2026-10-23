-- Keep original migrations and snapshots immutable; adapt run outcomes to scenario v4.
ALTER TABLE saas_context_facts ADD COLUMN job_run_as_principal VARCHAR(200);
ALTER TABLE saas_context_facts ADD COLUMN job_run_as_data_access BOOLEAN;
ALTER TABLE saas_context_facts ADD COLUMN license_plan VARCHAR(100);
DO $$
DECLARE c record;
BEGIN
  FOR c IN SELECT conname FROM pg_constraint
    WHERE conrelid='reclaim_runs'::regclass AND contype='c'
      AND (pg_get_constraintdef(oid) LIKE '%MANUAL_REVIEW%'
        OR pg_get_constraintdef(oid) LIKE '%NO_NEW_CANDIDATES%')
  LOOP EXECUTE format('ALTER TABLE reclaim_runs DROP CONSTRAINT %I',c.conname); END LOOP;
END $$;

UPDATE reclaim_runs SET
  status=CASE WHEN scan_complete AND pending_notification_count=0 THEN 'DONE' ELSE 'FAILED' END,
  reason_code=CASE WHEN pending_notification_count>0 THEN 'NOTIFICATION_FAILED'
    WHEN scan_complete THEN CASE WHEN needs_review_count>0 OR new_candidate_count>0 THEN 'SCAN_COMPLETED' ELSE 'NO_NEW_CANDIDATES' END
    ELSE 'SCAN_FAILED' END,
  message=CASE WHEN scan_complete AND pending_notification_count=0 THEN '점검 완료. 정보가 부족한 항목은 추가 확인 목록에서 확인하세요.'
    ELSE '전체 점검 또는 필수 알림을 완료하지 못했습니다.' END,
  needs_review_count=(SELECT count(*) FROM reclaim_run_items i WHERE i.run_id=reclaim_runs.id AND i.review_required)
WHERE status='MANUAL_REVIEW';

ALTER TABLE reclaim_runs ADD CONSTRAINT reclaim_v4_status CHECK
  (status IN ('RECEIVED','DIAGNOSING','EXECUTING','DONE','FAILED'));
ALTER TABLE reclaim_runs ADD CONSTRAINT reclaim_v4_done CHECK
  (status<>'DONE' OR (scan_complete AND pending_notification_count=0 AND reason_code IN ('SCAN_COMPLETED','NO_NEW_CANDIDATES')));
ALTER TABLE reclaim_runs ADD CONSTRAINT reclaim_v4_empty CHECK
  (reason_code IS DISTINCT FROM 'NO_NEW_CANDIDATES' OR (status='DONE' AND new_candidate_count=0 AND needs_review_count=0));
