from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from argus.domain.business.annotations import EditCurrentNote, edit_note
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.reporting_preferences import ReportRequestV2
from argus.domain.business.reporting_store import read_report
from argus.domain.business.supporting_files import append_file
from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from pydantic import ValidationError

from tests import test_business_actions_postgres as shared
from tests.test_business_reporting_postgres import record_expense, viewer_context

users = shared.users
actions = shared.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]


class FileObjects:
    bucket = "financial-document-sources"

    def __init__(self, directory: Path):
        self.directory = directory
        self.fail_after_put = False

    def put(self, path, content, media_type):
        target = self.directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        if self.fail_after_put:
            self.fail_after_put = False
            raise RuntimeError("synthetic lost acknowledgement")

    def get(self, path):
        target = self.directory / path
        return target.read_bytes() if target.exists() else None


class NoExtraction:
    async def extract(self, **kwargs):
        pytest.fail("supporting files cannot extract")


@pytest.fixture
def documents(actions, tmp_path):
    service, _, _ = actions
    objects = FileObjects(tmp_path)
    hub = IngestionHub(
        PostgresConnectionRepository(service.authority.pool),
        box=None,
        sink=service.imports,
        clock=lambda: datetime.now(timezone.utc),
    )
    return DocumentsService(
        hub, PostgresDocumentStore(service.authority.pool, objects), NoExtraction()
    ), objects


def test_note_unicode_clear_replay_and_approved_financial_facts(actions):
    service, context, _ = actions
    draft_id, _ = record_expense(service, context)
    before = service.dossier(context, draft_id)
    before_report = read_report(service.authority, context, ReportRequestV2())
    command = EditCurrentNote(expected_version=before.version, note="😀" * 500)
    result = edit_note(service.authority, context, draft_id, command, "unicode")
    assert edit_note(service.authority, context, draft_id, command, "unicode") == result
    after = service.dossier(context, draft_id)
    assert after.current_note == command.note
    assert after.facts == before.facts
    assert after.approval_result == before.approval_result
    assert after.history[-1].before == after.history[-1].after == before.facts
    assert after.history[-1].after_current_note == command.note
    assert len(after.history) == len(before.history) + 1
    report = read_report(service.authority, context, ReportRequestV2(filters={"q": "😀"}))
    assert report.items[0].revision == result.version
    assert report.items[0].can_edit_note
    assert report.items[0].recorded_amount == before_report.items[0].recorded_amount
    assert report.fingerprint != before_report.fingerprint
    cleared = edit_note(
        service.authority,
        context,
        draft_id,
        EditCurrentNote(expected_version=result.version, note=""),
        "clear",
    )
    assert service.dossier(context, draft_id).current_note == ""
    assert cleared.version == result.version + 1
    with pytest.raises(ValidationError):
        EditCurrentNote(expected_version=1, note="😀" * 501)
    with pytest.raises(ActionError, match="business_action_conflict"):
        edit_note(
            service.authority,
            context,
            draft_id,
            EditCurrentNote(expected_version=before.version, note="changed"),
            "unicode",
        )


def test_note_concurrent_loser_and_revoked_replay(actions, users):
    service, context, _ = actions
    draft_id = shared.ready(service, context)
    version = service.dossier(context, draft_id).version

    def write(note):
        try:
            return edit_note(
                service.authority,
                context,
                draft_id,
                EditCurrentNote(expected_version=version, note=note),
                note,
            )
        except ActionError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ["one", "two"]))
    assert results.count("stale_version") == 1
    winner = next(result for result in results if result != "stale_version")
    assert service.dossier(context, draft_id).current_note == winner.note
    viewer = viewer_context(service, context, users["other"])
    with pytest.raises(ActionError):
        edit_note(
            service.authority,
            viewer,
            draft_id,
            EditCurrentNote(expected_version=version, note="no"),
            "viewer",
        )
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set business_role='editor',capabilities=array['read','prepare'] where id=%s",
            (viewer.grant_id,),
        )
    editor = service.resolve_actor(
        TrustedActor(
            actor_id=viewer.actor.actor_id,
            actor_kind="member",
            space_id=context.actor.space_id,
        ),
        grant_id=viewer.grant_id,
    )
    edited = EditCurrentNote(expected_version=winner.version, note="editor note")
    edit_note(service.authority, editor, draft_id, edited, "editor")
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=clock_timestamp() where id=%s",
            (editor.grant_id,),
        )
    with pytest.raises(ActionError):
        edit_note(service.authority, editor, draft_id, edited, "editor")


def test_supporting_multiple_files_duplicate_bytes_and_retry(actions, documents):
    service, context, _ = actions
    docs, objects = documents
    draft_id, activity_id = record_expense(service, context)
    before = service.dossier(context, draft_id)
    first = append_file(
        service.authority,
        docs,
        context,
        draft_id,
        before.version,
        "José.txt",
        "text/plain",
        b"first synthetic file",
        "first",
    )
    assert first.outcome == "appended"
    assert (
        append_file(
            service.authority,
            docs,
            context,
            draft_id,
            before.version,
            "José.txt",
            "text/plain",
            b"first synthetic file",
            "first",
        )
        == first
    )
    second = append_file(
        service.authority,
        docs,
        context,
        draft_id,
        first.version,
        "Second.txt",
        "text/plain",
        b"second synthetic file",
        "second",
    )
    duplicate = append_file(
        service.authority,
        docs,
        context,
        draft_id,
        second.version,
        "renamed.txt",
        "text/plain",
        b"first synthetic file",
        "duplicate",
    )
    assert duplicate.outcome == "duplicate" and duplicate.version == second.version
    after = service.dossier(context, draft_id)
    assert after.facts == before.facts and after.approval_result == before.approval_result
    assert len(after.sources) == len(before.sources) + 2
    assert len(after.history) == len(before.history) + 2
    assert (
        docs.store.source(user_id=context.owner_id, connection_id=str(first.receipt_id))
        == b"first synthetic file"
    )
    assert (
        docs.get(
            user_id=context.owner_id,
            connection_id=str(first.receipt_id),
            scope=context.scope,
        ).status
        == "saved"
    )
    report = read_report(
        service.authority, context, ReportRequestV2(filters={"q": "jose"})
    )
    assert report.matching_count == 1
    assert report.items[0].linked_activity_ids == (activity_id,)
    assert len(report.items[0].attachment_sources) == 2
    with pytest.raises(ActionError, match="business_action_conflict"):
        append_file(
            service.authority,
            docs,
            context,
            draft_id,
            before.version,
            "José.txt",
            "text/plain",
            b"changed",
            "first",
        )


def test_supporting_storage_crash_resumes_without_duplicate_history(actions, documents):
    service, context, _ = actions
    docs, objects = documents
    draft_id = shared.ready(service, context)
    before = service.dossier(context, draft_id)
    objects.fail_after_put = True
    args = (
        service.authority,
        docs,
        context,
        draft_id,
        before.version,
        "Crash.txt",
        "text/plain",
        b"crash fixture",
        "crash",
    )
    with pytest.raises(RuntimeError, match="lost acknowledgement"):
        append_file(*args)
    assert service.dossier(context, draft_id) == before
    restarted = DocumentsService(
        docs.hub,
        PostgresDocumentStore(service.authority.pool, FileObjects(objects.directory)),
        NoExtraction(),
    )
    result = append_file(service.authority, restarted, *args[2:])
    assert append_file(service.authority, restarted, *args[2:]) == result
    assert len(service.dossier(context, draft_id).history) == len(before.history) + 1


def test_supporting_conflicting_link_wrong_business_and_revoked_replay(
    actions, documents, users
):
    service, context, _ = actions
    docs, _ = documents
    first_draft = shared.ready(service, context)
    second_draft = shared.ready(service, context)
    first = append_file(
        service.authority,
        docs,
        context,
        first_draft,
        1,
        "one.txt",
        "text/plain",
        b"one fixture",
        "one",
    )
    with pytest.raises(ActionError, match="supporting_file_already_linked"):
        append_file(
            service.authority,
            docs,
            context,
            second_draft,
            1,
            "one.txt",
            "text/plain",
            b"one fixture",
            "conflict",
        )
    with pytest.raises(ActionError, match="business_record_not_found"):
        append_file(
            service.authority,
            docs,
            context,
            uuid4(),
            1,
            "one.txt",
            "text/plain",
            b"one fixture",
            "foreign",
        )
    viewer = viewer_context(service, context, users["other"])
    assert (
        not read_report(service.authority, viewer, ReportRequestV2())
        .items[0]
        .can_append_supporting
    )
    with pytest.raises(ActionError):
        append_file(
            service.authority,
            docs,
            viewer,
            first_draft,
            first.version,
            "one.txt",
            "text/plain",
            b"one fixture",
            "viewer",
        )
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set business_role='editor',capabilities=array['read','prepare'] where id=%s",
            (viewer.grant_id,),
        )
    editor = service.resolve_actor(
        TrustedActor(
            actor_id=viewer.actor.actor_id,
            actor_kind="member",
            space_id=context.actor.space_id,
        ),
        grant_id=viewer.grant_id,
    )
    append_file(
        service.authority,
        docs,
        editor,
        first_draft,
        first.version,
        "one.txt",
        "text/plain",
        b"one fixture",
        "editor",
    )
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.business_client_grants set revoked_at=clock_timestamp() where id=%s",
            (editor.grant_id,),
        )
    with pytest.raises(ActionError):
        append_file(
            service.authority,
            docs,
            editor,
            first_draft,
            first.version,
            "one.txt",
            "text/plain",
            b"one fixture",
            "editor",
        )


def test_concurrent_supporting_replay_has_one_source_and_history(actions, documents):
    service, context, _ = actions
    docs, _ = documents
    draft = shared.ready(service, context)
    before = service.dossier(context, draft)

    def append(_):
        return append_file(
            service.authority,
            docs,
            context,
            draft,
            before.version,
            "same.txt",
            "text/plain",
            b"concurrent fixture",
            "same-key",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(append, range(2)))
    assert results[0] == results[1]
    after = service.dossier(context, draft)
    assert len(after.history) == len(before.history) + 1
    assert len(after.sources) == len(before.sources) + 1


@pytest.mark.parametrize("kind", ["note", "file"])
def test_closed_business_cannot_replay_annotation(actions, documents, kind):
    service, context, _ = actions
    docs, _ = documents
    draft = shared.ready(service, context)
    if kind == "note":

        def command():
            return edit_note(
                service.authority,
                context,
                draft,
                EditCurrentNote(expected_version=1, note="closed"),
                "closed",
            )
    else:

        def command():
            return append_file(
                service.authority,
                docs,
                context,
                draft,
                1,
                "closed.txt",
                "text/plain",
                b"closed fixture",
                "closed",
            )

    command()
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.spaces set closed_at=clock_timestamp() where id=%s",
            (context.actor.space_id,),
        )
    with pytest.raises(ActionError):
        command()


def test_append_to_another_existing_business_is_refused(actions, documents, users):
    from tests.test_business_spaces_migration_postgres import owned_space

    service, context, _ = actions
    docs, _ = documents
    with service.authority.pool.connection() as db:
        other_space = owned_space(db, users["other"])
    other = service.resolve_actor(
        TrustedActor(actor_id=users["other"], actor_kind="member", space_id=other_space)
    )
    draft = shared.ready(service, other)
    before = service.dossier(other, draft)
    with pytest.raises(ActionError, match="business_record_not_found"):
        append_file(
            service.authority,
            docs,
            context,
            draft,
            1,
            "foreign.txt",
            "text/plain",
            b"foreign fixture",
            "foreign",
        )
    assert service.dossier(other, draft) == before


def test_note_nonhuman_and_append_source_disconnect_are_refused(actions, documents):
    from dataclasses import replace

    service, context, _ = actions
    docs, _ = documents
    draft = shared.ready(service, context)
    agent = replace(
        context, actor=context.actor.model_copy(update={"actor_kind": "owner_via_agent"})
    )
    with pytest.raises(ActionError, match="business_human_command_required"):
        edit_note(
            service.authority,
            agent,
            draft,
            EditCurrentNote(expected_version=1, note="not human"),
            "agent",
        )
    result = append_file(
        service.authority,
        docs,
        context,
        draft,
        1,
        "source.txt",
        "text/plain",
        b"source fixture",
        "source",
    )
    docs.hub.connections.disconnect(
        user_id=context.owner_id,
        connection_id=str(result.receipt_id),
        now=datetime.now(timezone.utc),
    )
    with pytest.raises(ActionError, match="document_source_unavailable"):
        append_file(
            service.authority,
            docs,
            context,
            draft,
            1,
            "source.txt",
            "text/plain",
            b"source fixture",
            "source",
        )
