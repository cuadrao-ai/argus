import os
import runpy
from pathlib import Path
from dotenv import dotenv_values
source=Path('/Users/garces/Documents/projects/repos/argus-worktrees/private-alpha-next/.env')
os.environ.update({k:v for k,v in dotenv_values(source).items() if v is not None})
os.environ.update({'PYTHON_DOTENV_DISABLED':'1','ISSUE531_QA_API_PORT':'8538','ISSUE531_QA_WEB_PORT':'3218','ARGUS_MARKET_DATA_PROVIDER_MODE':'live_provider','ARGUS_ASSET_PROVIDER_MODE':'live_provider','ARGUS_RESEARCH_RAIL_ENABLED':'false','ARGUS_CONTEXT_PACKETS_ENABLED':'false','NUMBA_CACHE_DIR':'/private/tmp/argus-promotion-numba-cache'})
seed=runpy.run_path('docs/reports/evidence/531/browser/replay_api.py',run_name='p552_seed')
from argus.api.schemas import BacktestRun
from argus.api import state
conversation=seed['CONVERSATION_ID']
message=state.store.messages[conversation][-1]
metadata=message.metadata
facts=metadata['result_fact_bank']
config=facts['config_snapshot']
engine=config['resolved_parameters']['engine_config']
run=BacktestRun.model_validate({**facts,'id':seed['REPLAY_RUN_ID'],'status':'completed','allocation_method':engine['allocation_method'],'conversation_result_card':metadata['result_card'],'chart':metadata['result_card']['chart'],'created_at':message.created_at})
state.store.backtest_runs[run.id]=run
state.store.backtest_run_owners[run.id]=state.store.conversation_owners[conversation]
import uvicorn
uvicorn.run(seed['app'],host='127.0.0.1',port=8538)
