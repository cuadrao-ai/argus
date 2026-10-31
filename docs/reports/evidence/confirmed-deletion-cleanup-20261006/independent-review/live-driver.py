from pathlib import Path
import json,os,subprocess,uuid,time,socket
import httpx,psycopg
root=Path('/private/tmp/cuadrao-atomic-cleanup-live');base=Path('/private/tmp/cuadrao-confirmed-deletion-cleanup-20261006')
cfg=json.loads(Path('/private/tmp/cuadrao-trust-local-20261005/api-env.json').read_text())
assert cfg['SUPABASE_URL']=='http://127.0.0.1:60331'
with socket.socket() as sock:sock.bind(('127.0.0.1',60343))
headers={'apikey':cfg['SUPABASE_SERVICE_ROLE_KEY'],'Authorization':'Bearer '+cfg['SUPABASE_SERVICE_ROLE_KEY']}
users=[];api=None;fixture=root/'fixture.json'
with psycopg.connect(cfg['DATABASE_URL']) as db:before_runs={str(r[0]) for r in db.execute('select id from argus_private.account_deletion_runs')}
def wait(url):
 for _ in range(60):
  try:
   if httpx.get(url,timeout=2).status_code==200:return
  except httpx.HTTPError:pass
  time.sleep(.5)
 raise RuntimeError('owned API readiness failed')
try:
 for _ in range(2):
  email='atomic-cleanup-'+str(uuid.uuid4())+'@example.test';password=str(uuid.uuid4())+'Aa!'
  r=httpx.post(cfg['SUPABASE_URL']+'/auth/v1/admin/users',headers=headers,json={'email':email,'password':password,'email_confirm':True});assert r.status_code==200
  users.append({'id':r.json()['id'],'email':email,'password':password})
 fixture.write_text(json.dumps({'apiURL':'http://127.0.0.1:60343','supabaseURL':cfg['SUPABASE_URL'],'publicAnonKey':cfg['SUPABASE_ANON_KEY'],'users':users}));fixture.chmod(0o600)
 env={**os.environ,**cfg,'PYTHONPATH':str(base/'web')+':'+str(base/'src')+':'+str(base),'PYTHON_DOTENV_DISABLED':'1','CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED':'true','CUADRAO_ACCOUNT_DELETION_ENABLED':'true','CUADRAO_MOCK_AUTH':'false','NEXT_PUBLIC_MOCK_AUTH':'false','ARGUS_DEV_MEMORY_FALLBACK':'false','APP_ENV':'test','ARGUS_ANALYTICS_DELETION_ENABLED':'false'}
 log=open(root/'api-private.log','w')
 api=subprocess.Popen(['/private/tmp/cuadrao-scipy-env-20261005/bin/python','-m','uvicorn','argus.api.main:app','--host','127.0.0.1','--port','60343'],cwd=base,env=env,stdout=log,stderr=log)
 print('OWN_API_PID',api.pid,flush=True);wait('http://127.0.0.1:60343/health')
 testenv={**os.environ,'ARGUS_SESSION_LIVE_CONFIG':str(fixture),'CLANG_MODULE_CACHE_PATH':'/private/tmp/cuadrao-combined-clang-cache','SWIFTPM_MODULECACHE_OVERRIDE':'/private/tmp/cuadrao-combined-swift-cache'}
 with open(root/'swift-live.log','w') as out:
  result=subprocess.run(['swift','test','--package-path',str(root/'ios/Packages/ArgusSession'),'--scratch-path','/private/tmp/cuadrao-apple-session-swift','--cache-path','/private/tmp/cuadrao-session-spm-cache','--disable-sandbox','--disable-automatic-resolution','--filter','LiveDeletionTests'],env=testenv,stdout=out,stderr=out)
 print('LIVE_DELETION_EXIT',result.returncode,flush=True)
 with psycopg.connect(cfg['DATABASE_URL']) as db:
  alive=[db.execute('select exists(select 1 from auth.users where id=%s)',(user['id'],)).fetchone()[0] for user in users]
  new_runs={str(r[0]) for r in db.execute('select id from argus_private.account_deletion_runs')}-before_runs
  assert len(new_runs)==1
  status=db.execute('select status from argus_private.account_deletion_runs where id=%s',(next(iter(new_runs)),)).fetchone()
 print('PG_A_PRESENT',alive[0],'PG_B_PRESENT',alive[1],'PG_A_RUN_STATUS',status[0] if status else 'none',flush=True)
 assert alive[1]
 if result.returncode:raise RuntimeError('actual deletion SDK check failed')
 assert status and status[0] in ('done','in_progress')
 if status[0]=='done':assert not alive[0]
finally:
 if api:api.terminate();api.wait(timeout=20)
 for user in users:
  r=httpx.delete(cfg['SUPABASE_URL']+'/auth/v1/admin/users/'+user['id'],headers=headers);assert r.status_code in (200,404)
 with psycopg.connect(cfg['DATABASE_URL']) as db:
  owned_runs={str(r[0]) for r in db.execute('select id from argus_private.account_deletion_runs')}-before_runs
  assert len(owned_runs)<=1
  for run in owned_runs:db.execute('delete from argus_private.account_deletion_runs where id=%s',(run,))
 fixture.unlink(missing_ok=True)
 print('CLEANUP_OK own API stopped; own synthetic users removed; private fixture deleted; root Auth config/DB preserved',flush=True)
