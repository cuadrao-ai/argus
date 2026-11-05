from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from argus.domain.business.contracts.actions import canonical_input_hash
from argus.domain.ingestion.documents.models import ExtractionBatch
from psycopg import Connection, errors
from psycopg.types.json import Jsonb

from tests import test_business_contracts_postgres as shared
from tests.test_business_spaces_migration_postgres import connection, event, space

users = shared.users
db = shared.db
client = shared.client
pytestmark = shared.pytestmark


@pytest.fixture
def binding(db: Connection, client: dict[str, str]) -> dict:
    source = connection(db, client["owner"], client["id"])
    db.execute(
        "insert into public.business_client_grants"
        " (id,space_id,grantee_id,issuer_id,capabilities)"
        " values (%s,%s,%s,%s,array['read','prepare'])",
        (client["grant"], client["id"], client["owner"], client["owner"]),
    )
    actor = shared.actor_provenance(client) | {"actor_kind": "extractor"}
    return {
        "schema_version": 1,
        "binding_id": str(uuid4()),
        "space_id": client["id"],
        "owner_id": client["owner"],
        "connection_id": source,
        "source_sha256": "a" * 64,
        "actor": actor,
        "target": None,
        "consent": True,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }


def capture(db: Connection, binding: dict, **draft_changes: object) -> None:
    draft = {
        "sha256": "a" * 64,
        "consent": True,
        "source_available": True,
    } | draft_changes
    db.execute(
        "insert into public.financial_document_extractions"
        " (connection_id,user_id,draft,source_bytes,preparation_binding)"
        " values (%s,%s,%s,%s,%s)",
        (
            binding["connection_id"],
            binding["owner_id"],
            Jsonb(draft),
            b"synthetic receipt",
            Jsonb(binding),
        ),
    )


def save_batch(db: Connection, binding: dict) -> ExtractionBatch:
    batch = ExtractionBatch(candidates=())
    db.execute(
        "update public.financial_document_extractions set batch=%s where connection_id=%s",
        (Jsonb(batch.model_dump(mode="json")), binding["connection_id"]),
    )
    return batch


def receipt(db: Connection, binding: dict, **overrides: object) -> None:
    row = db.execute(
        "select batch from public.financial_document_extractions where connection_id=%s",
        (binding["connection_id"],),
    ).fetchone()
    digest = (
        canonical_input_hash(ExtractionBatch.model_validate(row[0]))
        if row and row[0] is not None
        else "b" * 64
    )
    command = {
        "action": "prepare_attachment",
        "binding": binding,
        "batch_sha256": digest,
    }
    values = {
        "space_id": binding["space_id"],
        "actor_id": binding["actor"]["actor_id"],
        "actor": binding["actor"],
        "command": command,
        "turn_key": None,
        "action_index": None,
    } | overrides
    db.execute(
        "insert into public.business_action_receipts"
        " (space_id,actor_id,actor,idempotency_key,input_hash,command,turn_key,action_index)"
        " values (%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            values["space_id"],
            values["actor_id"],
            Jsonb(values["actor"]),
            str(uuid4()),
            "c" * 64,
            Jsonb(values["command"]),
            values["turn_key"],
            values["action_index"],
        ),
    )


def test_bound_preparation_and_exact_receipt_survive_status_updates(
    db: Connection,
    binding: dict,
) -> None:
    capture(db, binding)
    save_batch(db, binding)
    receipt(db, binding)
    db.execute(
        "update public.financial_document_extractions"
        ' set draft=draft || \'{"status":"failed","consent":false}\'::jsonb'
        " where connection_id=%s",
        (binding["connection_id"],),
    )
    assert (
        db.execute(
            "select preparation_binding from public.financial_document_extractions"
            " where connection_id=%s",
            (binding["connection_id"],),
        ).fetchone()[0]
        == binding
    )


@pytest.mark.parametrize("field", ["grant_id", "issuer_id", "actor_id"])
def test_original_authority_must_match_live_grant(
    db: Connection,
    binding: dict,
    users: dict[str, str],
    field: str,
) -> None:
    binding["actor"][field] = users["other"]
    with pytest.raises(errors.CheckViolation), db.transaction():
        capture(db, binding)


@pytest.mark.parametrize("change", ["revoked", "read_only", "expired"])
def test_unavailable_preparer_cannot_bind(
    db: Connection,
    binding: dict,
    change: str,
) -> None:
    assignments = {
        "revoked": "revoked_at=clock_timestamp()",
        "read_only": "business_role='viewer'",
        "expired": "created_at=now()-interval '2 days', expires_at=now()-interval '1 day'",
    }
    db.execute(
        f"update public.business_client_grants set {assignments[change]} where id=%s",
        (binding["actor"]["grant_id"],),
    )
    with pytest.raises(errors.CheckViolation), db.transaction():
        capture(db, binding)


@pytest.mark.parametrize("field", ["consent", "source_available"])
def test_current_document_consent_and_source_required(
    db: Connection,
    binding: dict,
    field: str,
) -> None:
    with pytest.raises(errors.CheckViolation), db.transaction():
        capture(db, binding, **{field: False})


@pytest.mark.parametrize("change", ["space", "owner", "source"])
def test_binding_cannot_select_foreign_scope(
    db: Connection,
    binding: dict,
    users: dict[str, str],
    change: str,
) -> None:
    foreign = space(db, users["other"])
    binding[
        {"space": "space_id", "owner": "owner_id", "source": "connection_id"}[change]
    ] = {
        "space": foreign,
        "owner": users["other"],
        "source": connection(db, users["other"], foreign),
    }[change]
    with pytest.raises(errors.CheckViolation), db.transaction():
        capture(db, binding)


@pytest.mark.parametrize("target_kind", ["valid", "stale", "foreign", "legacy"])
def test_explicit_existing_target_is_exact_open_canonical_draft(
    db: Connection,
    binding: dict,
    client: dict[str, str],
    users: dict[str, str],
    target_kind: str,
) -> None:
    target = client["draft"]
    if target_kind == "foreign":
        target = event(db, users["other"], space(db, users["other"]))
    if target_kind != "legacy":
        db.execute(
            "update public.financial_import_events" " set resolution=%s where id=%s",
            (Jsonb({"business": {"schema_version": 1, "facts": {}}}), target),
        )
    binding["target"] = {
        "draft_id": target,
        "version": 2 if target_kind == "stale" else 1,
    }
    if target_kind == "valid":
        capture(db, binding)
        save_batch(db, binding)
        receipt(db, binding)
    else:
        with pytest.raises(errors.CheckViolation), db.transaction():
            capture(db, binding)


@pytest.mark.parametrize("change", ["grant", "source", "target", "remove"])
def test_original_binding_cannot_change_after_capture(
    db: Connection,
    binding: dict,
    change: str,
) -> None:
    capture(db, binding)
    changed = deepcopy(binding)
    if change == "grant":
        changed["actor"]["grant_id"] = str(uuid4())
    elif change == "source":
        changed["source_sha256"] = "d" * 64
    elif change == "target":
        changed["target"] = {"draft_id": str(uuid4()), "version": 1}
    with pytest.raises(errors.CheckViolation), db.transaction():
        db.execute(
            "update public.financial_document_extractions set preparation_binding=%s"
            " where connection_id=%s",
            (None if change == "remove" else Jsonb(changed), binding["connection_id"]),
        )


@pytest.mark.parametrize("change", ["digest", "bytes"])
def test_source_digest_cannot_be_rewritten(
    db: Connection,
    binding: dict,
    change: str,
) -> None:
    capture(db, binding)
    if change == "bytes":
        with pytest.raises(errors.CheckViolation), db.transaction():
            db.execute(
                "update public.financial_document_extractions set source_bytes=%s"
                " where connection_id=%s",
                (b"replacement receipt", binding["connection_id"]),
            )
        return
    with pytest.raises(errors.CheckViolation), db.transaction():
        db.execute(
            "update public.financial_document_extractions"
            " set draft=jsonb_set(draft,'{sha256}',%s) where connection_id=%s",
            (Jsonb("d" * 64), binding["connection_id"]),
        )


@pytest.mark.parametrize("change", ["missing", "batch", "grant", "human", "turn"])
def test_attachment_receipt_requires_original_stored_extractor_binding(
    db: Connection,
    binding: dict,
    client: dict[str, str],
    change: str,
) -> None:
    if change != "missing":
        capture(db, binding)
        save_batch(db, binding)
    changed = deepcopy(binding)
    args = {}
    if change == "grant":
        changed["actor"]["grant_id"] = str(uuid4())
    elif change == "human":
        changed["actor"]["actor_kind"] = "member"
    elif change == "batch":
        args["command"] = {
            "action": "prepare_attachment",
            "binding": binding,
            "batch_sha256": "bad",
        }
    elif change == "turn":
        args.update(turn_key=shared.add_turn(db, client, None), action_index=0)
    with pytest.raises(errors.CheckViolation), db.transaction():
        receipt(db, changed, **args)


def test_connection_delete_purges_binding_and_personal_unbound_is_unchanged(
    db: Connection,
    binding: dict,
) -> None:
    capture(db, binding)
    db.execute(
        "delete from public.financial_source_connections where id=%s",
        (binding["connection_id"],),
    )
    assert db.execute(
        "select count(*) from public.financial_document_extractions where connection_id=%s",
        (binding["connection_id"],),
    ).fetchone() == (0,)
    personal = connection(db, binding["owner_id"])
    db.execute(
        "insert into public.financial_document_extractions(connection_id,user_id,draft)"
        " values(%s,%s,'{}')",
        (personal, binding["owner_id"]),
    )
    assert db.execute(
        "select preparation_binding from public.financial_document_extractions"
        " where connection_id=%s",
        (personal,),
    ).fetchone() == (None,)


@pytest.mark.parametrize("field", ["binding_id", "captured_at", "display_name"])
def test_original_binding_rejects_null_audit_identity(
    db: Connection,
    binding: dict,
    field: str,
) -> None:
    if field == "display_name":
        binding["actor"][field] = None
    else:
        binding[field] = None
    with pytest.raises(errors.CheckViolation), db.transaction():
        capture(db, binding)


def test_receipt_requires_saved_batch(db: Connection, binding: dict) -> None:
    capture(db, binding)
    with pytest.raises(errors.CheckViolation), db.transaction():
        receipt(db, binding)


@pytest.mark.parametrize(
    "replacement", [None, {"candidates": [], "metadata": {"changed": True}}]
)
def test_bound_saved_batch_cannot_be_replaced(
    db: Connection,
    binding: dict,
    replacement: dict | None,
) -> None:
    capture(db, binding)
    saved = save_batch(db, binding)
    save_batch(db, binding)
    with pytest.raises(errors.CheckViolation), db.transaction():
        db.execute(
            "update public.financial_document_extractions set batch=%s where connection_id=%s",
            (
                None if replacement is None else Jsonb(replacement),
                binding["connection_id"],
            ),
        )
    assert db.execute(
        "select batch from public.financial_document_extractions where connection_id=%s",
        (binding["connection_id"],),
    ).fetchone()[0] == saved.model_dump(mode="json")


def test_bound_documents_remain_service_only(db: Connection) -> None:
    assert db.execute(
        "select c.relrowsecurity,"
        " has_table_privilege('anon',c.oid,'SELECT,INSERT,UPDATE,DELETE'),"
        " has_table_privilege('authenticated',c.oid,'SELECT,INSERT,UPDATE,DELETE'),"
        " has_table_privilege('service_role',c.oid,'SELECT,INSERT,UPDATE,DELETE')"
        " from pg_class c join pg_namespace n on n.oid=c.relnamespace"
        " where n.nspname='public' and c.relname='financial_document_extractions'"
    ).fetchone() == (True, False, False, True)
