from pathlib import Path
import json, os, subprocess, uuid, time, plistlib, socket
import httpx
import psycopg

root = Path('/private/tmp/apple-combined-live')
base = Path('/private/tmp/cuadrao-apple-session-20261005')
derived = Path('/private/tmp/cuadrao-apple-combined-xcode')
sim = 'AD3171CD-69D5-44E9-93AF-1E38FE5FFCD7'
cfg = json.loads(Path('/private/tmp/cuadrao-trust-local-20261005/api-env.json').read_text())
assert cfg['SUPABASE_URL'] == 'http://127.0.0.1:60331'
for port in (60341, 60345):
    with socket.socket() as sock: sock.bind(('127.0.0.1', port))
headers = {'apikey': cfg['SUPABASE_SERVICE_ROLE_KEY'], 'Authorization': 'Bearer ' + cfg['SUPABASE_SERVICE_ROLE_KEY']}
users=[]; api=None; bridge=None; runner=None
config=root/'native.xcconfig'
def url(value): return value.replace('://', ':/$()/')
config.write_text('\n'.join([
 'ARGUS_AUTH_ENABLED = true',
 'ARGUS_API_URL = '+url('http://127.0.0.1:60341'),
 'ARGUS_SUPABASE_URL = '+url(cfg['SUPABASE_URL']),
 'ARGUS_SUPABASE_ANON_KEY = '+cfg['SUPABASE_ANON_KEY'],
 'ARGUS_WEB_URL = '+url('http://127.0.0.1:60345'),
 'ARGUS_CAPTCHA_URL = '+url('http://127.0.0.1:60345/captcha.html'),
 'ARGUS_APPLE_SIGN_IN_ENABLED = false', 'ARGUS_GOOGLE_SIGN_IN_ENABLED = false',
 'ARGUS_LOCAL_BUNDLE_IDENTIFIER = local.argus.apple-combined-proof'])+'\n')
config.chmod(0o600)
def wait(url):
 for _ in range(60):
  try:
   if httpx.get(url,timeout=2).status_code==200:return
  except httpx.HTTPError:pass
  time.sleep(.5)
 raise RuntimeError('owned loopback readiness failed')
try:
 with open(root/'ui-build.log','w') as log:
  subprocess.run(['xcodebuild','build-for-testing','-project',str(base/'ios/ArgusFoundation.xcodeproj'),'-scheme','ArgusFoundation','-destination','platform=iOS Simulator,id='+sim,'-derivedDataPath',str(derived),'-clonedSourcePackagesDirPath','/private/tmp/cuadrao-apple-session-xcode-packages','-disableAutomaticPackageResolution','-parallel-testing-enabled','NO','-xcconfig',str(config),'CODE_SIGNING_REQUIRED=NO'],stdout=log,stderr=log,check=True)
 for _ in range(2):
  email='apple-combined-ui-'+str(uuid.uuid4())+'@example.test'; password=str(uuid.uuid4())+'Aa!'
  response=httpx.post(cfg['SUPABASE_URL']+'/auth/v1/admin/users',headers=headers,json={'email':email,'password':password,'email_confirm':True})
  assert response.status_code==200
  users.append({'id':response.json()['id'],'email':email,'password':password})
 env={**os.environ,**cfg,'PYTHONPATH':str(base/'src')+':'+str(base/'web'),'CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED':'true','CUADRAO_MOCK_AUTH':'false','NEXT_PUBLIC_MOCK_AUTH':'false','ARGUS_DEV_MEMORY_FALLBACK':'false'}
 api_log=open(root/'ui-api.log','w')
 api=subprocess.Popen(['/private/tmp/cuadrao-scipy-env-20261005/bin/python','-m','uvicorn','argus.api.main:app','--host','127.0.0.1','--port','60341'],cwd=base,env=env,stdout=api_log,stderr=api_log)
 print('OWN_API_PID',api.pid,flush=True);wait('http://127.0.0.1:60341/health')
 bridge_script=root/'captcha.py'
 bridge_script.write_text('''from http.server import BaseHTTPRequestHandler,HTTPServer
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  body=b'<html><body><script>setTimeout(()=>window.webkit.messageHandlers.argusCaptcha.postMessage({type:"token",token:"XXXX.DUMMY.TOKEN.XXXX"}),500)</script></body></html>'
  self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(body)
HTTPServer(('127.0.0.1',60345),Handler).serve_forever()
''')
 bridge=subprocess.Popen(['/private/tmp/cuadrao-scipy-env-20261005/bin/python',str(bridge_script)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 print('OWN_CAPTCHA_PID',bridge.pid,flush=True);wait('http://127.0.0.1:60345/captcha.html')
 source=next((derived/'Build/Products').glob('*.xctestrun'))
 for index, language in enumerate(('en','es-419')):
  owner=users[index]
  settings=plistlib.loads(source.read_bytes())
  targets=[t for c in settings['TestConfigurations'] for t in c['TestTargets']] if 'TestConfigurations' in settings else [v for k,v in settings.items() if not k.startswith('__')]
  for target in targets:
   target.setdefault('EnvironmentVariables',{}).update({'ARGUS_TEST_LANGUAGE':language,'ARGUS_TEST_EMAIL':owner['email'],'ARGUS_TEST_PASSWORD':owner['password'],'ARGUS_TEST_EMAIL_B':users[1]['email'],'ARGUS_TEST_PASSWORD_B':users[1]['password']})
  runner=source.with_name('apple-combined-'+language+'.xctestrun');runner.write_bytes(plistlib.dumps(settings));runner.chmod(0o600)
  result=root/('primary-currency-'+language+'.xcresult')
  with open(root/('primary-currency-'+language+'.log'),'w') as log:
   r=subprocess.run(['xcodebuild','test-without-building','-xctestrun',str(runner),'-destination','platform=iOS Simulator,id='+sim,'-parallel-testing-enabled','NO','-only-testing:ArgusFoundationUITests/AuthJourneyUITests/testPrimaryCurrencySurvivesRelaunch','-resultBundlePath',str(result)],stdout=log,stderr=log)
  print('PRIMARY_CURRENCY_UI',language,'EXIT',r.returncode,flush=True)
  runner.unlink();runner=None
  if r.returncode:raise RuntimeError('primary currency UI failure '+language)
  # Assert actual committed row after the UI write and relaunch.
  with psycopg.connect('postgresql://postgres:postgres@127.0.0.1:60332/postgres') as db:
   row=db.execute('select currency_override from public.profiles where id=%s',(owner['id'],)).fetchone()
  assert row==('USD',);print('PG_PRIMARY_CURRENCY_READBACK',language,'USD',flush=True)
finally:
 if runner:runner.unlink(missing_ok=True)
 for proc in (bridge,api):
  if proc:proc.terminate();proc.wait(timeout=20)
 for user in users:
  r=httpx.delete(cfg['SUPABASE_URL']+'/auth/v1/admin/users/'+user['id'],headers=headers);assert r.status_code==200
 config.unlink(missing_ok=True)
 print('UI_CLEANUP_OK own API/CAPTCHA stopped; own users removed; private runner/config deleted',flush=True)
