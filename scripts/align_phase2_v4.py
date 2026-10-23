"""Append scenario-v4 policy/price/route/rule revision 3 without rewriting baseline revisions."""
import argparse
import json
from pathlib import Path
from import_phase2_policy import ROOT, DIRECTORY, quote, digest, COPY_COLUMNS


def outputs():
    catalog=json.loads((ROOT/'data/phase2/catalog.json').read_text())
    sql=['-- Apply after V8, baseline seed.sql and policies/apply.sql (revision 2).',
         'BEGIN;', "SET LOCAL lock_timeout='5s';",
         'LOCK TABLE policy_revisions, pricing_revisions, approval_route_revisions, reclaim_rules IN SHARE ROW EXCLUSIVE MODE;']
    files={}
    for company,info in catalog['companies'].items():
        co,policy=quote(info['company_id']),quote(info['policy_id'])
        old=(DIRECTORY/f'company-{company.lower()}-policy-v2.md').read_text()
        content=old.replace('revision 2','revision 3').replace(' | 2 |',' | 3 |')
        content=content.replace('현재 Figma 모의 계약가는 월 15.00 USD이며 POL-14·FG-OFF-01의 Professional 예시 16달러와 다릅니다.',
            'v4 Figma 시연 단가는 Professional Full 월 16.00 USD입니다. 잔여 예산 100.00 USD에서 예상 예산은 84.00 USD입니다.')
        content=content.replace('현재 가격은 SYNTHETIC_CONTRACT이며 실제 계약가나 검증된 공식 가격으로 표시하지 않습니다.',
            '가격의 PUBLIC_LIST_PRICE는 제공 문서의 정가 기록이며 외부 원문을 재검증한 값이 아닙니다. 사용량과 계약 가정값은 SYNTHETIC_CONTRACT로 구분합니다. Notion은 Business 플랜 월 20달러, Tableau는 Enterprise Explorer 월 70달러입니다.')
        content=content.replace('스케줄러는 기본 비활성입니다.',
            '개별 정보 부족은 후보 알림 없이 추가 확인 목록에 남기고 점검을 완료합니다. 전체 조회 실패는 FAILED / SCAN_FAILED입니다. 스케줄러는 기본 비활성이며 수동 시연 후 명시적으로 활성화합니다.')
        files[DIRECTORY/f'company-{company.lower()}-policy-v3.md']=content
        sql.append(f'''DO $v4$
BEGIN
  IF NOT EXISTS(SELECT 1 FROM companies WHERE id={co} AND code='P2_{company}' AND is_mock)
    OR NOT EXISTS(SELECT 1 FROM policy_revisions WHERE policy_id={policy} AND revision=2 AND source_hash={quote(digest(old))})
    OR EXISTS(SELECT 1 FROM policy_revisions WHERE company_id={co} AND (policy_id<>{policy} OR revision>3)) THEN
    RAISE EXCEPTION 'Unexpected source policy: import revision 2 before scenario v4';
  END IF;
  INSERT INTO policy_revisions(policy_id,revision,company_id,doc_id,article,source_path,source_hash,content,is_mock)
    VALUES({policy},3,{co},'P2-{company}-POLICY','POL-01~14 / OFF / FLOW',
      'data/phase2/policies/company-{company.lower()}-policy-v3.md',{quote(digest(content))},{quote(content)},true)
    ON CONFLICT(policy_id,revision) DO NOTHING;
  IF NOT EXISTS(SELECT 1 FROM policy_revisions WHERE policy_id={policy} AND revision=3 AND source_hash={quote(digest(content))} AND content={quote(content)}) THEN
    RAISE EXCEPTION 'Conflicting scenario v4 revision';
  END IF;''')
        items={i['platform']:i for i in catalog['catalog'] if i['company']==company}
        for table,(key,fields) in COPY_COLUMNS.items():
            columns=[key,*fields.split(',')]
            expressions={c:('3' if c in {'revision','policy_revision'} else c) for c in columns}
            expected=12 if table=='pricing_revisions' else 1 if table=='approval_route_revisions' else 2
            if table=='pricing_revisions':
                expressions['monthly_amount']=f"CASE WHEN entitlement_id={quote(items['FIGMA']['entitlement_id'])} THEN 16.00 ELSE monthly_amount END"
                ids=','.join(quote(items[p]['entitlement_id']) for p in ['FIGMA','GITHUB','NOTION','TABLEAU_CLOUD'])
                expressions['source_kind']=f"CASE WHEN entitlement_id IN ({ids}) THEN 'PUBLIC_LIST_PRICE' ELSE source_kind END"
                expressions['source_reference']="'scenario-v4 / data/phase2/policies/policy_corpus.md; supplied reference, demo usage assumptions'"
            selected=','.join(f'{expressions[c]} AS {c}' for c in columns)
            source=f'company_id={co} AND policy_id={policy} AND revision=2 AND policy_revision=2'
            sql.append(f'''
  IF (SELECT count(*) FROM {table} WHERE {source})<>{expected}
    OR EXISTS(SELECT 1 FROM {table} WHERE company_id={co} AND (revision>3 OR policy_id<>{policy})) THEN
    RAISE EXCEPTION 'Unexpected source or later revision in {table}';
  END IF;
  INSERT INTO {table}({','.join(columns)}) SELECT {selected} FROM {table} WHERE {source}
    ON CONFLICT({key},revision) DO NOTHING;
  IF EXISTS(SELECT to_jsonb(expected) FROM (SELECT {selected} FROM {table} WHERE {source}) expected
    EXCEPT SELECT to_jsonb(actual) FROM {table} actual WHERE company_id={co} AND revision=3) THEN
    RAISE EXCEPTION 'Conflicting v4 bindings in {table}';
  END IF;''')
        sql.append(f'''
  -- Explicit synthetic facts for the v4 demo, never inferred from real provider data.
  UPDATE saas_context_facts SET job_run_as_principal='scenario-v4-demo-service-principal',job_run_as_data_access=true
    WHERE company_id={co} AND platform='DATABRICKS' AND source_reference LIKE 'SYNTHETIC:%'
      AND job_run_as_principal IS NULL AND job_run_as_data_access IS NULL;
  UPDATE saas_context_facts SET license_plan=CASE platform WHEN 'NOTION' THEN 'Business'
    WHEN 'FIGMA' THEN 'Professional Full' WHEN 'TABLEAU_CLOUD' THEN 'Enterprise Explorer' ELSE license_plan END
    WHERE company_id={co} AND source_reference LIKE 'SYNTHETIC:%' AND license_plan IS NULL;
  UPDATE resources SET access_scope='TF',tf_id={quote(info['active_tf_id'])}
    WHERE company_id={co} AND id IN ({','.join(quote(items[p]['resource_id']) for p in ['FIGMA','DATABRICKS','NOTION','SLACK'])})
      AND access_scope IN ('GENERAL','SEAT') AND tf_id IS NULL;
  -- Refresh only explicit synthetic observations for this demo installation.
  UPDATE assignment_usage SET observed_at=now()
    WHERE company_id={co} AND source_reference LIKE 'SYNTHETIC:%' AND observation_status='KNOWN';
END $v4$;''')
    sql.append('COMMIT;')
    files[DIRECTORY/'apply-v4.sql']='\n'.join(sql)+'\n'
    prompts={
        'E-01':'개발 업무에 필요한 GitHub Copilot 좌석을 신청합니다.',
        'E-02':'결제 개편 TF의 Notion Business 문서 편집 권한을 신청합니다.',
        'E-03':'Slack 대상 채널 참여 권한을 신청합니다.',
        'E-04':'Jira PAY 프로젝트 작업 권한을 신청합니다.',
        'E-05':'결제 개편 TF의 Notion 문서 편집 권한을 신청합니다.',
        'P-01':'추천 모델 분석용 Snowflake 웨어하우스 USAGE 권한이 필요합니다.',
        'P-02':'Databricks 추천 모델 프로젝트의 노트북 편집 권한과 지정 작업 실행 권한을 신청합니다.',
        'P-03':'Salesforce 담당 고객과 영업 기회 조회 및 수정 권한을 신청합니다.',
        'P-04':'Datadog 결제 서비스 로그와 대시보드 조회 권한을 신청합니다.',
        'P-05':'Tableau Cloud 매출 프로젝트 대시보드 편집 권한과 게시 권한을 신청합니다.',
        'P-06':'Figma 결제 개편 TF 파일 편집 권한과 Full 좌석을 신청합니다.',
        'B-01':'GitHub Copilot 좌석을 신청합니다.',
        'B-02':'GitHub 결제 개편 TF 저장소 Admin 권한을 신청하지만 목적은 코드 열람뿐입니다.',
        'B-03':'GitHub Copilot 사용에 필요한 권한을 신청합니다.',
        'B-04':'결제 개편 TF 비공개 Slack 채널 참여 권한을 신청합니다.',
        'B-05':'DB 배포 권한을 신청합니다.',
    }
    evidence={
        'E-01':[['POL-06','제1조'],['POL-06','제2조'],['GH-OFF-03']],
        'E-02':[['POL-06','제2조'],['POL-06','제3조']], 'E-03':[['POL-06','제4조']],
        'B-01':[['POL-06','제1조']], 'B-02':[['POL-01','제2조'],['POL-03','제4조'],['POL-07','제1조']],
    }
    for n,official in enumerate(['SN','DB','SF','DD','TB','FG'],1):
        evidence[f'P-0{n}']=[[f'POL-{n+8:02}','제2조'],[f'{official}-OFF-01']]
    cases=[]
    for original in catalog['scenarios']:
        case={**original,'input_text':prompts.get(original['id'],''),'expected_evidence':evidence.get(original['id'],[])}
        if case['id'].startswith('R-') and case['id']!='R-04':case['expected_evidence']=[['POL-06','제5조']]
        cases.append(case)
    files[ROOT/'data/phase2/scenarios-v4.json']=json.dumps({'scenario_version':'v4','policy_revision':3,'figma_monthly_amount':'16.00','scenarios':cases},ensure_ascii=False,indent=2)+'\n'
    return files


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    for path,content in outputs().items():
        if args.check:
            if not path.exists() or path.read_text()!=content:raise SystemExit(f'Stale v4 file: {path}')
        else:path.write_text(content)
    print('Scenario v4 revisions verified' if args.check else 'Scenario v4 revisions generated')
