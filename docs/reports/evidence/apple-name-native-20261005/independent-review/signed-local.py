from pathlib import Path
import json, os, subprocess
base='/private/tmp/cuadrao-native-apple-name-20261005'
cfg=json.loads(Path('/private/tmp/cuadrao-trust-local-20261005/api-env.json').read_text())
assert cfg['SUPABASE_URL']=='http://127.0.0.1:60331'
env={**os.environ,**cfg,'ARGUS_DISPOSABLE_DATABASE_URL':cfg['DATABASE_URL'],'ARGUS_LOCAL_SUPABASE_URL':cfg['SUPABASE_URL'],'ARGUS_LOCAL_SUPABASE_ANON_KEY':cfg['SUPABASE_ANON_KEY'],'ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY':cfg['SUPABASE_SERVICE_ROLE_KEY'],'PYTHONPATH':base+'/web:'+base+'/src:'+base,'PYTEST_ADDOPTS':'','PYTHON_DOTENV_DISABLED':'1'}
raise SystemExit(subprocess.call(['/private/tmp/cuadrao-scipy-env-20261005/bin/python','-m','pytest','tests/test_apple_name_api_postgres.py','-q','--no-cov','-o','addopts='],cwd=base,env=env))
