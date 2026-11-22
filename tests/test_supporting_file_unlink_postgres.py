from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from argus.domain.business import supporting_files
from argus.domain.business.actions.document_deletion import change_document
from argus.domain.business.actions.document_purge import DocumentExpiry
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import SUPPORTING_FILE_LIMIT
from argus.domain.business.contracts.deletion import (
    PURGE_AFTER,
    DocumentCommand,
    deletion,
)
from argus.domain.business.reporting_preferences import ReportRequestV2
from argus.domain.business.reporting_store import read_report
from argus.domain.business.supporting_files import (
    SupportingLinkCommand,
    append_file,
    change_file_link,
)
from argus.domain.ingestion.connections import ConnectionNotFound
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.documents.objects import InMemorySourceObjects
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from faker import Faker
from psycopg.errors import CheckViolation
from psycopg.types.json import Jsonb

from tests import test_business_actions_postgres as shared
from tests.test_business_reporting_postgres import record_expense
from tests.test_registros_annotations_postgres import NoExtraction

users = shared.users
actions = shared.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]
fake = Faker()


@pytest.fixture
def documents(actions):
    service, _, _ = actions
    objects = InMemorySourceObjects()
    hub = IngestionHub(
        PostgresConnectionRepository(service.authority.pool),
        box=None,
        sink=service.imports,
        clock=lambda: datetime.now(timezone.utc),
    )
    return DocumentsService(
        hub, PostgresDocumentStore(service.authority.pool, objects), NoExtraction()
    ), objects


def _content() -> bytes:
    return f"{fake.sentence()} {uuid4()}".encode()


def _append(service, docs, context, draft_id, content: bytes | None = None, name=None):
    return append_file(
        service.authority,
        docs,
        context,
        draft_id,
        service.dossier(context, draft_id).version,
        name or fake.file_name(extension="txt"),
        "text/plain",
        content or _content(),
        str(uuid4()),
    )


def _change(service, context, draft_id, source_id, action, key=None, version=None):
    command = SupportingLinkCommand(
        action=f"{action}_supporting_file",
        draft_id=draft_id,
        expected_version=version or service.dossier(context, draft_id).version,
        source_id=source_id,
    )
    return change_file_link(service.authority, context, command, key or str(uuid4()))


def _files(service, context, draft_id) -> dict:
    return {
        file.source_id: file
        for file in service.dossier(context, draft_id).supporting_files
    }


def _paths(service, receipt_id) -> list[str]:
    with service.authority.pool.connection() as db:
        row = db.execute(
            "select source_path,rebuilt_path from public.financial_document_extractions"
            " where connection_id=%s",
            (receipt_id,),
        ).fetchone()
    return [path for path in row or () if path]


def _expiry(service, objects) -> DocumentExpiry:
    return DocumentExpiry(service.authority.pool, objects, every=timedelta(hours=1))


def test_unlink_takes_the_file_off_the_record_and_history_names_it(actions, documents):
    service, context, _ = actions
    docs, _ = documents
    draft_id, _ = record_expense(service, context)
    name = fake.file_name(extension="txt")
    kept = _append(service, docs, context, draft_id)
    content = _content()
    gone = _append(service, docs, context, draft_id, content, name)
    before = service.dossier(context, draft_id)
    key = str(uuid4())

    result = _change(service, context, draft_id, gone.source_id, "unlink", key)

    assert (result.outcome, result.version) == ("unlinked", before.version + 1)
    after = service.dossier(context, draft_id)
    assert {source.id for source in before.sources} - {
        source.id for source in after.sources
    } == {gone.source_id}
    assert after.facts == before.facts
    assert after.approval_result == before.approval_result
    entry = after.history[-1]
    assert (entry.supporting_change, entry.supporting_filename) == ("unlinked", name)
    assert entry.source_ids == (gone.source_id,)
    assert entry.actor.actor_id == context.actor.actor_id
    assert result.purge_at == entry.created_at + PURGE_AFTER
    files = _files(service, context, draft_id)
    assert files[kept.source_id].state == "linked"
    assert files[kept.source_id].unlink_available
    assert files[gone.source_id].model_dump() == {
        "source_id": gone.source_id,
        "receipt_id": gone.receipt_id,
        "filename": name,
        "media_type": "text/plain",
        "size_bytes": len(content),
        "state": "unlinked",
        "purge_at": result.purge_at,
        "unlink_available": False,
        "restore_available": True,
    }
    [row] = read_report(service.authority, context, ReportRequestV2()).items
    assert {item.source_id for item in row.attachment_sources} >= {str(kept.source_id)}
    assert str(gone.source_id) not in {item.source_id for item in row.attachment_sources}
    # Off the record, never in Eliminados: the upload carries no deletion mark.
    with service.authority.pool.connection() as db:
        [stored] = db.execute(
            "select draft from public.financial_document_extractions where connection_id=%s",
            (gone.receipt_id,),
        ).fetchone()
    assert deletion(stored["status"], stored.get("resolution", {})) is None


@pytest.mark.parametrize("action", ["unlink", "restore"])
def test_the_same_key_twice_is_one_effect(actions, documents, action):
    service, context, _ = actions
    docs, _ = documents
    draft_id, _ = record_expense(service, context)
    file = _append(service, docs, context, draft_id)
    if action == "restore":
        _change(service, context, draft_id, file.source_id, "unlink")
    before = service.dossier(context, draft_id)
    key = str(uuid4())

    first = _change(service, context, draft_id, file.source_id, action, key)
    again = _change(
        service, context, draft_id, file.source_id, action, key, before.version
    )

    assert again == first
    after = service.dossier(context, draft_id)
    assert len(after.history) == len(before.history) + 1
    assert after.version == before.version + 1
    with pytest.raises(ActionError, match="business_action_conflict"):
        _change(service, context, draft_id, uuid4(), action, key, before.version)


def test_restore_within_the_window_puts_the_file_back(actions, documents):
    service, context, _ = actions
    docs, objects = documents
    draft_id, _ = record_expense(service, context)
    name = fake.file_name(extension="txt")
    file = _append(service, docs, context, draft_id, name=name)
    unlinked = _change(service, context, draft_id, file.source_id, "unlink")
    with pytest.raises(ActionError, match="stale_version"):
        _change(service, context, draft_id, file.source_id, "restore", version=1)
    # A run inside the window erases nothing.
    _expiry(service, objects).run(unlinked.purge_at - timedelta(minutes=1))

    restored = _change(service, context, draft_id, file.source_id, "restore")

    assert (restored.outcome, restored.purge_at) == ("restored", None)
    after = service.dossier(context, draft_id)
    assert file.source_id in {source.id for source in after.sources}
    assert _files(service, context, draft_id)[file.source_id].state == "linked"
    assert [
        (entry.supporting_change, entry.supporting_filename)
        for entry in after.history[-3:]
    ] == [("appended", name), ("unlinked", name), ("restored", name)]
    assert (
        docs.store.source(user_id=context.owner_id, connection_id=str(file.receipt_id))
        is not None
    )
    with pytest.raises(ActionError, match="supporting_file_already_linked"):
        _change(service, context, draft_id, file.source_id, "restore")
    # Linked again, the file outlives the old unlink's clock.
    _expiry(service, objects).run(unlinked.purge_at + PURGE_AFTER)
    assert _files(service, context, draft_id)[file.source_id].state == "linked"


def test_restore_is_refused_once_the_window_has_passed(actions, documents, monkeypatch):
    service, context, _ = actions
    docs, _ = documents
    draft_id, _ = record_expense(service, context)
    file = _append(service, docs, context, draft_id)
    _change(service, context, draft_id, file.source_id, "unlink")
    monkeypatch.setattr(supporting_files, "PURGE_AFTER", timedelta(0))

    with pytest.raises(ActionError, match="supporting_file_restore_expired"):
        _change(service, context, draft_id, file.source_id, "restore")
    assert _files(service, context, draft_id) == {}


def test_purge_erases_the_unlinked_file_and_restore_is_refused(actions, documents):
    service, context, _ = actions
    docs, objects = documents
    draft_id, _ = record_expense(service, context)
    other_id, _ = record_expense(service, context)
    name = fake.file_name(extension="txt")
    gone = _append(service, docs, context, draft_id, name=name)
    kept = _append(service, docs, context, draft_id)
    elsewhere = _append(service, docs, context, other_id)
    paths = {item.source_id: _paths(service, item.receipt_id) for item in (gone, kept, elsewhere)}
    assert all(paths.values())
    unlinked = _change(service, context, draft_id, gone.source_id, "unlink")
    expiry = _expiry(service, objects)

    expiry.run(unlinked.purge_at - timedelta(minutes=1))
    assert all(objects.get(path) for path in paths[gone.source_id])

    result = expiry.run(unlinked.purge_at + timedelta(minutes=1))

    assert (result["failed"], result["left"]) == (0, 0)
    assert all(objects.get(path) is None for path in paths[gone.source_id])
    for item in (kept, elsewhere):
        assert all(objects.get(path) for path in paths[item.source_id])
    with service.authority.pool.connection() as db:
        assert db.execute(
            "select (select count(*) from public.business_sources where id=%s),"
            " (select count(*) from public.financial_source_connections where id=%s)",
            (gone.source_id, gone.receipt_id),
        ).fetchone() == (0, 0)
    after = service.dossier(context, draft_id)
    assert set(_files(service, context, draft_id)) == {kept.source_id}
    [entry] = [e for e in after.history if e.supporting_change == "unlinked"]
    assert entry.supporting_filename == name
    assert entry.actor.actor_id == context.actor.actor_id
    assert entry.created_at == unlinked.purge_at - PURGE_AFTER
    assert set(_files(service, context, other_id)) == {elsewhere.source_id}
    with pytest.raises(ActionError, match="supporting_file_restore_expired"):
        _change(service, context, draft_id, gone.source_id, "restore")
    assert expiry.run(unlinked.purge_at + timedelta(minutes=2))["purged"] == 0


def test_purge_keeps_bytes_another_record_took(actions, documents):
    service, context, _ = actions
    docs, objects = documents
    draft_id, _ = record_expense(service, context)
    other_id, _ = record_expense(service, context)
    content = _content()
    file = _append(service, docs, context, draft_id, content)
    paths = _paths(service, file.receipt_id)
    unlinked = _change(service, context, draft_id, file.source_id, "unlink")
    taken = _append(service, docs, context, other_id, content)
    assert taken.receipt_id == file.receipt_id

    _expiry(service, objects).run(unlinked.purge_at + timedelta(minutes=1))

    assert all(objects.get(path) for path in paths)
    assert set(_files(service, context, other_id)) == {taken.source_id}
    assert _files(service, context, draft_id) == {}
    with pytest.raises(ActionError, match="supporting_file_already_linked"):
        _change(service, context, draft_id, file.source_id, "restore")


def test_purge_keeps_an_upload_another_source_holds(actions, documents):
    service, context, _ = actions
    docs, objects = documents
    draft_id, _ = record_expense(service, context)
    file = _append(service, docs, context, draft_id)
    paths = _paths(service, file.receipt_id)
    unlinked = _change(service, context, draft_id, file.source_id, "unlink")
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_sources"
            "(space_id,kind,channel,source_key,connection_id,received_at)"
            " values (%s,'attachment','web',%s,%s,clock_timestamp())",
            (context.actor.space_id, str(uuid4()), file.receipt_id),
        )

    _expiry(service, objects).run(unlinked.purge_at + timedelta(minutes=1))

    assert all(objects.get(path) for path in paths)
    with service.authority.pool.connection() as db:
        assert db.execute(
            "select (select count(*) from public.business_sources where id=%s),"
            " (select count(*) from public.financial_source_connections where id=%s)",
            (file.source_id, file.receipt_id),
        ).fetchone() == (0, 1)


def test_an_unlinked_file_of_a_purged_record_is_erased_on_the_next_run(actions, documents):
    service, context, _ = actions
    docs, objects = documents
    draft_id = shared.ready(service, context)
    file = _append(service, docs, context, draft_id)
    paths = _paths(service, file.receipt_id)
    unlinked = _change(service, context, draft_id, file.source_id, "unlink")
    for action in ("delete_document", "purge_document"):
        command = DocumentCommand(action=action, document_id=draft_id)
        done = change_document(service, context, command, str(uuid4()))
        assert done.outcome == "applied", done
    assert all(objects.get(path) for path in paths)

    result = _expiry(service, objects).run(unlinked.purge_at - PURGE_AFTER)

    assert (result["failed"], result["left"]) == (0, 0)
    assert all(objects.get(path) is None for path in paths)
    with service.authority.pool.connection() as db:
        assert db.execute(
            "select count(*) from public.financial_source_connections where id=%s",
            (file.receipt_id,),
        ).fetchone() == (0,)


def test_a_record_holds_three_files_and_unlinked_ones_do_not_count(actions, documents):
    service, context, _ = actions
    docs, objects = documents
    draft_id, _ = record_expense(service, context)
    held = [_append(service, docs, context, draft_id) for _ in range(SUPPORTING_FILE_LIMIT)]
    full = service.dossier(context, draft_id)
    assert full.supporting_file_limit == SUPPORTING_FILE_LIMIT == 3
    assert (full.supporting_limit_reached, full.supporting_append_available) == (True, False)
    [row] = read_report(service.authority, context, ReportRequestV2()).items
    assert row.can_edit_note and not row.can_append_supporting
    stored = dict(objects.objects)

    with pytest.raises(ActionError) as refused:
        _append(service, docs, context, draft_id)

    assert refused.value.result.outcome == "invalid_input"
    assert refused.value.code == "supporting_file_limit_reached"
    assert service.dossier(context, draft_id).version == full.version
    assert objects.objects == stored
    _change(service, context, draft_id, held[0].source_id, "unlink")
    freed = service.dossier(context, draft_id)
    assert (freed.supporting_limit_reached, freed.supporting_append_available) == (False, True)
    _append(service, docs, context, draft_id)
    files = _files(service, context, draft_id)
    assert not files[held[0].source_id].restore_available
    with pytest.raises(ActionError, match="supporting_file_limit_reached"):
        _change(service, context, draft_id, held[0].source_id, "restore")


def test_at_the_limit_a_request_that_adds_no_file_gets_its_own_answer(actions, documents):
    service, context, _ = actions
    docs, objects = documents
    draft_id, _ = record_expense(service, context)
    other_id, _ = record_expense(service, context)
    content = _content()
    elsewhere = _content()
    _append(service, docs, context, other_id, elsewhere)
    first = _append(service, docs, context, draft_id, content)
    for _ in range(SUPPORTING_FILE_LIMIT - 1):
        _append(service, docs, context, draft_id)
    full = service.dossier(context, draft_id)
    assert full.supporting_limit_reached
    stored = dict(objects.objects)

    again = _append(service, docs, context, draft_id, content)

    assert (again.outcome, again.source_id) == ("duplicate", first.source_id)
    with pytest.raises(ActionError, match="supporting_file_already_linked"):
        _append(service, docs, context, draft_id, elsewhere)
    with pytest.raises(ActionError, match="supporting_file_already_linked"):
        _change(service, context, draft_id, first.source_id, "restore")
    with pytest.raises(ActionError, match="supporting_file_limit_reached"):
        _append(service, docs, context, draft_id)
    assert service.dossier(context, draft_id).version == full.version
    assert objects.objects == stored


def test_only_a_supporting_file_of_this_record_can_be_unlinked(actions, documents):
    service, context, _ = actions
    docs, _ = documents
    draft_id, _ = record_expense(service, context)
    other_id, _ = record_expense(service, context)
    file = _append(service, docs, context, draft_id)
    original = service.dossier(context, draft_id).sources[0]
    for source_id in (original.id, uuid4()):
        with pytest.raises(ActionError, match="supporting_file_not_found"):
            _change(service, context, draft_id, source_id, "unlink")
    with pytest.raises(ActionError, match="supporting_file_not_found"):
        _change(service, context, other_id, file.source_id, "unlink")
    _change(service, context, draft_id, file.source_id, "unlink")
    with pytest.raises(ActionError, match="supporting_file_not_linked"):
        _change(service, context, draft_id, file.source_id, "unlink")
    with pytest.raises(ActionError, match="supporting_file_not_found"):
        _change(service, context, other_id, file.source_id, "restore")
    agent = replace(
        context, actor=context.actor.model_copy(update={"actor_kind": "owner_via_agent"})
    )
    with pytest.raises(ActionError, match="business_human_command_required"):
        _change(service, agent, draft_id, file.source_id, "restore", version=1)


@pytest.mark.parametrize("command", ["unlink_supporting_file", "restore_supporting_file"])
@pytest.mark.parametrize("actor_kind", ["member", "owner_via_agent", "extractor"])
def test_the_ledger_takes_the_commands_from_a_person_only(actions, command, actor_kind):
    service, context, _ = actions
    with supporting_files.transaction(service.authority, context) as tx:
        actor = tx.authorization.provenance.model_dump(mode="json")
        actor["actor_kind"] = actor_kind
        sql = (
            "insert into public.business_action_receipts"
            " (space_id,actor_id,actor,idempotency_key,input_hash,command)"
            " values (%s,%s,%s,%s,%s,%s)"
        )
        params = (
            context.actor.space_id,
            context.actor.actor_id,
            Jsonb(actor),
            str(uuid4()),
            "a" * 64,
            Jsonb({"action": command}),
        )
        if actor_kind == "member":
            tx.connection.execute(sql, params)
            return
        with pytest.raises(CheckViolation) as error, tx.connection.transaction():
            tx.connection.execute(sql, params)
        assert error.value.diag.constraint_name == "business_annotation_human_commands"


def _listings(service, context, name: str) -> dict:
    """What the receipt readers say about the file called ``name``."""

    from argus.api.business_drafts import (
        overview_with_drafts,
        receipt_summaries,
        search_with_drafts,
        updates_with_drafts,
    )
    from argus.api.business_receipt_activity import counts
    from argus.domain.business.search import parse

    from tests.test_business_receipt_views_postgres import _web

    web = _web(service, context)
    views = receipt_summaries(web, "all")
    today = datetime.now(timezone.utc).date()
    return {
        "all": [view["id"] for view in views if view["filename"] == name],
        "inbox": [
            view["id"]
            for view in receipt_summaries(web, "inbox")
            if view["filename"] == name
        ],
        "search": [
            hit["id"] for hit in search_with_drafts(web, parse(name))["receipts"]
        ],
        "updates": updates_with_drafts(web),
        "counts": counts(web, views),
        "overview": overview_with_drafts(web, today - timedelta(days=1), today),
    }


@pytest.mark.parametrize("record", ["approved", "open"])
def test_a_supporting_file_is_never_a_receipt(actions, documents, record):
    service, context, _ = actions
    docs, _ = documents
    draft_id = (
        record_expense(service, context)[0]
        if record == "approved"
        else shared.ready(service, context)
    )
    name = f"{uuid4().hex}.txt"
    without = _listings(service, context, name)
    assert (without["all"], without["inbox"], without["search"]) == ([], [], [])

    file = _append(service, docs, context, draft_id, name=name)
    assert _listings(service, context, name) == without

    _change(service, context, draft_id, file.source_id, "unlink")
    assert _listings(service, context, name) == without

    _change(service, context, draft_id, file.source_id, "restore")
    assert _files(service, context, draft_id)[file.source_id].state == "linked"
    assert _listings(service, context, name) == without


def test_an_upload_something_else_holds_is_still_a_receipt(actions, documents):
    service, context, _ = actions
    docs, _ = documents
    draft_id, _ = record_expense(service, context)
    name = f"{uuid4().hex}.txt"
    file = _append(service, docs, context, draft_id, name=name)
    _change(service, context, draft_id, file.source_id, "unlink")
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_sources"
            "(space_id,kind,channel,source_key,connection_id,received_at)"
            " values (%s,'attachment','web',%s,%s,clock_timestamp())",
            (context.actor.space_id, str(uuid4()), file.receipt_id),
        )

    assert _listings(service, context, name)["all"] == [str(file.receipt_id)]


def _upload_count(service, receipt_id) -> int:
    with service.authority.pool.connection() as db:
        return db.execute(
            "select count(*) from public.financial_source_connections where id=%s",
            (receipt_id,),
        ).fetchone()[0]


@pytest.mark.parametrize("first", ["supporting_file", "receipt"])
def test_the_same_bytes_as_a_receipt_are_a_receipt_the_erase_never_takes(
    actions, documents, first
):
    service, context, _ = actions
    docs, objects = documents
    draft_id, _ = record_expense(service, context)
    content, name = _content(), f"{uuid4().hex}.txt"

    def upload() -> str:
        return asyncio.run(
            docs.upload(
                user_id=context.owner_id,
                content=content,
                filename=name,
                media_type="text/plain",
                scope=context.scope,
            )
        ).connection_id

    receipt_id = upload() if first == "receipt" else None
    file = _append(service, docs, context, draft_id, content, name)
    unlinked = _change(service, context, draft_id, file.source_id, "unlink")
    receipt_id = receipt_id or upload()

    assert receipt_id != str(file.receipt_id)
    listed = _listings(service, context, name)
    assert (listed["all"], listed["inbox"]) == ([receipt_id], [receipt_id])

    result = _expiry(service, objects).run(unlinked.purge_at + timedelta(minutes=1))

    assert (result["failed"], result["left"]) == (0, 0)
    assert _upload_count(service, file.receipt_id) == 0
    assert _listings(service, context, name) == listed
    media_type, stored = docs.store.download_source(
        user_id=context.owner_id, connection_id=receipt_id
    )
    assert (media_type, stored) == ("text/plain", content)


@pytest.mark.parametrize("state", ["linked", "unlinked"])
def test_no_receipt_path_takes_a_supporting_upload(actions, documents, state):
    from argus.api.business_drafts import require_legacy_receipt_write

    from tests.test_business_receipt_views_postgres import _web

    service, context, _ = actions
    docs, _ = documents
    draft_id, _ = record_expense(service, context)
    content = _content()
    file = _append(service, docs, context, draft_id, content)
    if state == "unlinked":
        _change(service, context, draft_id, file.source_id, "unlink")
    web = _web(service, context)
    web.service.documents = docs
    receipt_id = str(file.receipt_id)
    before = service.dossier(context, draft_id)

    for read_or_write in (web.service.receipt, web.service.queue):
        with pytest.raises(ConnectionNotFound):
            read_or_write(web.scope, receipt_id)
    with pytest.raises(ConnectionNotFound):
        require_legacy_receipt_write(web, receipt_id)
    with pytest.raises(ActionError, match="business_record_not_found"):
        service.rebind_attachment_preparation(context, file.receipt_id)
    for action in ("delete_document", "restore_document", "purge_document"):
        command = DocumentCommand(action=action, document_id=file.receipt_id)
        refused = change_document(service, context, command, str(uuid4()))
        assert (refused.outcome, refused.code) == (
            "not_found",
            "business_record_not_found",
        ), action

    assert service.dossier(context, draft_id) == before
    assert _upload_count(service, file.receipt_id) == 1
    assert web.service.source(web.scope, receipt_id) == ("text/plain", content)
