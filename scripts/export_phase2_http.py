"""Export the registered Phase 2 server HTTP surface, connected to the v2 Worker."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def ref(name): return {'$ref':'./schema.json#/$defs/'+name}
def operation(summary,response,body=None,parameters=None,code='200'):
    result={'summary':summary,'description':'Implemented server handler. Asynchronous completion requires running the v2 Worker and MCP services.','responses':{code:{'description':'Success','content':{'application/json':{'schema':response}}},'401':{'description':'Login required'},'403':{'description':'Outside permitted organization/role'},'404':{'description':'Not found in permitted scope'},'409':{'description':'State, plan hash, or idempotency conflict'}},'security':[{'session':[]}]}
    if body: result['requestBody']={'required':True,'content':{'application/json':{'schema':ref(body)}}}
    if parameters: result['parameters']=parameters
    return result
key={'name':'Idempotency-Key','in':'header','required':True,'schema':{'type':'string','minLength':1,'maxLength':128}}
def identifier(name):return {'name':name,'in':'path','required':True,'schema':{'type':'string','format':'uuid'}}
read={'type':'object','required':['read_at'],'properties':{'read_at':{'type':'string','format':'date-time'}},'additionalProperties':False}
overview={'type':'object','required':['last_run','active_run','summary','targets'],'properties':{'last_run':{'anyOf':[ref('ReclaimRunView'),{'type':'null'}]},'active_run':{'anyOf':[ref('ReclaimRunView'),{'type':'null'}]},'summary':{'type':['object','null'],'description':'Final server aggregates; null before first scan or when the latest result is unconfirmed.','properties':{n:{'type':'integer','minimum':0} for n in ['review_target_count','new_candidate_count','newly_notified_count','needs_review_count','unread_count','unknown_cost_target_count']}},'targets':{'type':'array','items':ref('ReclaimTargetView')}},'additionalProperties':False}
overview['properties']['summary']['properties']['monthly_saving_by_currency']={'type':'object','additionalProperties':{'type':'string','pattern':r'^(0|[1-9][0-9]*)\.[0-9]{2}$'}}
paths={
'/api/v2/problems':{'post':operation('권한 요청 접수',ref('AccessView'),'AccessRequestInput',[key],code='202')},
'/api/v2/problems/{problem_id}':{'get':operation('권한 요청 상태 조회',ref('AccessView'),parameters=[identifier('problem_id')])},
'/api/v2/problems/{problem_id}/decisions':{'post':operation('현재 승인 단계 결정',ref('AccessView'),'ApprovalDecisionInput',[identifier('problem_id')])},
'/api/v2/problems/{problem_id}/resume':{'post':operation('보류·수동 검토 재개 후 최신 조건 재분석',ref('AccessView'),parameters=[identifier('problem_id')],code='202')},
'/api/reclaim/overview':{'get':operation('허용 범위의 마지막 점검·후보·미읽음 알림',overview)},
'/api/reclaim/runs':{'post':operation('시연용 회수 점검 접수',{'allOf':[ref('ReclaimRunView')], 'description':'Existing run reuses its actual status. Reuse may be indicated in a response header.'},'ReclaimStartInput',[key],code='202')},
'/api/reclaim/runs/{run_id}':{'get':operation('회수 실행 조회',ref('ReclaimRunView'),parameters=[identifier('run_id')])},
'/api/reclaim/targets/{target_id}':{'get':operation('저장된 후보 상세 조회',ref('ReclaimCandidate'),parameters=[identifier('target_id')])},
'/api/reclaim/notifications/{notification_id}/read':{'patch':operation('본인 알림 읽음, 최초 read_at 보존',read,parameters=[identifier('notification_id')])}}
# Human-confirmed mock revocation is synchronous and never executes through Worker/MCP.
paths['/api/reclaim/targets/{target_id}/execution']={'get':operation('현재 모의 회수 가능 여부와 기존 영수증',ref('ReclaimExecutionState'),parameters=[identifier('target_id')])}
paths['/api/reclaim/targets/{target_id}/revoke']={'post':operation('담당자 확정 후 모의 권한 회수·검증·영수증 원자 저장',ref('ReclaimExecutionReceipt'),'ReclaimRevokeInput',[identifier('target_id'),key])}
paths['/api/reclaim/executions']={'get':operation('담당 범위의 모의 회수 완료 영수증 목록',ref('ReclaimExecutionPage'),parameters=[{'name':'cursor','in':'query','required':False,'schema':{'type':'integer','minimum':0,'default':0}}])}
for route in ['/api/reclaim/targets/{target_id}/execution','/api/reclaim/targets/{target_id}/revoke','/api/reclaim/executions']:
    for op in paths[route].values():
        op['description']='Synchronous session-authenticated mock operation. Mutations require CSRF and demo/mock mode; no Worker or external SaaS call.'
        op['responses']['400']={'description':'Invalid input, cursor or missing Idempotency-Key'}
paths['/api/reclaim/targets/{target_id}/revoke']['post']['responses']['409']={'description':'Execution conflict; refetch state before deciding to retry.','content':{'application/json':{'schema':ref('ReclaimExecutionError')}}}
# Additional read endpoints needed by the UI and service-only MCP endpoints.
array=lambda item:{'type':'array','items':item}
obj={'type':'object'}
paths['/api/v2/problems']['get']=operation('본인 요청·담당 승인 목록',array(ref('AccessView')))
paths['/api/v2/problems/summaries']={'get':operation('허용된 요청의 화면용 목록: workflow·요청자·플랫폼·내용·접수 시각',array(obj))}
paths['/api/v2/problems/catalog']={'get':operation('현재 회사의 선택 가능한 자원·권한 항목',array(obj))}
paths['/api/v2/problems/{problem_id}/report']={'get':operation('승인 계획·근거·이력',obj,parameters=[identifier('problem_id')])}
paths['/api/reclaim/scopes']={'get':operation('실행·조회가 허용된 전체 플랫폼 범위',array(obj))}
paths['/api/reclaim/runs/{run_id}/items']={'get':operation('미확인 행을 포함한 실행별 판정',array(ref('ReclaimCandidate')),parameters=[identifier('run_id')])}
paths['/api/reclaim/notifications']={'get':operation('본인에게 전달된 범위 내 알림',array(obj))}
def internal(summary,response,body=None,parameters=None):
    result=operation(summary,response,body if isinstance(body,str) else None,parameters)
    result['security']=[{'serviceToken':[]}]
    if isinstance(body,dict):result['requestBody']={'required':True,'content':{'application/json':{'schema':body}}}
    return result
uuid_field={'type':'string','format':'uuid'}
execution={'type':'object','required':['job_event_id','plan_hash','idempotency_key'],'properties':{
    'job_event_id':uuid_field,'plan_hash':{'type':'string','pattern':'^[0-9a-f]{64}$'},'idempotency_key':{'type':'string','minLength':1,'maxLength':150}}}
assessment={'type':'object','required':['job_event_id','entitlement_id'],'properties':{'job_event_id':uuid_field,'entitlement_id':uuid_field}}
paths['/internal/v2/problems/{problem_id}/context']={'get':internal('요청·회사별 자원·정책·계정 사실',obj,parameters=[identifier('problem_id')])}
paths['/internal/v2/problems/{problem_id}/assessment']={'post':internal('서버 정책 판정·가격·승인 경로 미리보기, 상태 변경 없음',obj,assessment,[identifier('problem_id')])}
paths['/internal/v2/problems/{problem_id}/execute']={'post':internal('모의 권한 부여·예산·영수증 원자 처리',obj,execution,[identifier('problem_id')])}
paths['/internal/v2/problems/{problem_id}/verify']={'post':internal('별도 요청에서 모의 제공자 상태 재조회, 상태 변경 없음',obj,execution,[identifier('problem_id')])}
paths['/internal/v2/reclaim/context']={'post':internal('고정된 점검 문맥',obj,'ReclaimContextRequest')}
paths['/internal/v2/reclaim/candidates']={'post':internal('고정된 후보 페이지',ref('CandidatePage'),'CandidatePageRequest')}
paths['/internal/v2/reclaim/notification-history']={'post':internal('실행 스냅샷 내 할당의 알림 이력',array(obj),'NotificationHistoryRequest')}
result={'openapi':'3.1.0','info':{'title':'UnlockOps Phase 2 server API','version':'2.0.0'},'paths':paths,'components':{'securitySchemes':{'session':{'type':'apiKey','in':'cookie','name':'JSESSIONID'},'serviceToken':{'type':'http','scheme':'bearer'}}}}
path=ROOT/'contracts/phase2/http.json';content=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
if '--check' in sys.argv:
    if path.read_text()!=content: raise SystemExit('Stale HTTP contract')
else:path.write_text(content)
