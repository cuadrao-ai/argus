from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import get_args
from uuid import UUID, uuid4

import pytest
from argus.domain.business.access import AccessAction
from argus.domain.business.activity.catalog import (
    CATALOG,
    READ_MARKS,
    excluded_actions,
    project,
)
from argus.domain.business.activity.queries import (
    Cursor,
    InvalidCursor,
    decode_cursor,
    encode_cursor,
)
from argus.domain.business.contracts.activity import ActivityAction

AT = datetime(2026, 10, 27, 15, 4, 5, 123456, tzinfo=timezone.utc)
ITEM_ID = "f" * 32
DRAFT = uuid4()
ACTOR = {
    "actor_id": str(uuid4()),
    "actor_kind": "member",
    "display_name": "Ana",
    "grant_id": str(uuid4()),
    "issuer_id": str(uuid4()),
    "issuer_display_name": "Luis",
}
ACCESS_CHANGES = {
    "owner_grant",
    "grant_access",
    "invite_access",
    "accept_invite",
    "revoke_grant",
    "revoke_invite",
    "change_role",
}


def row(command: dict, outcome: dict | None = None, **actor: str) -> dict:
    return {
        "id": ITEM_ID,
        "created_at": AT,
        "actor": {**ACTOR, **actor},
        "command": command,
        "outcome": {"outcome": "applied"} if outcome is None else outcome,
    }


def test_every_listed_action_is_in_the_enum_and_no_read_mark_is():
    assert set(CATALOG) == set(get_args(ActivityAction)) - {"other"}
    assert not READ_MARKS & set(CATALOG)


def test_every_access_action_is_a_manager_change_or_a_read_mark():
    managed = {name for name, spec in CATALOG.items() if spec.audience == "manager"}
    assert managed == set(get_args(AccessAction)) - READ_MARKS


def test_a_member_never_gets_access_changes_and_a_manager_gets_every_change():
    assert set(excluded_actions(manager=True)) == READ_MARKS
    assert set(excluded_actions(manager=False)) == READ_MARKS | ACCESS_CHANGES


@pytest.mark.parametrize(
    ("command", "outcome", "expected"),
    [
        (
            {"action": "review_draft", "draft_id": str(uuid4())},
            {"outcome": "applied", "draft_id": str(DRAFT)},
            ("draft", DRAFT),
        ),
        ({"action": "settle_remainder", "draft_id": str(DRAFT)}, None, ("draft", DRAFT)),
        (
            {
                "action": "business_propose_activity",
                "draft": {"draft_id": str(DRAFT), "version": 1},
            },
            None,
            ("draft", DRAFT),
        ),
        ({"action": "business_attach_source", "draft": {"from_action": 0}}, None, None),
        (
            {"action": "invite_access", "invite_id": str(DRAFT), "email": "x@y.test"},
            None,
            ("invite", DRAFT),
        ),
        ({"action": "change_role", "grant_id": str(DRAFT)}, None, ("grant", DRAFT)),
        ({"action": "review_draft", "draft_id": "not-a-uuid"}, None, None),
        ({"action": "receipt_review", "subjects": [str(DRAFT)]}, None, None),
        ({"action": "receipt_upload", "subjects": [str(DRAFT)]}, None, None),
        ({"action": "email_ai_consent_declined"}, None, None),
    ],
)
def test_the_object_is_the_server_owned_id_when_one_is_known(
    command: dict, outcome: dict | None, expected: tuple[str, UUID] | None
):
    item = project(row(command, outcome))
    assert item.action == command["action"]
    assert (
        None if item.object is None else (item.object.kind, item.object.id)
    ) == expected


@pytest.mark.parametrize(
    "command",
    [
        {"action": "business_future_action", "draft_id": str(DRAFT)},
        {"action": 7},
        {"no_action": True},
        {"action": ["review_draft"]},
    ],
)
def test_an_action_the_feed_does_not_know_is_other_with_no_object(command: dict):
    item = project(row(command))
    assert (item.action, item.object) == ("other", None)


def test_the_item_carries_the_stored_name_and_only_the_promised_fields():
    item = project(
        row({"action": "review_draft", "draft_id": str(DRAFT)}, display_name="Exmiembro")
    )
    dumped = json.loads(item.model_dump_json())
    assert set(dumped) == {"id", "occurred_at", "actor", "action", "object"}
    assert dumped["actor"] == {"display_name": "Exmiembro", "kind": "member"}
    assert dumped["object"] == {"kind": "draft", "id": str(DRAFT)}
    text = item.model_dump_json()
    assert ACTOR["actor_id"] not in text
    assert ACTOR["grant_id"] not in text
    assert "Luis" not in text


def _cursor(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def test_a_cursor_round_trips_and_one_the_feed_did_not_issue_is_refused():
    item = project(row({"action": "review_draft"}))
    assert decode_cursor(encode_cursor(item)) == Cursor(AT, ITEM_ID)
    shifted = item.model_copy(
        update={"occurred_at": AT.astimezone(timezone(timedelta(hours=-4)))}
    )
    assert decode_cursor(encode_cursor(shifted)) == Cursor(AT, ITEM_ID)
    assert decode_cursor(encode_cursor(shifted)).occurred_at.utcoffset() == timedelta(0)
    for cursor in (
        "",
        "not base64 !!",
        _cursor("no separator"),
        _cursor(f"2026-10-27T15:04:05|{ITEM_ID}"),
        _cursor("2026-10-27T15:04:05+00:00|short"),
        _cursor(f"2026-10-27T15:04:05+00:00|{'g' * 32}"),
        _cursor(f"yesterday|{ITEM_ID}"),
    ):
        with pytest.raises(InvalidCursor):
            decode_cursor(cursor)
