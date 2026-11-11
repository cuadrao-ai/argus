from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

import psycopg
from loguru import logger

ROOT = Path(__file__).resolve().parents[4]
URL = 'postgresql://postgres:postgres@127.0.0.1:59612/postgres'
RESET = ROOT / 'scripts/ops/production_reset/reset.sql'


def fingerprint() -> str:
    dump = subprocess.run(['docker', 'exec', 'supabase_db_cuadrao-reset-history',
                           'pg_dump', '-U', 'supabase_admin', '-d', 'postgres', '--schema-only'],
                          check=True, capture_output=True).stdout
    dump = re.sub(rb'(?m)^\\(?:un)?restrict .*\n', b'', dump)
    with psycopg.connect(URL) as db:
        counts = db.execute('select (select count(*) from auth.users),'
                            '(select count(*) from public.profiles),'
                            '(select count(*) from supabase_migrations.schema_migrations),'
                            '(select count(*) from storage.objects)').fetchone()
    return hashlib.sha256(dump + repr(counts).encode()).hexdigest()


def refuse(label: str, fragment: str, url: str = URL) -> None:
    before = fingerprint()
    with psycopg.connect(url, autocommit=True) as db:
        try:
            db.execute(RESET.read_text())
        except psycopg.Error as error:
            db.execute('rollback')
            message = error.diag.message_primary or str(error)
            assert fragment.lower() in message.lower(), message
            logger.info('{}: refused ({})', label, message)
        else:
            raise AssertionError(f'{label}: reset unexpectedly committed')
    assert fingerprint() == before, f'{label}: database changed after refusal'
    logger.info('{}: whole schema and data counts unchanged', label)


def main() -> None:
    refuse('wrong database', 'database', URL.rsplit('/', 1)[0] + '/template1')
    refuse('missing project marker', 'marker')
    with psycopg.connect(URL, autocommit=True) as db:
        db.execute("create table public.cuadrao_reset_marker (project_ref text not null)")
        db.execute("insert into public.cuadrao_reset_marker values ('wrong-project')")
    refuse('wrong project marker', 'marker')
    with psycopg.connect(URL, autocommit=True) as db:
        db.execute("update public.cuadrao_reset_marker set project_ref='lgdhvepyrzbnscqssgqq'")
    refuse('storage still populated', 'storage')


if __name__ == '__main__':
    main()
