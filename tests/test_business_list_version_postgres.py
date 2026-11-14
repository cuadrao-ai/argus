"""The Business's list version moves with every write the lists show, and
stays put when nothing was written (#2033). Real Postgres; values made up."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from argus.api.business_list_version import etag, stored_version
from argus.api.routers.business import list_receipts
from argus.domain.business.contracts.actions import ReopenDraft
from argus.domain.business.list_version import (
    LIST_VERSION_TABLES,
    WINDOW_SECONDS,
    list_version,
    records_mark,
)
from starlette.requests import Request
from starlette.responses import Response

from tests import test_business_actions_postgres as shared
from tests import test_business_document_delete_postgres as deleting

users = shared.users
actions = shared.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]


def _mark(service, context) -> str:
    return records_mark(
        service.authority.pool,
        space_id=str(context.actor.space_id),
        person_id=str(context.owner_id),
    )


class _Moves:
    """Each step must move the mark, and a second look must not."""

    def __init__(self, service, context) -> None:
        self.service, self.context = service, context
        self.seen = [_mark(service, context)]

    def after(self, step: str) -> None:
        mark = _mark(self.service, self.context)
        assert mark not in self.seen, f"{step} left the list version as it was"
        assert _mark(self.service, self.context) == mark, f"{step}: unstable"
        self.seen.append(mark)


def test_upload_and_a_finished_read_each_move_the_version(actions):
    service, context, _ = actions
    moves = _Moves(service, context)
    _, _, cid, _, web = deleting._unread(actions)
    moves.after("upload")
    draft = web.service.documents.store.draft(user_id=context.owner_id, connection_id=cid)
    web.service.documents._update(
        context.owner_id, draft, holder=None, status="needs_attention", error_code=None
    )
    moves.after("a read that finished")


def test_approve_reopen_delete_restore_and_purge_each_move_the_version(actions):
    service, context, _ = actions
    moves = _Moves(service, context)
    draft_id = deleting._captured_purchase(service, context)
    moves.after("a typed note")
    approved = deleting._captured_purchase(service, context, approve=True)
    moves.after("approve")
    version = service.dossier(context, approved).version
    reopened = service.reopen(
        context, approved, ReopenDraft(version=version), str(uuid4())
    )
    assert reopened.outcome == "applied", reopened
    moves.after("reopen")
    client = deleting._client(service, context)
    for action in ("delete", "restore", "delete", "purge"):
        assert deleting._act(client, draft_id, action).status_code == 200
        moves.after(action)


def test_a_finished_bridge_read_moves_the_version(actions):
    service, context, _ = actions
    before = _mark(service, context)
    deleting._ready(actions)
    assert _mark(service, context) != before


def test_one_person_seeing_a_receipt_moves_only_their_version(actions, users):
    service, context, cid, _, web = deleting._ready(actions)
    other = lambda: records_mark(  # noqa: E731
        service.authority.pool,
        space_id=str(context.actor.space_id),
        person_id=users["other"],
    )
    mine, theirs = _mark(service, context), other()
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_receipt_read_states"
            "(space_id,person_id,connection_id,completion_cursor) values (%s,%s,%s,%s)",
            (context.actor.space_id, context.owner_id, cid, "0" * 64),
        )
    assert _mark(service, context) != mine
    assert other() == theirs


def test_another_business_never_moves_this_one(actions, users):
    service, context, _ = actions
    elsewhere = lambda: records_mark(  # noqa: E731
        service.authority.pool, space_id=str(uuid4()), person_id=users["owner"]
    )
    before = elsewhere()
    deleting._captured_purchase(service, context)
    assert elsewhere() == before


def test_the_version_names_the_person_their_capabilities_and_the_window():
    now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    base = {"space_id": "s", "person_id": "p", "capabilities": ("read",), "now": now}
    version = list_version("m", **base)
    assert version == list_version("m", **{**base, "now": now + timedelta(seconds=1)})
    assert version != list_version("other", **base)
    assert version != list_version("m", **{**base, "person_id": "q"})
    assert version != list_version("m", **{**base, "capabilities": ("read", "approve")})
    later = now + timedelta(seconds=WINDOW_SECONDS)
    assert version != list_version("m", **{**base, "now": later})


def _request(version: str | None = None) -> Request:
    headers = [(b"if-none-match", version.encode())] if version else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def test_the_receipts_route_answers_no_change_from_the_stored_version(actions):
    service, context, cid, _, web = deleting._ready(actions)
    held = etag(stored_version(web))

    same = list_receipts(_request(held), Response(), "inbox", held, web)
    assert (same.status_code, same.body, same.headers["etag"]) == (304, b"", held)

    deleting._captured_purchase(service, context)
    fresh = Response()
    page = list_receipts(_request(held), fresh, "inbox", held, web)
    assert [item["id"] for item in page["items"]] == [cid]
    assert fresh.headers["etag"] not in (held, "")


def test_the_statement_reads_only_the_tables_it_names():
    from argus.domain.business import list_version as owner

    for table in LIST_VERSION_TABLES:
        assert table in owner._STATEMENT
    assert (
        owner._STATEMENT.count(" from ") + owner._STATEMENT.count(" join ")
        == len(LIST_VERSION_TABLES) + 1
    )
