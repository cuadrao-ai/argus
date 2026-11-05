import os,json,subprocess,time,pathlib,uuid,httpx,psycopg
root=pathlib.Path('/private/tmp/apple-combined-live'); base='/private/tmp/cuadrao-apple-session-20261005'
name='supabase_auth_cuadrao-trust-20261005'; saved=name+'-apple-combined-saved'
def docker(*args,env=None):return subprocess.check_output(['docker',*args],text=True,env=env,stderr=subprocess.PIPE)
def wait_http(url):
 for _ in range(60):
  try:
   r=httpx.get(url,timeout=2)
   if r.status_code==200:return
  except httpx.HTTPError:pass
  time.sleep(.5)
 raise RuntimeError('local service readiness failed')
cfg=json.loads(pathlib.Path('/private/tmp/cuadrao-trust-local-20261005/api-env.json').read_text())
assert cfg['SUPABASE_URL']=='http://127.0.0.1:60331'
dsn='postgresql://postgres:postgres@127.0.0.1:60332/postgres'
headers={'apikey':cfg['SUPABASE_SERVICE_ROLE_KEY'],'Authorization':'Bearer '+cfg['SUPABASE_SERVICE_ROLE_KEY']}
original=json.loads(docker('inspect',name))[0]
assert list(original['NetworkSettings']['Networks'])==['supabase_network_cuadrao-trust-20261005']
env_vars=dict(e.split('=',1) for e in original['Config']['Env'])
assert env_vars['GOTRUE_SMTP_HOST']=='supabase_inbucket_cuadrao-trust-20261005'
old_users=set()
with psycopg.connect(dsn) as c:old_users={str(r[0]) for r in c.execute('select id from auth.users')}
users=[];api=None;replaced=False;created=False
try:
 docker('stop',name);docker('rename',name,saved);replaced=True
 env_vars.update(GOTRUE_JWT_EXP='60',GOTRUE_MAILER_AUTOCONFIRM='false')
 args=['run','-d','--name',name,'--network','supabase_network_cuadrao-trust-20261005']
 for key in env_vars:args+=['-e',key]
 args+=[original['Config']['Image'],*original['Config']['Cmd']]
 docker(*args,env={**os.environ,**env_vars});created=True
 wait_http(cfg['SUPABASE_URL']+'/auth/v1/health')
 for _ in range(2):
  email=f'apple-final-{uuid.uuid4()}@example.test';password=str(uuid.uuid4())+'Aa!'
  r=httpx.post(cfg['SUPABASE_URL']+'/auth/v1/admin/users',headers=headers,json={'email':email,'password':password,'email_confirm':True});assert r.status_code==200
  users.append({'id':r.json()['id'],'email':email,'password':password})
 fixture=root/'fixture.json';fixture.write_text(json.dumps({'apiURL':'http://127.0.0.1:60341','supabaseURL':cfg['SUPABASE_URL'],'publicAnonKey':cfg['SUPABASE_ANON_KEY'],'users':users}));fixture.chmod(0o600)
 env={**os.environ,**cfg,'PYTHONPATH':base+'/src:'+base+'/web','CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED':'true','CUADRAO_MOCK_AUTH':'false','NEXT_PUBLIC_MOCK_AUTH':'false','ARGUS_DEV_MEMORY_FALLBACK':'false'}
 log=open(root/'api.log','w');api=subprocess.Popen(['/private/tmp/cuadrao-scipy-env-20261005/bin/python','-m','uvicorn','argus.api.main:app','--host','127.0.0.1','--port','60341'],cwd=base,env=env,stdout=log,stderr=log)
 wait_http('http://127.0.0.1:60341/health')
 testenv={**os.environ,'ARGUS_SESSION_LIVE_CONFIG':str(fixture),'CLANG_MODULE_CACHE_PATH':str(root/'clang-cache'),'SWIFTPM_MODULECACHE_OVERRIDE':str(root/'module-cache')}
 with open(root/'swift-live.log','w') as out:
  result=subprocess.run(['swift','test','--package-path',str(root/'package'),'--scratch-path',str(root/'build'),'--disable-sandbox','--skip-build','--filter','Live'],env=testenv,stdout=out,stderr=out)
 print('SWIFT_EXIT',result.returncode,flush=True)
finally:
 if api:
  api.terminate();api.wait(timeout=20)
 with psycopg.connect(dsn) as c:
  owned=[str(row[0]) for row in c.execute("select id from auth.users where id != all(%s::uuid[]) and (email like 'apple-final-%%@example.test' or email like 'ios-%%@example.test')",(list(old_users),))]
 for uid in owned:
  r=httpx.delete(cfg['SUPABASE_URL']+'/auth/v1/admin/users/'+uid,headers=headers);assert r.status_code==200,'owned cleanup failed'
 if created:docker('rm','-f',name)
 if replaced:docker('rename',saved,name);docker('start',name)
 wait_http(cfg['SUPABASE_URL']+'/auth/v1/health')
 restored=json.loads(docker('inspect',name))[0]
 assert restored['Id']==original['Id'] and restored['Config']==original['Config']
 with psycopg.connect(dsn) as c:after={str(row[0]) for row in c.execute('select id from auth.users')}
 assert after==old_users,'fixture user set changed'
 (root/'fixture.json').unlink(missing_ok=True)
 print('CLEANUP_OK original Auth container and env restored; owned API stopped; synthetic users removed; initial user set unchanged',flush=True)
