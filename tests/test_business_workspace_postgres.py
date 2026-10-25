import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from argus.domain.business.access import PostgresAccessStore
from argus.domain.business.spaces import PostgresSpaceStore
from argus.domain.business.workspace import SaveWorkspace, WorkspaceError
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared
from tests.test_business_scope_switch_routes_postgres import web as web_fixture

users = shared.users
web = web_fixture
pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")


@pytest.fixture
def pool():
    with ConnectionPool(shared.DSN, min_size=0, max_size=5) as pool:
        yield pool


def test_concurrent_creation_and_legacy_bootstrap_preserve_default(pool, users):
    store = PostgresSpaceStore(pool)
    actor = users["owner"]
    first, _ = store.create(actor, "Zulu")
    key = str(uuid4())

    def create(index):
        if index % 2:
            return store.create(actor, "Ignored")
        return store.create_additional(actor, "Alpha", "US", key)

    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(create, range(8)))
    additional = {s.id for i, (s, _) in enumerate(results) if not i % 2}
    assert len(additional) == 1
    second_id = additional.pop()
    assert sum(created for _, created in results) == 1
    assert {s.id for i, (s, _) in enumerate(results) if i % 2} == {first.id}
    assert store.open_space(actor).id == first.id
    directory = PostgresAccessStore(pool).spaces_for(actor)
    assert [s.space_id for s in directory] == [first.id, second_id]
    with psycopg.connect(shared.DSN) as db:
        assert (
            db.execute("select public.business_space_of(%s)::text", (actor,)).fetchone()[
                0
            ]
            == first.id
        )
        assert (
            db.execute(
                "select count(*) from public.business_client_grants where space_id=%s",
                (second_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "select count(*) from public.financial_accounts where owner_space_id=%s",
                (second_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "select count(*) from argus_private.business_workspace_commands where actor_id=%s",
                (actor,),
            ).fetchone()[0]
            == 1
        )
    third, _ = store.create_additional(actor, "Third", "CA", str(uuid4()))
    assert third.id not in {first.id, second_id}
    with pytest.raises(WorkspaceError, match="idempotency_conflict"):
        store.create_additional(actor, "Changed", "US", key)


def test_profile_survives_fresh_store_and_partial_patch_preserves_details(pool, users):
    store = PostgresSpaceStore(pool)
    actor = users["owner"]
    first, _ = store.create(actor, "Original")
    second, _ = store.create_additional(actor, "Second", "DO", str(uuid4()))
    saved = store.save_workspace(
        actor,
        first.id,
        SaveWorkspace(
            expected_revision=0,
            details={"address": "Calle Sol", "email": "a@example.test"},
        ),
        "address",
    )
    with ConnectionPool(shared.DSN, min_size=0, max_size=1) as fresh:
        reread = PostgresSpaceStore(fresh).read_workspace(actor, first.id)
    assert reread == saved
    import subprocess
    import sys

    code = (
        "import os; from psycopg_pool import ConnectionPool; "
        "from argus.domain.business.spaces import PostgresSpaceStore; "
        "pool=ConnectionPool(os.environ['ARGUS_DISPOSABLE_DATABASE_URL']); "
        f"print(PostgresSpaceStore(pool).read_workspace({actor!r},{first.id!r}).model_dump_json()); "
        "pool.close()"
    )
    fresh_process = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert type(saved).model_validate_json(fresh_process.stdout) == saved
    updated = store.save_workspace(
        actor,
        first.id,
        SaveWorkspace(
            expected_revision=saved.revision, details={"website": "shop.example"}
        ),
        "presence",
    )
    assert updated.details.address == "Calle Sol"
    assert updated.details.email == "a@example.test"
    assert updated.details.website == "https://shop.example"
    assert store.read_workspace(actor, second.id).details.address == ""
    cleared = store.save_workspace(
        actor,
        first.id,
        SaveWorkspace(expected_revision=updated.revision, details={"email": None}),
        "clear",
    )
    assert cleared.details.email == ""
    assert cleared.details.address == "Calle Sol"


def test_concurrent_save_has_one_winner_and_replay_is_once(pool, users):
    store = PostgresSpaceStore(pool)
    actor = users["owner"]
    space, _ = store.create(actor, "Original")

    def save(index):
        try:
            return store.save_workspace(
                actor,
                space.id,
                SaveWorkspace(expected_revision=0, name=f"Name {index}"),
                f"save-{index}",
            )
        except WorkspaceError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(save, range(2)))
    assert results.count("business_workspace_stale") == 1
    current = store.read_workspace(actor, space.id)
    winner = int(current.name[-1])
    assert current.revision == 1
    assert (
        store.save_workspace(
            actor,
            space.id,
            SaveWorkspace(expected_revision=0, name=current.name),
            f"save-{winner}",
        )
        == current
    )
    with pytest.raises(WorkspaceError, match="idempotency_conflict"):
        store.save_workspace(
            actor,
            space.id,
            SaveWorkspace(expected_revision=1, name="Other"),
            f"save-{winner}",
        )


def test_legacy_rename_and_fiscal_writer_bump_profile_revision(pool, users):
    store = PostgresSpaceStore(pool)
    actor = users["owner"]
    space, _ = store.create(actor, "Original")
    store.rename(actor, "Renamed", space.id)
    assert store.read_workspace(actor, space.id).revision == 1
    with psycopg.connect(shared.DSN) as db:
        db.execute(
            "update public.spaces set name='Fiscal display name' where id=%s", (space.id,)
        )
    assert store.read_workspace(actor, space.id).revision == 2
    with pytest.raises(WorkspaceError, match="business_workspace_stale"):
        store.save_workspace(
            actor, space.id, SaveWorkspace(expected_revision=0, name="Old"), "stale"
        )


def test_default_required_and_client_roles_cannot_read_private_receipts(pool, users):
    store = PostgresSpaceStore(pool)
    with pytest.raises(WorkspaceError, match="business_default_required"):
        store.create_additional(users["owner"], "Extra", "DO", "first")
    for role in ("anon", "authenticated"):
        with (
            psycopg.connect(shared.DSN) as db,
            pytest.raises(psycopg.errors.InsufficientPrivilege),
        ):
            db.execute(f"set local role {role}")
            db.execute("select * from argus_private.business_workspace_commands")


def test_closed_default_reopens_beside_additional_business(pool, users):
    from argus.domain.business.lifecycle import PostgresBusinessLifecycle

    store = PostgresSpaceStore(pool)
    actor = users["owner"]
    first, _ = store.create(actor, "First")
    second, _ = store.create_additional(actor, "Second", "DO", "additional")
    with psycopg.connect(shared.DSN) as db:
        db.execute(
            "update public.spaces set closed_at=clock_timestamp() where id=%s",
            (first.id,),
        )
    assert store.open_space(actor) is None
    result = PostgresBusinessLifecycle(pool)._command(
        owner_id=actor,
        space_id=first.id,
        action="reopen",
        confirmation=None,
        idempotency_key="reopen",
    )
    assert result.closed_at is None
    assert store.open_space(actor).id == first.id
    assert store.get(second.id) is not None


def test_revoked_default_does_not_disable_additional_business_or_heal_grants(pool, users):
    from argus.domain.business.authority import ActionError
    from argus.domain.business.lifecycle import BusinessLifecycleError
    from argus.domain.business.roles import BusinessRole

    store, access = PostgresSpaceStore(pool), PostgresAccessStore(pool)
    actor, other = users["owner"], users["other"]
    first, _ = store.create(actor, "First")
    second, _ = store.create_additional(actor, "Second", "DO", "second")
    with psycopg.connect(shared.DSN) as db:
        email = db.execute(
            "update auth.users set email_confirmed_at=now() where id=%s returning email",
            (other,),
        ).fetchone()[0]
    _, listing = access.give(first.id, actor, email, BusinessRole.OWNER)
    access.accept_invite(other, first.id, listing.invites[0].id)
    owner_grant = next(
        g.id for g in access.list(first.id, actor).grants if g.grantee_id == actor
    )
    access.revoke_grant(first.id, other, owner_grant)
    assert store.open_space(actor) is None
    with pytest.raises(BusinessLifecycleError):
        store.create(actor, "Cannot heal")
    with pytest.raises(ActionError):
        store.read_workspace(actor, first.id)
    assert store.read_workspace(actor, second.id).name == "Second"
    assert store.create_additional(actor, "Second", "DO", "second")[0].id == second.id
    third, _ = store.create_additional(actor, "Third", "DO", "third")
    assert third.id != second.id
    assert access.capabilities(first.id, actor) == ()


@pytest.mark.parametrize("transfer_default", [False, True])
def test_transfer_preserves_default_marker_and_original_custody(
    pool, users, transfer_default
):
    from argus.domain.business.roles import BusinessRole
    from argus.domain.business.transfer import PostgresBusinessTransfer

    store, access = PostgresSpaceStore(pool), PostgresAccessStore(pool)
    actor, other = users["owner"], users["other"]
    first, _ = store.create(actor, "First")
    second, _ = store.create_additional(actor, "Second", "DO", "second")
    target = first if transfer_default else second
    with psycopg.connect(shared.DSN) as db:
        email = db.execute(
            "update auth.users set email_confirmed_at=now() where id=%s returning email",
            (other,),
        ).fetchone()[0]
    _, listing = access.give(target.id, actor, email, BusinessRole.EDITOR)
    grant = access.accept_invite(other, target.id, listing.invites[0].id)
    transfer = PostgresBusinessTransfer(pool)
    requested = transfer._request(
        owner_id=actor,
        space_id=target.id,
        target_grant_id=grant,
        confirmation=target.name,
        idempotency_key="transfer",
    )
    transfer.accept(actor_id=other, transfer_id=requested.id)
    if transfer_default:
        assert store.open_space(actor) is None
        assert store.open_space(other).id == first.id
    else:
        assert store.open_space(actor).id == first.id
        assert store.open_space(other) is None
    with psycopg.connect(shared.DSN) as db:
        assert db.execute(
            "select created_by::text,current_owner_id::text,business_legacy_default from public.spaces where id=%s",
            (target.id,),
        ).fetchone() == (actor, other, transfer_default)


def test_appearance_metadata_persists_and_foreign_asset_is_refused(pool, users):
    from io import BytesIO

    from argus.domain.profile_images.objects import InMemoryProfileImageObjects
    from PIL import Image

    store, objects = PostgresSpaceStore(pool), InMemoryProfileImageObjects()
    actor = users["owner"]
    first, _ = store.create(actor, "First")
    second, _ = store.create_additional(actor, "Second", "DO", "second")
    content = BytesIO()
    Image.new("RGB", (160, 80), "blue").save(content, format="PNG")
    asset = store.upload_workspace_image(
        actor, first.id, content.getvalue(), "image/png", "upload", objects
    )
    assert (
        store.upload_workspace_image(
            actor, first.id, content.getvalue(), "image/png", "upload", objects
        )
        == asset
    )
    command = SaveWorkspace(
        expected_revision=0,
        appearance={"kind": "image", "asset_id": asset.id, "crop": {"mode": "fit"}},
    )
    saved = store.save_workspace(actor, first.id, command, "save", objects)
    with ConnectionPool(shared.DSN, min_size=0, max_size=1) as fresh:
        assert PostgresSpaceStore(fresh).read_workspace(actor, first.id) == saved
        assert (
            PostgresSpaceStore(fresh).workspace_asset(actor, first.id, asset.id) == asset
        )
    before = dict(objects.objects)
    with pytest.raises(WorkspaceError, match="business_image_not_found"):
        store.save_workspace(actor, second.id, command, "foreign", objects)
    assert objects.objects == before
    reset = store.save_workspace(
        actor,
        first.id,
        SaveWorkspace(expected_revision=1, appearance={"kind": "default"}),
        "reset",
        objects,
    )
    assert reset.appearance.kind == "default"
    assert store.workspace_asset(actor, first.id, asset.id) == asset


@pytest.mark.skipif(
    not os.getenv("ARGUS_LOCAL_SUPABASE_URL"), reason="Local Storage required"
)
def test_actual_local_storage_reads_and_paginates_exact_identity_prefix(pool, users):
    from io import BytesIO

    from argus.domain.profile_images.objects import SupabaseProfileImageObjects
    from PIL import Image

    from tests.local_supabase_support import local_supabase_gateway

    objects = SupabaseProfileImageObjects(local_supabase_gateway().client.storage)
    store = PostgresSpaceStore(pool)
    actor = users["owner"]
    first, _ = store.create(actor, "First")
    second, _ = store.create_additional(actor, "Second", "DO", "second")
    content = BytesIO()
    Image.new("RGB", (2, 2), "green").save(content, format="WEBP")
    value = content.getvalue()
    prefix = f"business/{first.id}/identity/"
    other = f"business/{second.id}/identity/keep-source.webp"
    logo = f"business/{first.id}/256.webp"
    try:
        for index in range(103):
            objects.put(prefix + f"{index:064x}-source.webp", value, "image/webp")
        objects.put(other, value, "image/webp")
        objects.put(logo, value, "image/webp")
        assert objects.read(prefix + f"{0:064x}-source.webp") == value
        objects.remove_identity(first.id)
        objects.remove_identity(first.id)
        assert objects.read(other) == value
        assert objects.read(logo) == value
        with psycopg.connect(shared.DSN) as db:
            assert (
                db.execute(
                    "select count(*) from storage.objects where bucket_id='profile-images' and starts_with(name,%s)",
                    (prefix,),
                ).fetchone()[0]
                == 0
            )
    finally:
        objects.remove_identity(first.id)
        objects.remove_identity(second.id)
        objects.remove(logo)


@pytest.mark.skipif(
    not os.getenv("ARGUS_LOCAL_SUPABASE_URL"), reason="Local Auth required"
)
def test_same_creator_additional_business_starts_empty_on_existing_api(web):
    from tests.business.test_business_api import RECEIPT
    from tests.test_business_scope_switch_routes_postgres import _upload

    first = web.alice
    account = web.client.post(
        "/api/v1/business/accounts",
        headers={**first.headers, "Idempotency-Key": "account"},
        json={"type": "checking", "currency": "DOP", "nickname": "First only"},
    )
    assert account.status_code == 201, account.text
    receipt = _upload(web, first, RECEIPT)
    assert receipt.status_code == 200, receipt.text
    second = web.client.post(
        "/api/v1/business/spaces",
        headers={**first.headers, "Idempotency-Key": "additional"},
        json={"name": "Second", "country": "US"},
    )
    assert second.status_code == 201, second.text
    listed = web.client.get("/api/v1/business/spaces", headers=first.headers).json()[
        "spaces"
    ]
    grant = next(s["grant_id"] for s in listed if s["space_id"] == second.json()["id"])
    headers = {**first.headers, "X-Business-Grant": grant}
    workspace = web.client.get("/api/v1/business/workspace", headers=headers)
    assert workspace.status_code == 200, workspace.text
    assert workspace.json()["accounts"] == []
    assert workspace.json()["country"] == "US"
    receipts = web.client.get(
        "/api/v1/business/receipts", headers=headers, params={"view": "all"}
    )
    assert receipts.status_code == 200, receipts.text
    assert receipts.json()["items"] == []
    foreign = web.client.get(
        f"/api/v1/business/receipts/{receipt.json()['id']}", headers=headers
    )
    assert foreign.status_code == 404
    default = web.client.get("/api/v1/business/workspace", headers=first.headers).json()
    assert account.json()["id"] in {a["id"] for a in default["accounts"]}
    assert (
        web.client.get("/api/v1/business/space", headers=first.headers).json()["id"]
        == first.space_id
    )
    path = f"/api/v1/business/spaces/{second.json()['id']}/profile"
    saved = web.client.patch(
        path,
        headers={**headers, "Idempotency-Key": "profile"},
        json={"expected_revision": 0, "details": {"phone": "809-555-0100"}},
    )
    assert saved.status_code == 200, saved.text
    from tests.local_supabase_support import local_supabase_gateway

    gateway = local_supabase_gateway()
    password = f"Synthetic-{uuid4()}-A1!"
    gateway.client.auth.admin.update_user_by_id(first.id, {"password": password})
    session = gateway.client.auth.sign_in_with_password(
        {"email": first.email, "password": password}
    ).session
    assert session is not None
    fresh_headers = {**headers, "Authorization": f"Bearer {session.access_token}"}
    reread = web.client.get(path, headers=fresh_headers)
    assert reread.status_code == 200, reread.text
    assert reread.json() == saved.json()
