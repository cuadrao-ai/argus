from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psycopg
from faker import Faker
from loguru import logger

ROOT = Path(__file__).resolve().parents[4]
URL = 'postgresql://postgres:postgres@127.0.0.1:59612/postgres'
API = 'http://127.0.0.1:59611'
BUCKETS = ('financial-document-sources', 'profile-images')


def client() -> httpx.Client:
    status = json.loads(subprocess.run(
        ['supabase', 'status', '--workdir', str(ROOT / 'temp/history'), '-o', 'json'],
        check=True, capture_output=True, text=True,
    ).stdout)
    assert status['API_URL'] == API
    key = status['SERVICE_ROLE_KEY']
    return httpx.Client(base_url=API, headers={'apikey': key, 'Authorization': f'Bearer {key}'})


def seed() -> None:
    fake = Faker()
    fake.seed_instance(1789)
    with client() as api, psycopg.connect(URL) as db:
        for _ in range(3):
            email = fake.unique.user_name() + '@example.test'
            password = fake.password(length=24)
            response = api.post('/auth/v1/admin/users', json={
                'email': email, 'password': password, 'email_confirm': True,
            })
            response.raise_for_status()
            user = response.json()['id']
            login = api.post('/auth/v1/token?grant_type=password', json={
                'email': email, 'password': password,
            })
            login.raise_for_status()
            db.execute('insert into public.profiles (id,email,display_name) values (%s,%s,%s)',
                       (user, email, fake.name()))
            space = db.execute(
                "insert into public.spaces (kind,name,created_by) values ('business',%s,%s) returning id",
                (fake.company()[:70], user),
            ).fetchone()[0]
            db.execute("insert into public.financial_accounts (user_id,type,currency,owner_space_id) "
                       "values (%s,'cash','DOP',%s)", (user, space))
        db.execute('alter function argus_private.bind_guest_signup_handoff() set schema public')
        db.execute('create type public.reset_legacy_kind as enum (\'synthetic\')')
        db.execute('create table public.reset_legacy_extra (id int primary key, kind public.reset_legacy_kind)')
        db.execute("insert into public.reset_legacy_extra values (1,'synthetic')")
        db.execute('create view public.reset_legacy_view as select id from public.reset_legacy_extra')
        db.execute("create function public.reset_legacy_function() returns int language sql as 'select 1'")
        for bucket, mime in zip(BUCKETS, ('text/plain', 'image/webp'), strict=False):
            upload = api.post(f'/storage/v1/object/{bucket}/synthetic-proof',
                              content=fake.sentence().encode(), headers={'Content-Type': mime})
            upload.raise_for_status()
        counts = db.execute('select (select count(*) from auth.users), '
                            '(select count(*) from auth.identities), '
                            '(select count(*) from auth.sessions), '
                            '(select count(*) from storage.objects)').fetchone()
        assert counts == (3, 3, 3, 2), counts
    logger.info('Seeded 3 Faker users, 3 identities, 3 sessions, 3 profiles, 3 spaces, 3 accounts, '
                '2 real Storage API uploads, a legacy public auth handler, and extra legacy table/view/type/function')


def empty() -> None:
    with client() as api:
        for bucket in BUCKETS:
            api.post(f'/storage/v1/bucket/{bucket}/empty').raise_for_status()
        for _ in range(30):
            with psycopg.connect(URL) as db:
                if db.execute('select count(*) from storage.objects').fetchone()[0] == 0:
                    break
            time.sleep(1)
        else:
            raise RuntimeError('Storage API did not finish emptying local buckets')
        for bucket in BUCKETS:
            response = api.get(f'/storage/v1/object/authenticated/{bucket}/synthetic-proof')
            assert response.status_code >= 400
            api.delete(f'/storage/v1/bucket/{bucket}').raise_for_status()
    with psycopg.connect(URL) as db:
        assert db.execute('select count(*) from storage.buckets').fetchone()[0] == 0
    logger.info('Storage API empty/delete completed for both buckets; uploaded files no longer readable')


if __name__ == '__main__':
    {'seed': seed, 'empty': empty}[sys.argv[1]]()
