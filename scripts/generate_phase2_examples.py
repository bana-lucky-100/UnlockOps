"""Golden v2 wire vectors shared by Python and Java; no live services required."""
import copy
import json
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
from unlockops.common.phase2 import GrantPlanV2
ROOT=Path(__file__).resolve().parents[1]
def uid(s): return str(uuid5(NAMESPACE_URL,'unlockops:phase2:'+s))
catalog=json.loads((ROOT/'data/phase2/catalog.json').read_text())
c=catalog['companies']['A'];item=catalog['catalog'][0]
plan=dict(schema_version=2,problem_id=uid('example-problem'),company_id=c['company_id'],requester_id=c['users']['requester'],platform='SNOWFLAKE',resource_id=item['resource_id'],entitlement_id=item['entitlement_id'],entitlement_revision=1,pricing_id=item['pricing_id'],pricing_revision=1,monthly_amount='120.00',currency='USD',cost_basis='USAGE_ESTIMATE',policy_id=c['policy_id'],policy_revision=1,route_id=c['route_id'],route_revision=1,approver_ids=[c['users']['head'],c['users']['operator']])
model=GrantPlanV2.model_validate(plan)
common=dict(schema_version=2,status='RECEIVED',reason_code=None,message='접수됨',current_step=None,total_steps=0,approval_steps=[],verification_ok=None)
steps=[dict(step=1,approver_id=plan['approver_ids'][0],status='APPROVED',reason=None,acted_at='2026-10-22T08:00:00+09:00'),dict(step=2,approver_id=plan['approver_ids'][1],status='WAITING',reason=None,acted_at=None)]
access={**common,'task_type':'ACCESS_REQUEST','problem_id':plan['problem_id'],'result_type':None,'status':'WAITING_APPROVAL','reason_code':'ELIGIBLE','message':'IT 최종 승인 대기','current_step':2,'total_steps':2,'approval_steps':steps,'plan_hash':model.digest(),'plan_version':1}
scan={**common,'task_type':'RECLAIM_SCAN','run_id':uid('example-run'),'status':'DONE','reason_code':'NO_NEW_CANDIDATES','message':'신규 회수 후보 없음','snapshot_id':uid('example-snapshot'),'as_of':catalog['as_of'],'scan_complete':True,'needs_review_count':0,'new_candidate_count':0,'pending_notification_count':0}
job=dict(schema_version=2,event_id=uid('example-job'),task_type='RECLAIM_SCAN',job_type='RECLAIM_CHECK',run_id=scan['run_id'],trigger='MANUAL_DEMO',scope_key='phase2:A:paid-seats',scheduled_for=catalog['as_of'])
policy_file=ROOT/'data/phase2/company-a-policy.md'
import hashlib
candidate=dict(assignment_id=catalog['reclaim_fixtures']['R-01']['assignment_id'],target_id=None,episode_id=None,platform='GITHUB',candidate_status='PENDING_REVIEW',candidate_reason_code='TF_ENDED_UNUSED_30D',exclusion_reason_code=None,skip_reason_code=None,review_required=False,notified_at=None,read_at=None,action_taken='NONE',generation_mode='template',explanation='TF 종료 후 미사용 30일 이상인 좌석으로 담당자 검토가 필요합니다.',policy_evidence=[dict(doc_id='P2-A-POLICY',article='POL-06 제5조',version='1',source_hash=hashlib.sha256(policy_file.read_bytes()).hexdigest(),text='프로젝트 지급 좌석은 TF 종료 후 연속 미사용 30일 이상이고 다른 활성 TF 이용 및 유효 유지 승인이 없으면 검토 후보로 제안한다.')],fact_evidence=[dict(source='assignment_usage',record_id=catalog['reclaim_fixtures']['R-01']['assignment_id'],observed_at=catalog['as_of'])],cost_impact=dict(status='ESTIMATED',monthly_amount='19.00',currency='USD',basis='SYNTHETIC_CONTRACT'))
event=dict(schema_version=2,event_id=uid('example-event'),job_event_id=job['event_id'],task_type='RECLAIM_SCAN',run_id=scan['run_id'],event_type='RECLAIM_CHECKED',result={**scan,'status':'EXECUTING','reason_code':'SCAN_IN_PROGRESS','message':'점검 결과 반영 대기','new_candidate_count':1},targets=[candidate])
valid=[dict(name='plan',model='GrantPlanV2',payload=plan),dict(name='approval_waiting',model='AccessView',payload=access),dict(name='scan_done_empty',model='ReclaimRunView',payload=scan),dict(name='scan_job',model='ReclaimJob',payload=job),dict(name='candidate',model='ReclaimCandidate',payload=candidate),dict(name='scan_result',model='ReclaimEvent',payload=event),dict(name='hold',model='AccessView',payload={**common,'task_type':'ACCESS_REQUEST','problem_id':plan['problem_id'],'status':'ON_HOLD','reason_code':'BUDGET_INSUFFICIENT','result_type':None})]
invalid=[]
def bad(name,model,value,change):
    value=copy.deepcopy(value);change(value);invalid.append(dict(name=name,model=model,payload=value))
bad('self_approval','GrantPlanV2',plan,lambda p:p.update(approver_ids=[p['requester_id']]))
bad('numeric_money','GrantPlanV2',plan,lambda p:p.update(monthly_amount=120))
bad('unexpected_field','GrantPlanV2',plan,lambda p:p.update(admin=True))
bad('approval_bypass','AccessView',access,lambda p:p['approval_steps'][0].update(status='PENDING',acted_at=None))
bad('incomplete_scan','ReclaimRunView',scan,lambda p:p.update(scan_complete=False))
bad('notification_pending','ReclaimRunView',scan,lambda p:p.update(pending_notification_count=1))
bad('new_candidates_reported_empty','ReclaimRunView',scan,lambda p:p.update(new_candidate_count=1))
bad('scan_claims_grant','ReclaimRunView',scan,lambda p:p.update(verification_ok=True))
bad('worker_claims_done','ReclaimEvent',event,lambda p:p['result'].update(status='DONE',reason_code='SCAN_COMPLETED'))
bad('wrong_run','ReclaimEvent',event,lambda p:p.update(run_id=uid('wrong-run')))
bad('unknown_cost_zero','ReclaimCandidate',candidate,lambda p:p['cost_impact'].update(status='UNKNOWN'))
bad('notification_without_delivery','ReclaimCandidate',candidate,lambda p:p.update(skip_reason_code='ALREADY_NOTIFIED'))
bad('missing_policy','ReclaimCandidate',candidate,lambda p:p.update(policy_evidence=[]))
decision=dict(action='APPROVE',expected_plan_hash=model.digest(),expected_plan_version=2,reason=None)
bad('hold_without_reason','ApprovalDecisionInput',{**decision,'action':'HOLD','reason':''},lambda p:None)
bad('decision_missing_version','ApprovalDecisionInput',decision,lambda p:p.pop('expected_plan_version'))
bad('decision_invalid_version','ApprovalDecisionInput',decision,lambda p:p.update(expected_plan_version=0))
bad('wrong_hold_reason','AccessView',valid[-1]['payload'],lambda p:p.update(reason_code='ELIGIBLE'))
bad('missing_version','GrantPlanV2',plan,lambda p:p.pop('schema_version'))
bad('false_verification_on_lookup_error','AccessView',{**common,'task_type':'ACCESS_REQUEST','problem_id':plan['problem_id'],'result_type':None,'status':'FAILED','reason_code':'TOOL_CALL_FAILED','verification_ok':False},lambda p:None)
valid.append(dict(name='approval_decision',model='ApprovalDecisionInput',payload=decision))
valid.append(dict(name='scan_done_needs_review',model='ReclaimRunView',payload={**scan,'reason_code':'SCAN_COMPLETED','needs_review_count':1,'message':'점검 완료 · 추가 확인 1건','summary':{'needs_review_count':1,'new_candidate_count':0,'pending_notification_count':0},'needs_review':[{'assignment_id':candidate['assignment_id'],'employee_name':'김개발','resource_name':'Copilot 좌석','missing':['USAGE_OBSERVATION']}]}))
bad('review_reported_empty','ReclaimRunView',scan,lambda p:p.update(needs_review_count=1))
bad('scan_manual_review','ReclaimRunView',scan,lambda p:p.update(status='MANUAL_REVIEW',reason_code='MISSING_SOURCE_EVIDENCE'))
output={'schema_version':2,'plan_canonical_json':model.canonical_json(),'plan_sha256':model.digest(),'valid':valid,'invalid':invalid}
(ROOT/'contracts/phase2/examples/vectors.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
for v in valid:
    (ROOT/'contracts/phase2/examples'/(v['name']+'.json')).write_text(json.dumps(v['payload'],ensure_ascii=False,indent=2)+'\n')
