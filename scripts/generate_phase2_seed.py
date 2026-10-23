import json, hashlib
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
root=Path(__file__).resolve().parents[1]
def uid(key): return str(uuid5(NAMESPACE_URL,'unlockops:phase2:'+key))
def q(v):
    if v is None: return 'NULL'
    if isinstance(v,bool): return 'TRUE' if v else 'FALSE'
    if isinstance(v,(dict,list)): v=json.dumps(v,ensure_ascii=False,separators=(',',':'))
    return "'"+str(v).replace("'","''")+"'"
rows=[]
name_updates=[]
def insert(table,**values):
    rows.append('INSERT INTO '+table+' ('+','.join(values)+') VALUES ('+','.join(q(v) for v in values.values())+') ON CONFLICT DO NOTHING;')

def insert_named(table,**values):
    insert(table,**values)
    # Upgrade only original demo labels; preserve names edited by the user.
    identity={'id':values['id']}
    if table=='companies':
        identity.update(code=values['code'],is_mock=True)
    else:
        identity['company_id']=values['company_id']
    identity['name']='Phase 2 '+values['name']
    name_updates.append('UPDATE '+table+' SET name='+q(values['name'])+' WHERE '
        +' AND '.join(key+'='+q(value) for key,value in identity.items())+';')

def insert_notified_reclaim_history(company_code, company, assignment, scope, platform):
    """R-04 is a synthetic past scan, including the report its delivered alert opens."""
    case='R-04'
    as_of='2026-10-21T09:00:00+09:00'
    delivered='2026-10-21T09:00:01+09:00'
    run=uid(case+'-run');snapshot=uid(case+'-snapshot')
    target=uid(case+'-target');episode=uid(case+'-episode')
    company_id=company['company_id']
    policy_path='data/phase2/company-'+company_code.lower()+'-policy.md'
    content=(root/policy_path).read_text()
    source_hash=hashlib.sha256(content.encode()).hexdigest()
    article='POL-06 제5조 — 회수 후보'
    excerpt=('## '+article+'\n'+content.split('## '+article+'\n',1)[1].split('\n## ',1)[0]).strip()
    policy={'policy_id':company['policy_id'],'revision':1,'company_id':company_id,
        'doc_id':'P2-'+company_code+'-POLICY','article':'POL-06 제1~5조 / FLOW 제7조',
        'source_path':policy_path,'source_hash':source_hash,'content':content,'is_mock':True}
    rules=[{'rule_id':uid(company_code+'-'+code),'revision':1,'company_id':company_id,
        'policy_id':company['policy_id'],'policy_revision':1,'code':code,'idle_days':idle,
        'exclude_other_active_tf':code!='EMPLOYEE_LEFT','exclude_retention':code!='EMPLOYEE_LEFT'}
        for code,idle in [('TF_ENDED_UNUSED_30D',30),('EMPLOYEE_LEFT',None)]]
    evidence=[{'doc_id':policy['doc_id'],'article':article,'version':'1','source_hash':source_hash,'text':excerpt}]
    cost={'status':'ESTIMATED','monthly_amount':'19.00','currency':'USD','basis':'SYNTHETIC_CONTRACT'}
    report={'assignment_id':assignment,'target_id':target,'episode_id':episode,'platform':platform,
        'candidate_status':'PENDING_REVIEW','candidate_reason_code':'TF_ENDED_UNUSED_30D',
        'exclusion_reason_code':None,'skip_reason_code':None,'review_required':False,
        'notified_at':delivered,'read_at':None,'action_taken':'NONE','generation_mode':'template',
        'explanation':'합성 과거 점검: TF 종료 후 연속 30일 미사용 조건을 충족해 담당자 검토 후보로 알렸습니다. 실제 권한은 회수하지 않았습니다.',
        'policy_evidence':evidence,'fact_evidence':[{'source':'reclaim_snapshot_items','record_id':assignment,'observed_at':as_of}],
        'cost_impact':cost}
    facts={'assignment_id':assignment,'company_id':company_id,'user_id':uid(case+'-user'),
        'department_id':company['department_id'],'employee_name':'회수 R-04',
        'resource_name':'Phase 2 '+company_code+' '+platform,'platform':platform,
        'entitlement_id':uid(company_code+'-'+platform+'-entitlement'),'employment_status':'ACTIVE',
        'origin_tf_id':company['ended_tf_id'],'granted_at':'2026-08-01T00:00:00+09:00',
        'tf_ends_on':'2026-09-20','last_used_at':'2026-09-05T09:00:00+09:00',
        'observation_status':'KNOWN','observed_at':as_of,'other_active_tf':False,'retention':False,
        'price':{'monthly_amount':19,'currency':'USD','source_kind':'SYNTHETIC_CONTRACT'}}
    # Freeze the original pre-notification facts. Never reconstruct past evidence from today's state.
    candidate={**report,'target_id':None,'episode_id':None,'notified_at':None}
    insert('reclaim_runs',id=run,company_id=company_id,scope_id=scope,trigger='DAILY_SCHEDULE',
        scheduled_for=as_of,schedule_date='2026-10-21',request_hash=hashlib.sha256(scope.encode()).hexdigest(),
        status='DONE',reason_code='SCAN_COMPLETED',message='합성 과거 점검: 신규 후보 1건 · 월 19.00 USD. 실제 회수 없음.',
        snapshot_id=snapshot,as_of=as_of,scan_complete=True,new_candidate_count=1,
        created_at=as_of,updated_at=delivered)
    insert('reclaim_snapshots',id=snapshot,company_id=company_id,run_id=run,as_of=as_of,
        policy_id=company['policy_id'],policy_revision=1,expected_count=1,
        context={'policy':policy,'rules':rules,'policy_hash':source_hash})
    insert('reclaim_snapshot_items',snapshot_id=snapshot,company_id=company_id,ordinal=1,
        assignment_id=assignment,facts={'facts':facts,'candidate':candidate})
    insert('reclaim_targets',id=target,company_id=company_id,assignment_id=assignment,episode_id=episode,
        rule_code='TF_ENDED_UNUSED_30D',candidate_status='PENDING_REVIEW',opened_at=as_of,notified_at=delivered)
    insert('reclaim_run_items',run_id=run,company_id=company_id,assignment_id=assignment,target_id=target,
        candidate_status='PENDING_REVIEW',candidate_reason_code='TF_ENDED_UNUSED_30D',review_required=False,
        report=report,policy_evidence=evidence,fact_evidence=report['fact_evidence'],generation_mode='template',
        cost_status='ESTIMATED',monthly_amount='19.00',currency='USD')
    insert('reclaim_notifications',id=uid(case+'-notification'),company_id=company_id,target_id=target,
        recipient_id=company['users']['operator'],channel='IN_APP',delivery_status='DELIVERED',delivered_at=delivered,attempts=1)
platforms=['SNOWFLAKE','DATABRICKS','SALESFORCE','DATADOG','TABLEAU_CLOUD','FIGMA','GITHUB','JIRA','SLACK','NOTION']
items=[('SNOWFLAKE','WAREHOUSE','ANALYST','ROLE','120.00','USAGE_ESTIMATE'),('DATABRICKS','WORKSPACE','NOTEBOOK_JOB_USER','PERMISSION_SET','80.00','USAGE_ESTIMATE'),('SALESFORCE','CUSTOMER_SCOPE','ASSIGNED_CUSTOMER_EDITOR','PERMISSION_SET','0.00','NO_ADDITIONAL_COST'),('DATADOG','SERVICE','SERVICE_VIEWER','ROLE','0.00','NO_ADDITIONAL_COST'),('TABLEAU_CLOUD','PROJECT','PROJECT_PUBLISHER','ROLE','70.00','SEAT_MONTHLY'),('FIGMA','PROJECT','EDITOR_SEAT','SEAT','15.00','SEAT_MONTHLY'),('GITHUB','SEAT','COPILOT_SEAT','SEAT','19.00','SEAT_MONTHLY'),('JIRA','PROJECT','DEVELOPER','ROLE','0.00','NO_ADDITIONAL_COST'),('SLACK','CHANNEL','MEMBER','MEMBERSHIP','0.00','NO_ADDITIONAL_COST'),('NOTION','PAGE','EDITOR','ROLE','20.00','SEAT_MONTHLY')]
manifest={'schema_version':2,'dataset_id':'phase2-baseline-v1','is_mock':True,'as_of':'2026-10-22T09:00:00+09:00','timezone':'Asia/Seoul','companies':{},'catalog':[],'reclaim_fixtures':{},'scenarios':[]}
for co in ['A','B']:
    company=uid('company-'+co); dept=uid(co+'-department'); policy=uid(co+'-policy'); route=uid(co+'-route')
    insert_named('companies',id=company,code='P2_'+co,name=co+'사 (mock)',timezone='Asia/Seoul',is_mock=True)
    insert_named('departments',id=dept,company_id=company,code='P2_'+co+'_DEV',name=co+'사 업무팀')
    names={'requester':'김개발','team_lead':'박팀장','head':'윤부장','operator':'송운영','it_head':'최총괄','figma_operator':'이디자인'}
    users={}
    for i,(role,name) in enumerate(names.items()):
        user=uid(co+'-'+role);users[role]=user
        insert('users',id=user,company_id=company,employee_no='P2-'+co+'-'+str(i),login_id='p2_'+co.lower()+'_'+role,email='p2_'+co.lower()+'_'+role+'@example.test',name=name+'('+co+')',role='REQUESTER' if role=='requester' else 'APPROVER',department_id=dept,job_grade='사원' if role=='requester' else '부장',job_family='DEV')
    rows.append('UPDATE departments SET head_id='+q(users['head'])+' WHERE id='+q(dept)+' AND head_id IS NULL;')
    insert('department_budgets',department_id=dept,remaining_monthly_amount='500.00' if co=='A' else '100.00',unit_monthly_price='19.00',currency='USD')
    text=f'''# {co}사 Phase 2 임시 규정 · baseline-v1\n\n교육용 합성 데이터이며 실제 회사 규정·SaaS 공식 역할·가격이 아니다.\n\n## POL-06 제1조 — 신청 대상\n개발/분석 업무 권한은 해당 업무 담당자, Salesforce는 담당 고객 배정 직원, Datadog은 서비스 운영 담당자, Figma는 TF 디자인 담당자에게 제안한다. 실제 직군·배정은 서버 사실로 확인한다.\n## POL-06 제2조 — 비용\n서버의 구조화된 가격표와 잔여 예산을 사용한다. 사용량 기반 금액은 예상 예산 배정이며 실제 청구액이 아니다.\n## POL-06 제3조 — 예산 부족\n예산 부족이면 ON_HOLD로 보류한다. 재개 때 최신 정책·예산·승인 계획을 다시 검토한다.\n## POL-06 제4조 — 중복\n이미 필요한 권한이 있으면 변경 없이 안내한다. 기존 유료 좌석을 추가 구매하려는 요청은 거절한다.\n## POL-06 제5조 — 회수 후보\n프로젝트 지급 좌석은 TF 종료 후 연속 미사용 30일 이상이고 다른 활성 TF 이용 및 유효 유지 승인이 없으면 검토 후보로 제안한다. 종료 후 미사용 시작은 TF 종료 시각·마지막 사용 시각·할당 시각 중 가장 늦은 시각이다. 미조회는 미사용이 아니다. 퇴사자 유료 좌석도 별도 검토 후보로 제안한다. 비용 미확인은 UNKNOWN으로 남기며 실제 회수·예산 환입은 하지 않는다.\n## FLOW 제7조 — 승인 경로\n'''+('부서장 → IT 권한 담당자의 순서로 승인한다.\n' if co=='A' else '팀장 → 부서장 → SaaS 담당자의 순서로 승인한다. 예상 월 비용 100.00 USD 이상이면 IT 총괄을 마지막에 추가한다. 다른 통화는 임의 환산하지 않고 수동 검토한다.\n')+'''본인 승인과 임의 승인자 추측은 금지한다. 담당자 식별은 회사·부서·플랫폼별 서버 매핑을 따른다.\n'''
    policy_file=root/'data/phase2'/('company-'+co.lower()+'-policy.md');policy_file.write_text(text)
    insert('policy_revisions',policy_id=policy,revision=1,company_id=company,doc_id='P2-'+co+'-POLICY',article='POL-06 제1~5조 / FLOW 제7조',source_path='data/phase2/'+policy_file.name,source_hash=hashlib.sha256(text.encode()).hexdigest(),content=text,is_mock=True)
    insert('approval_route_revisions',route_id=route,revision=1,company_id=company,code='DEFAULT',policy_id=policy,policy_revision=1,steps=['DEPARTMENT_HEAD','SAAS_OPERATOR'] if co=='A' else ['TEAM_LEAD','DEPARTMENT_HEAD','SAAS_OPERATOR'],extra_step_threshold=None if co=='A' else '100.00',currency=None if co=='A' else 'USD')
    active_tf=uid(co+'-active-tf');ended_tf=uid(co+'-ended-tf')
    for tf,code,ends in [(active_tf,'ACTIVE',None),(ended_tf,'ENDED','2026-09-20')]:
        insert_named('tfs',id=tf,company_id=company,code='P2_'+co+'_'+code,name=co+'사 '+code+' TF',leader_id=users['team_lead'],starts_on='2026-08-01',ends_on=ends)
    insert('tf_members',tf_id=active_tf,user_id=users['requester'],company_id=company,active=True,joined_at='2026-08-01T00:00:00+09:00')
    scope=uid(co+'-scope')
    insert('reclaim_scopes',id=scope,company_id=company,department_id=dept,scope_key='phase2:'+co+':paid-seats',platforms=['GITHUB','FIGMA'],enabled=False,selection_mode='ASSIGNMENTS')
    manifest['companies'][co]={'company_id':company,'department_id':dept,'users':users,'policy_id':policy,'route_id':route,'scope_id':scope,'active_tf_id':active_tf,'ended_tf_id':ended_tf}
    for platform,resource_type,code,kind,amount,basis in items:
        resource=uid(co+'-'+platform+'-resource'); entitlement=uid(co+'-'+platform+'-entitlement');pricing=uid(co+'-'+platform+'-price')
        insert_named('resources',id=resource,company_id=company,platform=platform,external_id='p2-'+co.lower()+'-'+platform.lower(),name=co+' '+platform,aliases=[],access_scope='SEAT' if kind=='SEAT' else 'GENERAL',resource_type=resource_type,owner_department_id=dept)
        insert('entitlements',id=entitlement,company_id=company,resource_id=resource,code=code,kind=kind)
        insert('entitlement_revisions',entitlement_id=entitlement,revision=1,company_id=company,external_role=code,mapping={'mock':True,'scope':'assigned_resource_only','requires_existing_account':True,'allows_admin':False,'includes_seat':kind=='SEAT','requires_existing_data_access':platform in ['DATABRICKS','TABLEAU_CLOUD']})
        insert('pricing_revisions',pricing_id=pricing,revision=1,company_id=company,entitlement_id=entitlement,entitlement_revision=1,monthly_amount=amount,currency='USD',cost_basis=basis,source_kind='SYNTHETIC_CONTRACT',source_reference='data/phase2/catalog.json',effective_from='2026-10-01',policy_id=policy,policy_revision=1)
        for capability,actor in [('TEAM_LEAD',users['team_lead']),('DEPARTMENT_HEAD',users['head']),('SAAS_OPERATOR',users['figma_operator'] if co=='B' and platform=='FIGMA' else users['operator']),('IT_HEAD',users['it_head']),('RECLAIM_REVIEWER',users['figma_operator'] if co=='B' and platform=='FIGMA' else users['operator'])]:
            insert('operator_assignments',company_id=company,user_id=actor,department_id=dept,platform=platform,capability=capability)
        insert('saas_context_facts',company_id=company,user_id=users['requester'],platform=platform,account_exists=True,license_active=True,data_access=True,work_scope_assigned=True,job_function={'SALESFORCE':'SALES','DATADOG':'OPS','FIGMA':'DESIGN','TABLEAU_CLOUD':'ANALYST','DATABRICKS':'ANALYST'}.get(platform,'DEV'),observed_at=manifest['as_of'],source_reference='SYNTHETIC:'+co+':'+platform)
        manifest['catalog'].append({'company':co,'platform':platform,'resource_id':resource,'entitlement_id':entitlement,'pricing_id':pricing,'code':code,'kind':kind,'monthly_amount':amount,'currency':'USD','cost_basis':basis,'source_kind':'SYNTHETIC_CONTRACT'})
    for code,idle in [('TF_ENDED_UNUSED_30D',30),('EMPLOYEE_LEFT',None)]:
        insert('reclaim_rules',rule_id=uid(co+'-'+code),revision=1,company_id=company,policy_id=policy,policy_revision=1,code=code,idle_days=idle,exclude_other_active_tf=code!='EMPLOYEE_LEFT',exclude_retention=code!='EMPLOYEE_LEFT')
for co in ['A','B']:
    c=manifest['companies'][co]; company=c['company_id']; resource=uid(co+'-GITHUB-repository')
    insert_named('resources',id=resource,company_id=company,platform='GITHUB',external_id='p2-'+co.lower()+'-payment-repo',name=co+' payment repository',aliases=[],access_scope='TF',tf_id=c['active_tf_id'],resource_type='REPOSITORY',owner_department_id=c['department_id'])
    for role in ['Read','Write']:
        ent=uid(co+'-GITHUB-repo-'+role)
        insert('entitlements',id=ent,company_id=company,resource_id=resource,code=role,kind='ROLE')
        insert('entitlement_revisions',entitlement_id=ent,revision=1,company_id=company,external_role=role,mapping={'mock':True,'team_key':'p2-'+co.lower()+'-payment-'+role.lower(),'requires_team_membership':True})
        insert('pricing_revisions',pricing_id=uid(co+'-GITHUB-repo-'+role+'-price'),revision=1,company_id=company,entitlement_id=ent,entitlement_revision=1,monthly_amount='0.00',currency='USD',cost_basis='NO_ADDITIONAL_COST',source_kind='SYNTHETIC_CONTRACT',source_reference='data/phase2/catalog.json',effective_from='2026-10-01',policy_id=c['policy_id'],policy_revision=1)
        insert('github_teams',id='p2-'+co.lower()+'-payment-'+role.lower(),resource_id=resource,saas_role=role)
    jira=uid(co+'-JIRA-resource')
    insert('jira_role_permissions',resource_id=jira,saas_role='Developer',can_browse=True)
# Each reclaim case has a distinct assignment so fixture conditions cannot interfere.
for case in ['R-01','R-02','R-03','R-04','X-11','MISSING_USAGE','X-10-GITHUB','X-10-FIGMA']:
    company_code='B' if case.startswith('X-10') else 'A'
    platform='FIGMA' if case=='X-10-FIGMA' else 'GITHUB'
    c=manifest['companies'][company_code];co=c['company_id'];user=uid(case+'-user');assignment=uid(case+'-assignment')
    insert('users',id=user,company_id=co,employee_no='P2-'+case,login_id='p2_'+case.lower().replace('-','_'),email=case.lower()+'@example.test',name='회수 '+case,role='REQUESTER',department_id=c['department_id'],job_grade='사원',job_family='DEV',employment_status='LEFT' if case=='X-11' else 'ACTIVE')
    insert('access_assignments',id=assignment,company_id=co,user_id=user,resource_id=uid(company_code+'-'+platform+'-resource'),entitlement_id=uid(company_code+'-'+platform+'-entitlement'),entitlement_revision=1,origin_tf_id=c['ended_tf_id'],granted_at='2026-08-01T00:00:00+09:00')
    insert('assignment_usage',assignment_id=assignment,company_id=co,last_used_at=None if case=='MISSING_USAGE' else '2026-09-05T09:00:00+09:00',observation_status='UNKNOWN' if case=='MISSING_USAGE' else 'KNOWN',observed_at=manifest['as_of'],source_reference='SYNTHETIC:'+case)
    if case=='R-02': insert('tf_members',tf_id=c['active_tf_id'],user_id=user,company_id=co,active=True,joined_at='2026-10-01T00:00:00+09:00')
    if case=='R-03': insert('retention_exceptions',id=uid(case+'-retention'),company_id=co,assignment_id=assignment,approved_by=c['users']['operator'],valid_from='2026-10-01T00:00:00+09:00',valid_until='2026-11-01T00:00:00+09:00',reason='합성 데이터: 인수인계용 유지 승인')
    scope=c['scope_id'] if case=='R-01' or case.startswith('X-10') else uid(case+'-scope')
    if scope!=c['scope_id']:
        insert('reclaim_scopes',id=scope,company_id=co,department_id=c['department_id'],scope_key='phase2:'+company_code+':'+case,platforms=[platform],enabled=False,selection_mode='ASSIGNMENTS')
    insert('reclaim_scope_assignments',scope_id=scope,company_id=co,assignment_id=assignment)
    manifest['reclaim_fixtures'][case]={'user_id':user,'assignment_id':assignment,'scope_id':scope,'company':company_code,'platform':platform}
    if case=='R-04':
        insert_notified_reclaim_history(company_code,c,assignment,scope,platform)
# Scenario overrides are per-test input, never global DB changes on an already running demo.
scenario_defs=[('E-01','GITHUB','WAITING_APPROVAL','ELIGIBLE',{}),('E-02','NOTION','ON_HOLD','BUDGET_INSUFFICIENT',{'budget':'10.00'}),('E-03','SLACK','DONE','ALREADY_HAS_ACCESS',{'already_assigned':True}),('E-04','JIRA','REJECTED','HUMAN_REJECTED',{'reject_step':1}),('E-05','NOTION','REJECTED','HUMAN_REJECTED',{'reject_step':2})]
scenario_defs += [(f'P-0{i+1}',item[0],'WAITING_APPROVAL','ELIGIBLE',{}) for i,item in enumerate(items[:6])]
scenario_defs += [('B-01','GITHUB','REJECTED','POLICY_NOT_ELIGIBLE',{'job_family':'NON_DEV'}),('B-02','GITHUB','WAITING_APPROVAL','LEAST_PRIVILEGE_PROPOSED',{'requested':'Admin','proposed':'Read','resource_kind':'REPOSITORY','resource_id':uid('A-GITHUB-repository'),'entitlement_id':uid('A-GITHUB-repo-Read')}),('B-03','GITHUB','MANUAL_REVIEW','MISSING_SOURCE_EVIDENCE',{'policy_missing':True}),('B-04','SLACK','REJECTED','NOT_TF_MEMBER',{'membership':False}),('B-05','GITHUB','MANUAL_REVIEW','OUT_OF_SCOPE',{'request':'DB 배포 권한'})]
scenario_defs += [(case,'GITHUB','DONE','SCAN_COMPLETED' if case=='R-01' else 'NO_NEW_CANDIDATES',{'assignment_id':manifest['reclaim_fixtures'][case]['assignment_id']}) for case in ['R-01','R-02','R-03','R-04']]
for case,platform,status,reason,overrides in scenario_defs:
    if case=='P-02': overrides['budget']='300.00'
    if case=='P-05': overrides['budget']='200.00'
    if case.startswith('R-'): overrides['scope_id']=manifest['reclaim_fixtures'][case]['scope_id']
    manifest['scenarios'].append({'id':case,'company':'B' if case=='P-06' else 'A','platform':platform,'expected_status':status,'expected_reason_code':reason,'overrides':overrides,'execution_ready':True,'validation_status':'NOT_RUN'})
(root/'data/phase2/catalog.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(root/'data/phase2/seed.sql').write_text('-- Explicit opt-in mock data; not part of automatic Flyway startup.\n-- Apply only to a migrated local/demo database. Reapplying preserves existing mutable state except original demo display names.\nBEGIN;\n'+ '\n'.join(rows)+'\n-- Remove development-stage prefixes from current default labels, preserving custom names and historical evidence.\n'+'\n'.join(name_updates)+'\nCOMMIT;\n')
