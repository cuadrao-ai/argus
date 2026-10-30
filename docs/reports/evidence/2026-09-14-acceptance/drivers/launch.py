import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from dotenv import dotenv_values
import yaml

EVIDENCE = Path(__file__).resolve().parent.parent
SCRATCH = Path('/private/tmp/argus-acceptance-20260914')
ROOT = SCRATCH / 'source'
PYTHON = '/Users/garces/.codex/worktrees/edb9/private-alpha-next/.venv/bin/python'
PATH = '/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'
BASICS = {'PATH': PATH, 'HOME': os.path.expanduser('~')}
APP_ORIGIN = 'http://localhost:3149'
API_ORIGIN = 'http://localhost:8149/api/v1'
REAL_ENV = '/Users/garces/Documents/projects/repos/argus-worktrees/private-alpha-next/.env'
MEASURED = '039189128ea6ffcf59be73f3564fd936f191f662'

def env_files_absent():
    return all(not p.exists() and not p.is_symlink() for p in [ROOT/'.env', ROOT/'web/.env.local'])

def assemble():
    assert env_files_absent(), 'environment check failed: env file present'
    # ROOT is a clean git archive of MEASURED; dependencies are linked only.
    assert (SCRATCH/'source-sha.txt').read_text().strip() == MEASURED
    status = subprocess.run(['supabase','status','--workdir',str(SCRATCH/'stack'),'-o','env'],env=BASICS,capture_output=True,text=True)
    if status.returncode:
        # Access failure: report the exact error, no alternate access path.
        print(status.stderr, file=sys.stderr)
        raise SystemExit(status.returncode)
    local = dotenv_values(stream=io.StringIO(status.stdout))
    for key in ('API_URL','ANON_KEY','SERVICE_ROLE_KEY','DB_URL','JWT_SECRET'):
        assert local.get(key), f'environment check failed: missing scratch {key}'
    assert local['API_URL'].startswith('http://127.0.0.1:56731')
    assert '@127.0.0.1:56732/' in local['DB_URL']
    source = dotenv_values(REAL_ENV)
    required_secrets = ['CUADRAO_OPS_TOKEN','CUADRAO_VISITOR_KEY_SECRET','PERPLEXITY_API_KEY','CUADRAO_PROD_OPENROUTER_API_KEY','CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY','ALPACA_API_KEY','ALPACA_SECRET_KEY']
    for key in required_secrets:
        assert source.get(key), f'environment check failed: missing {key}'
    services = {s['name']:s for s in yaml.safe_load((ROOT/'render.yaml').read_text())['services']}
    environments, reports = {}, {}
    for service in ('argus-api','argus-app'):
        entries = services[service]['envVars']
        declared = {x['key'] for x in entries}
        literals = {x['key']:str(x['value']) for x in entries if 'value' in x}
        env = {**BASICS, **literals}
        if service == 'argus-api':
            substitutions = {'SUPABASE_URL':local['API_URL'],'SUPABASE_ANON_KEY':local['ANON_KEY'],'ARGUS_APP_ORIGIN':APP_ORIGIN,'CUADRAO_CORS_ALLOW_ORIGINS':APP_ORIGIN,'ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED':'false','ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED':'false'}
            env.update({key:source[key] for key in required_secrets})
            env.update(DATABASE_URL=local['DB_URL'],SUPABASE_SERVICE_ROLE_KEY=local['SERVICE_ROLE_KEY'],SUPABASE_JWT_SECRET=local['JWT_SECRET'])
            intentionally_absent = ['RENDER_API_KEY','POSTHOG_PROJECT_TOKEN','CUADRAO_APPROVAL_EMAIL_SMTP_PASSWORD']
            allowed_extra = set(BASICS)
        else:
            substitutions = {'NEXT_PUBLIC_SUPABASE_URL':local['API_URL'],'NEXT_PUBLIC_SUPABASE_ANON_KEY':local['ANON_KEY'],'NEXT_PUBLIC_ARGUS_API_URL':API_ORIGIN,'ARGUS_APP_ORIGIN':APP_ORIGIN}
            # Derive the same token used by the repository QA launcher.
            captcha = re.search(r'^export const LOCAL_QA_CAPTCHA_TOKEN = "([^"]+)";', (ROOT/'web/lib/guest-captcha.ts').read_text(), re.M).group(1)
            env['NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN'] = captcha
            intentionally_absent = ['NEXT_PUBLIC_POSTHOG_KEY','NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY']
            allowed_extra = {*BASICS,'NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN'}
        env.update(substitutions)
        assert all(key in env for key in literals), f'environment check failed: missing {service} literal'
        assert {key for key,value in literals.items() if env[key] != value} == set(substitutions), f'environment check failed: unexpected {service} literal difference'
        assert set(env)-declared <= allowed_extra, f'environment check failed: undeclared {service} key'
        assert not any(key in env for key in intentionally_absent), f'environment check failed: forbidden {service} key'
        assert not any(marker in value for value in env.values() for marker in ('lgdhvepyrzbnscqssgqq','arguschat.ai')), f'environment check failed: production value in {service}'
        assert env_files_absent()
        def present_value(key):
            if key not in env:
                return 'absent'
            if re.search('KEY|TOKEN|PASSWORD|SECRET|DATABASE',key):
                return 'present'
            return env[key]
        reports[service] = {'status':'pass','all_render_literal_keys_set':True,'only_approved_literal_differences':True,'no_undeclared_keys':True,'no_forbidden_production_values':True,'env_files_absent':True,'keys':{key:present_value(key) for key in sorted(declared | set(env))},'substitution_keys':sorted(substitutions),'intentionally_absent':intentionally_absent}
        environments[service] = env
    report = {'candidate_sha':MEASURED,'render_sha256':hashlib.sha256((ROOT/'render.yaml').read_bytes()).hexdigest(),'release_profile_sha256':hashlib.sha256((ROOT/'.github/private-alpha-release-profile.json').read_bytes()).hexdigest(),'services':reports,'local_differences':['in-process backtests instead of argus-backtests','no Turnstile widget; localhost-only QA token','no PostHog','no real application emails','localhost origins'],'api_shadow_jobs_enabled':True,'api_app_env_production':True,'secrets_never_printed_or_written':True}
    (EVIDENCE/'environment-proof.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'environment_check':'pass','services':list(reports),'values_printed':False,'env_files_absent':True}),flush=True)
    return environments

def serve_api(phase='browser'):
    sys.path[:0] = [str(ROOT/'src'),str(ROOT/'web'),str(ROOT)]
    import argus
    assert Path(argus.__file__).resolve().is_relative_to(ROOT)
    # Reuse the read-only invoice observer without adding environment keys.
    observer_path = Path(__file__).parent/'observer.py'
    spec = importlib.util.spec_from_file_location('promotion_observer',observer_path)
    observer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(observer)
    observer.SIDE = 'browser_walk' if phase == 'browser' else 'replay'
    observer.LEDGER = EVIDENCE / 'cost-events.jsonl'
    observer.PHASE = SCRATCH/'phase.txt'
    sys.setprofile(observer.observe)
    __import__('threading').setprofile(observer.observe)
    import uvicorn
    uvicorn.run('argus.api.main:app',host='127.0.0.1',port=8149)

if __name__ == '__main__':
    action = sys.argv[1]
    if action in ('serve-api', 'serve-api-replay'):
        serve_api('replay' if action == 'serve-api-replay' else 'browser')
    else:
        envs = assemble()
        if action == 'build':
            with (SCRATCH/'web-build.log').open('w') as log:
                result = subprocess.run(['bun','run','build'],cwd=ROOT/'web',env=envs['argus-app'],stdout=log,stderr=subprocess.STDOUT)
            print(json.dumps({'web_production_build_exit':result.returncode}),flush=True)
            raise SystemExit(result.returncode)
        if action in ('start', 'start-replay'):
            assert (ROOT/'web/.next/BUILD_ID').exists(), 'production build required'
            pids = {}
            api_action = 'serve-api-replay' if action == 'start-replay' else 'serve-api'
            for service,cmd,cwd in [('argus-api',[PYTHON,str(Path(__file__)),api_action],ROOT),('argus-app',['bun','run','start','--','-p','3149'],ROOT/'web')]:
                # Pure env passed directly to exec, equivalent to env -i plus
                # the audited declared keys. No shell or dotenv sourcing.
                with (SCRATCH/f'{service}.log').open('w') as log:
                    os.chmod(log.name, 0o600)
                    p = subprocess.Popen(cmd,cwd=cwd,env=envs[service],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                pids[service]=p.pid
            (SCRATCH/'server-pids.json').write_text(json.dumps(pids)+'\n')
            print(json.dumps({'started':pids}),flush=True)
