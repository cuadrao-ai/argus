import json, shutil, subprocess, tempfile
from pathlib import Path
root=Path.cwd()
with tempfile.TemporaryDirectory(prefix='recovery loader ') as tmp:
    contract=Path(tmp)/'checkout with spaces'/'.github'
    contract.mkdir(parents=True)
    for name in ('argus-env.sh','private-alpha-release-profile.py','private-alpha-release-profile.json'):
        shutil.copy2(root/'.github'/name,contract/name)
    expected=json.loads((contract/'private-alpha-release-profile.json').read_text())['services']
    def run(flags='-c'):
        return subprocess.run(['/bin/bash',flags,'source "$1"; printf "API:%s\\n" "${ARGUS_RENDER_API_ENV[@]}"; printf "WEB:%s\\n" "${ARGUS_RENDER_WEB_ENV[@]}"; echo CONTRACT_LOADED','bash',str(contract/'argus-env.sh')],cwd='/private/tmp',capture_output=True,text=True)
    count=0
    for flags in ('-c','-uc','-euc'):
        p=run(flags)
        assert p.returncode==0,p.stderr
        for surface,prefix in [('api','API:'),('web','WEB:')]:
            keys={line[len(prefix):] for line in p.stdout.splitlines() if line.startswith(prefix)}
            assert keys==set(expected[surface]['env'])|set(expected[surface]['required_present'])|set(expected[surface]['optional'])
        count+=1
    tool=contract/'private-alpha-release-profile.py'
    original=tool.read_text()
    for failure in ('missing-tool','malformed-profile','empty','partial'):
        if failure=='missing-tool':tool.unlink()
        elif failure=='malformed-profile':(contract/'private-alpha-release-profile.json').write_text('{')
        elif failure=='empty':tool.write_text('')
        else:tool.write_text('print("ARGUS_PARTIAL_KEY")\nraise SystemExit(7)\n')
        for flags in ('-c','-uc','-euc'):
            p=run(flags)
            assert p.returncode!=0,(failure,flags,p.stdout)
            assert 'CONTRACT_LOADED' not in p.stdout and 'ARGUS_PARTIAL_KEY' not in p.stdout
            count+=1
        tool.write_text(original)
        shutil.copy2(root/'.github/private-alpha-release-profile.json',contract/'private-alpha-release-profile.json')
    for flags in ('-c','-uc'):
        tool.write_text('import sys\nif sys.argv[-1] == "web":\n print("ARGUS_PARTIAL_WEB_KEY")\n raise SystemExit(7)\nprint("ARGUS_API_TEST_KEY")\n')
        p=run(flags)
        assert p.returncode!=0 and 'CONTRACT_LOADED' not in p.stdout and 'ARGUS_PARTIAL_WEB_KEY' not in p.stdout
        count+=1
    print(subprocess.run(['/bin/bash','--version'],capture_output=True,text=True).stdout.splitlines()[0])
    print(f'{count} loader boundary checks passed; outside cwd, spaced checkout, nounset, malformed/missing/empty/partial failures, resolved API/web keys.')
