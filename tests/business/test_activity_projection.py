from __future__ import annotations

import base64
import json
from datetime import date, datetime, timedelta, timezone
from types import UnionType
from typing import Annotated, Literal, Union, get_args, get_origin
from uuid import UUID, uuid4

import pytest
from argus.domain.business.access import AccessAction
from argus.domain.business.activity.catalog import (
    ACTIONS,
    CATALOG,
    DERIVED,
    PERSONAL_STATE,
    READ_MARKS,
    UNLISTED,
    Visibility,
    project,
    selected,
    visibility,
    with_labels,
)
from argus.domain.business.activity.queries import (
    Cursor,
    InvalidCursor,
    day_bounds,
    decode_cursor,
    encode_cursor,
    fingerprint,
)
from argus.domain.business.annotations import NoteCommand
from argus.domain.business.contracts.actions import Command
from argus.domain.business.contracts.activity import (
    ActionGroup,
    ActivityAction,
    ActivityFilters,
    Area,
)
from argus.domain.business.fiscal_profile import FiscalProfileChange
from argus.domain.business.roles import BusinessRole
from argus.domain.business.supporting_files import SupportingCommand
from argus.domain.business.transactions import LegacyAction
from pydantic import ValidationError

AT = datetime(2026, 10, 27, 15, 4, 5, 123456, tzinfo=timezone.utc)
ITEM_ID = "f" * 32
ACTOR_KEY = "a" * 32
DRAFT = uuid4()
ACCESS_CHANGES = {
    "owner_grant",
    "grant_access",
    "invite_access",
    "accept_invite",
    "revoke_grant",
    "revoke_invite",
    "change_role",
}
MANAGER_ONLY = ACCESS_CHANGES | set(DERIVED)
NONE = ActivityFilters()


def row(command: dict, outcome: dict | None = None, **actor: object) -> dict:
    return {
        "id": ITEM_ID,
        "created_at": AT,
        "actor_key": ACTOR_KEY,
        "actor_kind": "member",
        "display_name": "Ana",
        "membership": "current",
        "action": command.get("action"),
        "command": command,
        "outcome": {"outcome": "applied"} if outcome is None else outcome,
        **actor,
    }


def test_every_listed_action_is_in_the_enum_and_no_unlisted_one_is():
    assert set(ACTIONS) == set(get_args(ActivityAction)) - {"other"}
    assert not set(CATALOG) & set(DERIVED)
    assert not UNLISTED & set(ACTIONS)
    assert not UNLISTED & set(get_args(ActivityAction))
    assert "email_ai_consent_declined" in PERSONAL_STATE


def test_every_action_has_a_catalog_area_and_group():
    for name, spec in ACTIONS.items():
        assert spec.area in get_args(Area), name
        assert spec.group in get_args(ActionGroup), name
    assert {spec.area for spec in ACTIONS.values()} == {
        "documents",
        "records",
        "business",
    }
    assert {spec.group for spec in ACTIONS.values()} == set(get_args(ActionGroup)) - {
        "invoices"
    }
    assert {name for name, spec in ACTIONS.items() if spec.audience == "manager"} == (
        MANAGER_ONLY
    )


def test_every_access_action_is_a_manager_change_or_a_read_mark():
    managed = {name for name, spec in CATALOG.items() if spec.audience == "manager"}
    assert managed == set(get_args(AccessAction)) - READ_MARKS


def test_a_member_sees_only_listed_changes_and_a_manager_everything_but_unlisted():
    member = visibility(manager=False, filters=NONE)
    assert member.only is not None
    assert set(member.only) == set(ACTIONS) - MANAGER_ONLY
    assert "email_ai_consent_declined" not in member.only
    assert member.hidden == ()
    manager = Visibility(only=None, hidden=tuple(sorted(UNLISTED)))
    assert visibility(manager=True, filters=NONE) == manager
    assert "email_ai_consent_declined" in manager.hidden


def test_an_area_or_group_filter_is_or_within_and_and_across():
    documents = selected(ActivityFilters(areas=("documents",)))
    assert documents == {name for name, s in ACTIONS.items() if s.area == "documents"}
    both = selected(ActivityFilters(areas=("documents", "business")))
    assert both == documents | {n for n, s in ACTIONS.items() if s.area == "business"}
    crossed = selected(ActivityFilters(areas=("documents",), groups=("files",)))
    assert crossed == {
        "rebind_attachment",
        "append_supporting_file",
        "business_attach_source",
    }
    assert selected(ActivityFilters(areas=("invoicing",))) == set()
    assert selected(NONE) == set(ACTIONS)


def test_a_filtered_manager_page_names_only_catalog_actions_so_other_never_matches():
    filtered = visibility(manager=True, filters=ActivityFilters(groups=("access",)))
    assert filtered.only is not None
    assert set(filtered.only) == ACCESS_CHANGES | {"ownership_transferred"}
    assert filtered.hidden == ()
    member = visibility(manager=False, filters=ActivityFilters(groups=("access",)))
    assert member.only == ()
    settings = visibility(manager=False, filters=ActivityFilters(groups=("settings",)))
    assert settings.only == ("set_business_rnc",)


def _action_names(annotation: object) -> set[str]:
    origin = get_origin(annotation)
    if origin is Annotated:
        return _action_names(get_args(annotation)[0])
    if origin in (Union, UnionType):
        return set().union(*(_action_names(member) for member in get_args(annotation)))
    if origin is Literal:
        return set(get_args(annotation))
    return _action_names(annotation.model_fields["action"].annotation)


TYPED_LEDGER_ACTIONS = (
    _action_names(Command)
    | _action_names(AccessAction)
    | _action_names(FiscalProfileChange)
    | _action_names(NoteCommand)
    | _action_names(SupportingCommand)
    | _action_names(LegacyAction)
)
#: In the ledger's allow-list (20261014100000) with no Python command type.
UNTYPED_LEDGER_ACTIONS = frozenset({"email_ai_consent_declined"})


def test_every_typed_ledger_action_has_a_catalog_decision():
    assert len(TYPED_LEDGER_ACTIONS) > 20
    assert TYPED_LEDGER_ACTIONS <= set(CATALOG) | UNLISTED
    assert set(CATALOG) | UNLISTED == TYPED_LEDGER_ACTIONS | UNTYPED_LEDGER_ACTIONS
    assert not set(DERIVED) & TYPED_LEDGER_ACTIONS


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
            {
                "action": "business_ask",
                "draft": {"from_action": 0},
                "field": "amount",
                "asked_of": "owner",
                "prompt": "Cuanto fue en total",
            },
            {
                "outcome": "applied",
                "draft_id": str(DRAFT),
                "version": 1,
                "question_id": str(uuid4()),
            },
            ("draft", DRAFT),
        ),
        (
            {"action": "invite_access", "invite_id": str(DRAFT), "email": "x@y.test"},
            None,
            ("invite", DRAFT),
        ),
        ({"action": "change_role", "grant_id": str(DRAFT)}, None, ("grant", DRAFT)),
        ({"action": "review_draft", "draft_id": "not-a-uuid"}, None, None),
        ({"action": "receipt_review", "subjects": [str(DRAFT)]}, None, None),
        ({"action": "receipt_upload", "subjects": [str(DRAFT)]}, None, None),
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
    assert item.object is None or item.object.label is None


def test_the_area_and_restriction_come_from_the_catalog():
    assert (project(row({"action": "review_draft"})).area, False) == ("records", False)
    grant = project(row({"action": "revoke_grant", "grant_id": str(DRAFT)}))
    assert (grant.area, grant.restricted) == ("business", True)
    upload = project(row({"action": "receipt_upload"}))
    assert (upload.area, upload.restricted) == ("documents", False)
    transfer = project(row({"action": "ownership_transferred"}))
    assert (transfer.area, transfer.restricted, transfer.object) == (
        "business",
        True,
        None,
    )


@pytest.mark.parametrize(
    ("command", "field", "expected"),
    [
        (
            {"action": "grant_access", "grant_id": str(DRAFT), "business_role": "admin"},
            "role",
            BusinessRole.ADMIN,
        ),
        (
            {
                "action": "invite_access",
                "invite_id": str(DRAFT),
                "business_role": "viewer",
            },
            "role",
            BusinessRole.VIEWER,
        ),
        (
            {"action": "change_role", "grant_id": str(DRAFT), "business_role": "editor"},
            "role",
            BusinessRole.EDITOR,
        ),
        (
            {"action": "change_role", "grant_id": str(DRAFT), "business_role": "god"},
            "role",
            None,
        ),
        (
            {"action": "owner_grant", "grant_id": str(DRAFT), "business_role": "owner"},
            "role",
            None,
        ),
        (
            {
                "action": "mark_personal",
                "draft_id": str(DRAFT),
                "request": {"personal": True},
            },
            "personal",
            True,
        ),
        (
            {
                "action": "mark_personal",
                "draft_id": str(DRAFT),
                "request": {"personal": False},
            },
            "personal",
            False,
        ),
        (
            {
                "action": "mark_personal",
                "draft_id": str(DRAFT),
                "request": {"personal": 1},
            },
            "personal",
            None,
        ),
        (
            {
                "action": "decide_606",
                "draft_id": str(DRAFT),
                "request": {"include": False},
            },
            "include",
            False,
        ),
        (
            {"action": "decide_606", "draft_id": str(DRAFT), "request": {}},
            "include",
            None,
        ),
        (
            {
                "action": "review_draft",
                "draft_id": str(DRAFT),
                "request": {"personal": True},
            },
            "personal",
            None,
        ),
    ],
)
def test_the_typed_detail_is_read_from_the_stored_command(command, field, expected):
    item = project(row(command))
    assert getattr(item, field) == expected
    assert {
        f for f in ("role", "personal", "include") if getattr(item, f) is not None
    } <= {field}


@pytest.mark.parametrize(
    "command",
    [
        {"action": "business_future_action", "draft_id": str(DRAFT)},
        {"action": "email_ai_consent_declined"},
        {"action": 7},
        {"no_action": True},
        {"action": ["review_draft"]},
    ],
)
def test_an_action_the_feed_does_not_know_is_other_with_no_object(command: dict):
    item = project(row(command))
    assert (item.action, item.object, item.area, item.restricted) == (
        "other",
        None,
        None,
        True,
    )


def test_the_item_carries_the_stored_name_and_only_the_promised_fields():
    item = project(
        row({"action": "review_draft", "draft_id": str(DRAFT)}, display_name="Exmiembro")
    )
    dumped = json.loads(item.model_dump_json())
    assert set(dumped) == {
        "id",
        "occurred_at",
        "actor",
        "action",
        "object",
        "area",
        "restricted",
        "role",
        "personal",
        "include",
    }
    assert dumped["actor"] == {
        "display_name": "Exmiembro",
        "kind": "member",
        "id": ACTOR_KEY,
        "membership": "current",
    }
    assert dumped["object"] == {"kind": "draft", "id": str(DRAFT), "label": None}


def test_a_row_with_no_recorded_name_has_no_actor_and_an_extractor_no_membership():
    unnamed = project(row({"action": "ownership_transferred"}, display_name=None))
    assert unnamed.actor is None
    former = project(row({"action": "review_draft"}, membership="former"))
    assert former.actor is not None and former.actor.membership == "former"
    read = project(
        row({"action": "prepare_attachment"}, actor_kind="extractor", membership=None)
    )
    assert read.actor is not None
    assert (read.actor.kind, read.actor.membership, read.area) == (
        "extractor",
        None,
        "documents",
    )


def test_a_label_attaches_to_the_object_it_names_and_to_nothing_else():
    item = project(row({"action": "review_draft", "draft_id": str(DRAFT)}))
    labelled = with_labels(item, {("draft", DRAFT): "Ferretería Popular"})
    assert labelled.object is not None and labelled.object.label == "Ferretería Popular"
    assert with_labels(item, {("grant", DRAFT): "Ana"}).object.label is None
    assert with_labels(item, {}) == item
    plain = project(row({"action": "receipt_upload"}))
    assert with_labels(plain, {("draft", DRAFT): "x"}) == plain


def test_filters_canonicalize_and_refuse_a_reversed_range():
    filters = ActivityFilters(
        actors=("b" * 32, "a" * 32, "b" * 32),
        areas=("records", "documents", "records"),
        groups=("edits", "access"),
    )
    assert filters.actors == ("a" * 32, "b" * 32)
    assert filters.areas == ("documents", "records")
    assert filters.groups == ("access", "edits")
    with pytest.raises(ValidationError):
        ActivityFilters(since=date(2026, 10, 28), until=date(2026, 10, 27))
    with pytest.raises(ValidationError):
        ActivityFilters(actors=("not-an-id",))
    with pytest.raises(ValidationError):
        ActivityFilters(areas=("mail",))
    assert ActivityFilters(since=date(2026, 10, 27), until=date(2026, 10, 27))


def test_day_bounds_are_whole_days_in_the_business_time_zone():
    since, until = day_bounds(
        ActivityFilters(since=date(2026, 10, 27), until=date(2026, 10, 27))
    )
    assert since == datetime(2026, 10, 27, 4, 0, tzinfo=timezone.utc)
    assert until == datetime(2026, 10, 28, 4, 0, tzinfo=timezone.utc)
    assert day_bounds(NONE) == (None, None)
    assert day_bounds(ActivityFilters(until=date(2026, 1, 1)))[0] is None


def _cursor(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def test_a_cursor_round_trips_only_with_the_filters_that_issued_it():
    item = project(row({"action": "review_draft"}))
    filters = ActivityFilters(areas=("records",), since=date(2026, 10, 1))
    issued = encode_cursor(item, filters)
    assert decode_cursor(issued, filters) == Cursor(AT, ITEM_ID, fingerprint(filters))
    same = ActivityFilters(areas=("records", "records"), since=date(2026, 10, 1))
    assert decode_cursor(issued, same).id == ITEM_ID
    for other in (
        NONE,
        ActivityFilters(areas=("records",)),
        ActivityFilters(areas=("records",), since=date(2026, 10, 2)),
        ActivityFilters(areas=("records",), since=date(2026, 10, 1), actors=("a" * 32,)),
    ):
        with pytest.raises(InvalidCursor):
            decode_cursor(issued, other)
    shifted = item.model_copy(
        update={"occurred_at": AT.astimezone(timezone(timedelta(hours=-4)))}
    )
    assert decode_cursor(encode_cursor(shifted, NONE), NONE) == Cursor(
        AT, ITEM_ID, fingerprint(NONE)
    )
    assert decode_cursor(encode_cursor(shifted, NONE), NONE).occurred_at.utcoffset() == (
        timedelta(0)
    )
    for cursor in (
        "",
        "not base64 !!",
        _cursor("no separator"),
        _cursor(f"2026-10-27T15:04:05+00:00|{ITEM_ID}"),
        _cursor(f"2026-10-27T15:04:05|{ITEM_ID}|{fingerprint(NONE)}"),
        _cursor(f"2026-10-27T15:04:05+00:00|short|{fingerprint(NONE)}"),
        _cursor(f"2026-10-27T15:04:05+00:00|{'g' * 32}|{fingerprint(NONE)}"),
        _cursor(f"yesterday|{ITEM_ID}|{fingerprint(NONE)}"),
    ):
        with pytest.raises(InvalidCursor):
            decode_cursor(cursor, NONE)
