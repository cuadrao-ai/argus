from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parents[4]


def main() -> None:
    assert os.environ['ARGUS_DISPOSABLE_DATABASE_URL'] == 'postgresql://postgres:postgres@127.0.0.1:59612/postgres'
    files = sorted(str(path.relative_to(ROOT)) for path in (ROOT / 'tests').rglob('test_*.py')
                   if 'postgres' in path.name or 'rls' in path.name
                   or 'ARGUS_DISPOSABLE_DATABASE_URL' in path.read_text())
    logger.info('Selected {} Postgres/RLS test files', len(files))
    (ROOT / 'docs/reports/evidence/production-reset/test-files.txt').write_text('\n'.join(files) + '\n')
    status = json.loads(subprocess.run(
        ['supabase', 'status', '--workdir', str(ROOT / 'temp/history'), '-o', 'json'],
        check=True, capture_output=True, text=True,
    ).stdout)
    assert status['API_URL'] == 'http://127.0.0.1:59611'
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'LANG') if key in os.environ}
    env.update({
        'ARGUS_DISPOSABLE_DATABASE_URL': os.environ['ARGUS_DISPOSABLE_DATABASE_URL'],
        'ARGUS_LOCAL_SUPABASE_URL': status['API_URL'],
        'ARGUS_LOCAL_SUPABASE_ANON_KEY': status['ANON_KEY'],
        'ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY': status['SERVICE_ROLE_KEY'],
        'OPENROUTER_API_KEY': '', 'ARGUS_MARKET_DATA_PROVIDER_MODE': 'synthetic_unit_fixture',
    })
    raise SystemExit(subprocess.run(['poetry', 'run', 'pytest', *files, '-q', '--no-cov'],
                                   cwd=ROOT, env=env).returncode)


if __name__ == '__main__':
    main()
