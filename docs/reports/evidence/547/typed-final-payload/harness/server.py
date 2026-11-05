"""Local-only investigation harness: exact code, fixture auth, synthetic market data.
No transport/allowance/graph/projection substitutions. /qa endpoints seed input
artifacts and roll the disposable visitor counter to the prior day.
"""
import os, sys, json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4
qa_language=sys.argv[3] if len(sys.argv)>3 else 'en'
if os.environ.get('CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED') not in {'true', 'false'}:
    raise ValueError('Set CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED explicitly for acceptance')
ROOT=Path(sys.argv[1]).resolve()
OUT=Path(sys.argv[2]).resolve()
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
os.chdir(ROOT)
os.environ.update(CUADRAO_PERSISTENCE_MODE='memory',ARGUS_DEV_MEMORY_FALLBACK='false', CUADRAO_CHECKPOINTER_MODE='memory', ARGUS_MARKET_DATA_PROVIDER_MODE='synthetic_unit_fixture', CUADRAO_GUEST_ACCESS_ENABLED='true',  ARGUS_BACKTEST_JOBS_SHADOW_ENABLED='true',ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED='false',ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED='false', CUADRAO_CORS_ALLOW_ORIGINS='http://127.0.0.1:55480,http://localhost:55480', ARGUS_DISPOSABLE_DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:55482/postgres', CUADRAO_VISITOR_KEY_SECRET='local-docn-investigation', OPENROUTER_API_KEY='', OPENROUTER_GUEST_API_KEY='', CUADRAO_MOCK_AUTH='false')
from fastapi import Request
from argus.api.main import app
from argus.api import state as api_state
from argus.api.dependencies import current_user
from argus.api.guest_access import AccountContext, guest_capabilities, store_account_context, visitor_key_for_request
from argus.api.schemas import User
from argus.domain.supabase_gateway import SupabaseGateway
from postgrest import SyncPostgrestClient
from tests.test_allowance_accounting_postgres import _connect, _seed_guest_owner
from argus.agent_runtime.stages.confirm import _coverage_preflight
from argus.agent_runtime.confirmation_artifacts import confirmation_artifact_reference
from argus.api.chat.confirmation import runtime_confirmation_card
from argus.api.message_store import create_message
from argus.agent_runtime.graph import workflow as wf

client=SyncPostgrestClient('http://127.0.0.1:55481')
api_state.supabase_gateway=SupabaseGateway(client=client)
api_state.PERSISTENCE_MODE='supabase'
with _connect() as db:
    owner=_seed_guest_owner(db)
    db.execute('update public.profiles set language=%s,locale=%s where id=%s',(qa_language, 'es-419' if qa_language=='es-419' else 'en-US',owner['user_id']))
    db.execute('update public.conversations set language=%s where id=%s',(qa_language,owner['conversation_id']))
now=datetime.now(timezone.utc)
user=User(id=owner['user_id'],email=None,language=qa_language,locale='es-419' if qa_language=='es-419' else 'en-US',created_at=now,updated_at=now)
async def fixture_current_user(request: Request):
    store_account_context(request,AccountContext(kind='guest',user_id=user.id,expires_at=datetime.fromisoformat(owner['period_end']),capabilities=guest_capabilities(),conversation_id=owner['conversation_id'],visitor_key=visitor_key_for_request(request)))
    return user
app.dependency_overrides[current_user]=fixture_current_user

def record(kind,data):
    with OUT.open('a') as f: f.write(json.dumps({'kind':kind,'data':data},default=str)+'\n')
original_apply=wf._apply_stage_result
def trace_apply(state,result):
    changed=original_apply(state,result)
    if 'final_response_payload' in result.patch:
        record('stage_boundary',{'outcome':result.outcome,'before':result.patch['final_response_payload'],'after':changed['run_state'].final_response_payload.model_dump(mode='json') if changed['run_state'].final_response_payload else None})
    return changed
wf._apply_stage_result=trace_apply

@app.get('/qa/state')
def state():
    with _connect() as db:
        data={'owner':owner,'jobs':db.execute('select id,status,failure_code,result_run_id from public.backtest_jobs where user_id=%s order by created_at',(user.id,)).fetchall(),'runs':db.execute('select id,status from public.backtest_runs where user_id=%s',(user.id,)).fetchall(),'workspace_usage':db.execute('select resource,period,used_count,limit_count from public.usage_counters where user_id=%s',(user.id,)).fetchall(),'visitor_usage':db.execute('select resource,period,period_start,used_count from public.visitor_usage_counters').fetchall()}
    return json.loads(json.dumps(data,default=str))

@app.post('/qa/confirmation')
def seed():
    base={'strategy_type':'buy_and_hold','symbol':'DOCN','symbols':['DOCN'],'asset_class':'equity','timeframe':'1D','date_range':{'start':'2023-09-05','end':'2026-09-03'},'sizing_mode':'capital_amount','capital_amount':1000,'benchmark_symbol':'SPY','language':qa_language}
    preflight=_coverage_preflight(base,optional_parameter_status={})
    assert preflight['outcome']=='ready_to_confirm', preflight
    launch=preflight['launch_payload']
    cid='confirmation-'+str(uuid4())
    confirmation={'confirmation_id':cid,'artifact_id':cid,'strategy':{'strategy_type':'buy_and_hold','strategy_thesis':'Buy and hold DOCN','asset_universe':['DOCN'],'asset_class':'equity','capital_amount':1000,'date_range':launch['date_range'],'comparison_baseline':'SPY'},'optional_parameters':{},'launch_payload':launch,'validation':{'status':'ready_to_run','executable':True}}
    ref=confirmation_artifact_reference(confirmation_payload=confirmation,confirmation_id=cid)
    card=runtime_confirmation_card({'stage_outcome':'await_approval','confirmation_payload':confirmation},confirmation_id=cid,conversation_id=owner['conversation_id'],language=qa_language)
    msg=create_message(user_id=user.id,conversation_id=owner['conversation_id'],role='assistant',content='',metadata={'confirmation_payload':confirmation,'confirmation_card':card,'active_confirmation_reference':ref.model_dump(mode='json'),'artifact_references':[ref.model_dump(mode='json')]})
    # A prepared card is a fixture input, with no retained graph from prior runs.
    api_state.reset_agent_runtime_workflow(app)
    return {'message_id':msg.id,'confirmation_id':cid,'conversation_id':owner['conversation_id'],'card':card}

@app.post('/qa/day-rollover')
def rollover():
    with _connect() as db:
        # Move only the visitor-day charges to yesterday, simulating UTC rollover.
        # The lifetime workspace usage and identity remain untouched.
        db.execute("update public.visitor_usage_counters set period_start=period_start-interval '1 day', period_end=period_end-interval '1 day'")
    return state()

@app.post('/qa/start-over')
def start_over():
    with _connect() as db:
        owner['conversation_id']=str(db.execute("select id from public.replace_guest_conversation(%s,'DOCN investigation','system_default',%s)",(user.id,qa_language)).fetchone()[0])
    api_state.reset_agent_runtime_workflow(app)
    return state()

@app.post('/qa/cleanup')
def cleanup():
    with _connect() as db:
        db.execute('delete from auth.users where id=%s',(user.id,))
        db.execute('delete from public.visitor_usage_counters')
    return {'cleaned':True}

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=55479,log_level='warning')
