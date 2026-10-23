"""Compile the reviewed corpus and an opt-in, atomic baseline revision update. No DB connection."""
import argparse
import hashlib
import json
from pathlib import Path

from unlockops_rag.corpus import parse_corpus, render_corpus

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'data/phase2/policies'
SOURCE = DIRECTORY / 'policy_corpus.md'


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def digest(content):
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


COPY_COLUMNS = {
    'pricing_revisions': ('pricing_id', 'revision,company_id,entitlement_id,entitlement_revision,monthly_amount,currency,cost_basis,source_kind,source_reference,effective_from,effective_until,policy_id,policy_revision'),
    'approval_route_revisions': ('route_id', 'revision,company_id,code,policy_id,policy_revision,steps,extra_step_threshold,currency'),
    'reclaim_rules': ('rule_id', 'revision,company_id,policy_id,policy_revision,code,idle_days,exclude_other_active_tf,exclude_retention'),
}


def company_bundle(company, documents, source_hash):
    flow = ('부서장 → SaaS 담당자' if company == 'A' else
            '팀장 → 부서장 → SaaS 담당자. 예상 월 비용 100.00 USD 이상이면 IT 총괄을 마지막 단계에 추가')
    return f'''# {company}사 Phase 2 정책 묶음 · revision 2

수신 원문: data/phase2/policies/policy_corpus.md
원문 SHA-256: {source_hash}
아래 원문 문서 ID·버전과 DB 정책 묶음 revision은 서로 다른 식별자입니다.

## BASELINE | COMMON | 2 | 적용 범위와 비용 해석

이 묶음은 제공받은 규정·공식 요약을 기존 모의 서비스의 검색 근거로 연결합니다.
공식 요약의 확인일·가격은 제공 문서의 기록이며 이번 반영에서 외부 원문을 재검증한 값이 아닙니다.
실행 금액·통화·승인자는 서버의 구조화된 데이터로 확정합니다. 문서의 정가 예시로 덮어쓰지 않습니다.
현재 가격은 SYNTHETIC_CONTRACT이며 실제 계약가나 검증된 공식 가격으로 표시하지 않습니다.
회수 비용은 예상 검토 금액이며 실제 회수·절감·예산 환입 완료를 의미하지 않습니다.

## BASELINE | FIGMA | 2 | 시연 계약 가격

현재 Figma 모의 계약가는 월 15.00 USD이며 POL-14·FG-OFF-01의 Professional 예시 16달러와 다릅니다.
이 시연의 예산 계산과 보고서 금액은 서버가 반환한 모의 계약 값을 사용합니다.

## FLOW | COMMON | 2 | {company}사 승인 경로

{flow}. 사람의 순차 승인이 모두 끝나야 실행할 수 있습니다.
담당자는 회사·부서·플랫폼의 서버 매핑으로 확인합니다.{' Figma 단계는 지정 Figma 담당자입니다.' if company == 'B' else ''}
본인 승인과 승인자 추측을 금지합니다. 보류 후 재개하면 새 회차에서 다시 승인받습니다.

## BASELINE | COMMON | 2 | 회수 점검의 구현 기준

미사용 기간은 TF 종료 다음 날 00:00(KST)·지급 시각·마지막 사용 시각 중 가장 늦은 시점부터 계산합니다.
다른 TF는 현재 활성 TF를 의미합니다. 유효한 유지 승인은 RETAINED로 관리합니다.
퇴사자 규칙은 TF 종료·미사용 규칙과 별개입니다. 사용 이력·비용 미확인은 0이나 미사용으로 추정하지 않습니다.
스케줄러는 기본 비활성입니다. 점검 완료는 실제 회수 완료를 뜻하지 않습니다.

''' + render_corpus(documents)


def update_sql(company, info, content, baseline):
    co, policy = quote(info['company_id']), quote(info['policy_id'])
    # Fixed revision 2 is intentional: changed input must not silently overwrite an imported revision.
    statements = [f'''DO $policy_import$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM companies WHERE id={co} AND code='P2_{company}' AND is_mock) THEN
    RAISE EXCEPTION 'Seed the expected P2_{company} mock company before importing policies';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM policy_revisions WHERE policy_id={policy} AND company_id={co}
      AND revision=1 AND source_hash={quote(digest(baseline))}) THEN
    RAISE EXCEPTION 'Unexpected baseline policy for P2_{company}';
  END IF;
  IF EXISTS (SELECT 1 FROM policy_revisions WHERE company_id={co} AND (policy_id<>{policy} OR revision>2)) THEN
    RAISE EXCEPTION 'A different policy family or a later revision already exists for P2_{company}';
  END IF;
  INSERT INTO policy_revisions(policy_id,revision,company_id,doc_id,article,source_path,source_hash,content,is_mock)
    VALUES ({policy},2,{co},'P2-{company}-POLICY','POL-01~14 / OFF / FLOW',
      'data/phase2/policies/company-{company.lower()}-policy-v2.md',{quote(digest(content))},{quote(content)},true)
    ON CONFLICT (policy_id,revision) DO NOTHING;
  IF NOT EXISTS (SELECT 1 FROM policy_revisions WHERE policy_id={policy} AND revision=2 AND company_id={co}
      AND doc_id='P2-{company}-POLICY' AND source_hash={quote(digest(content))} AND content={quote(content)}) THEN
    RAISE EXCEPTION 'Policy revision 2 already contains different content for P2_{company}';
  END IF;''']
    for table, (key, fields) in COPY_COLUMNS.items():
        expected = 12 if table == 'pricing_revisions' else 1 if table == 'approval_route_revisions' else 2
        source = f"company_id={co} AND policy_id={policy} AND policy_revision=1 AND revision=1"
        columns = [key, *fields.split(',')]
        values = ['2' if name in {'revision', 'policy_revision'} else name for name in columns]
        statements.append(f'''
  IF (SELECT count(*) FROM {table} WHERE {source})<>{expected}
     OR EXISTS (SELECT 1 FROM {table} WHERE company_id={co} AND (revision>2 OR policy_id<>{policy})) THEN
    RAISE EXCEPTION 'Unexpected baseline or later revisions in {table} for P2_{company}';
  END IF;
  INSERT INTO {table}({','.join(columns)}) SELECT {','.join(values)} FROM {table} WHERE {source}
    ON CONFLICT ({key},revision) DO NOTHING;
  IF EXISTS (
    SELECT to_jsonb(old) || '{{"revision":2,"policy_revision":2}}'::jsonb FROM {table} old WHERE {source}
    EXCEPT SELECT to_jsonb(new) FROM {table} new WHERE company_id={co} AND revision=2
  ) THEN
    RAISE EXCEPTION 'Revision 2 bindings differ in {table} for P2_{company}';
  END IF;''')
    statements.append('END $policy_import$;')
    return '\n'.join(statements)


def outputs():
    raw = SOURCE.read_text(encoding='utf-8')
    documents = parse_corpus(raw)
    required = {f'POL-{i:02}' for i in range(1, 15)}
    if not required.issubset({doc.doc_id for doc in documents}):
        raise ValueError('The imported corpus must contain POL-01 through POL-14')
    catalog = json.loads((ROOT / 'data/phase2/catalog.json').read_text())
    files = {}
    sql = ['-- Generated by scripts/import_phase2_policy.py. Apply after V7 + data/phase2/seed.sql.',
           '-- Existing prices/routes/rules retain their values; only their revision bindings advance.',
           'BEGIN;', 'SET LOCAL lock_timeout = \'5s\';',
           'LOCK TABLE policy_revisions, pricing_revisions, approval_route_revisions, reclaim_rules IN SHARE ROW EXCLUSIVE MODE;']
    for company, info in catalog['companies'].items():
        content = company_bundle(company, documents, digest(raw))
        if '$policy_import$' in content:
            raise ValueError('Reserved SQL delimiter in source')
        files[DIRECTORY / f'company-{company.lower()}-policy-v2.md'] = content
        baseline = (ROOT / f'data/phase2/company-{company.lower()}-policy.md').read_text()
        sql.append(update_sql(company, info, content, baseline))
    sql.append('COMMIT;')
    files[DIRECTORY / 'apply.sql'] = '\n\n'.join(sql) + '\n'
    return files


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify generated files without changing them')
    args = parser.parse_args()
    for path, content in outputs().items():
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f'Stale generated policy: {path}')
        else:
            path.write_text(content, encoding='utf-8')
    print('Phase 2 policy files verified' if args.check else 'Phase 2 policy bundles and opt-in SQL generated')
