"""Durable once-only semantics for guest funnel milestone events (#376).

Duplicate milestones inflate acquisition conversion counts in one direction, so
the guarantee is a claim per subject rather than a count the caller happens to
read. The real cross-process guarantee is the ``guest_funnel_milestones``
primary key and is proven in ``test_guest_funnel_milestones_postgres.py``; these
cover the policy layer that decides what is claimed and against which subject.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import get_args
from unittest.mock import patch

import pytest
from argus.api import state as api_state
from argus.api.guest_access import (
    account_context,
    guest_account_context,
    store_account_context,
)
from argus.api.guest_observability import (
    emit_guest_funnel_event,
    emit_guest_turn_funnel_events,
    emit_verified_guest_funnel_event,
    milestone_emission_allowed,
)
from argus.domain.guest_funnel_milestones import (
    MILESTONE_RETENTION,
    claim_memory_milestone,
    purge_memory_milestones,
)
from argus.domain.guest_workspaces import GuestWorkspace
from argus.domain.visitor_usage import visitor_key_for
from argus.observability.guest_funnel import (
    GUEST_FUNNEL_EVENT_MAP,
    MILESTONE_EVENT_KINDS,
    GuestFunnelEventKind,
    build_guest_funnel_event,
    milestone_subject,
)
from fastapi import Request

VISITOR_KEY = visitor_key_for("203.0.113.7")
OTHER_VISITOR_KEY = visitor_key_for("198.51.100.4")
FIRST_GUEST_USER_ID = "00000000-0000-0000-0000-0000000003a1"
RENEWED_GUEST_USER_ID = "00000000-0000-0000-0000-0000000003a2"


def _guest_context(user_id: str, *, visitor_key: str | None = VISITOR_KEY):
    created_at = datetime.now(timezone.utc)
    return guest_account_context(
        GuestWorkspace(
            user_id=user_id,
            conversation_id="conversation-1",
            status="active",
            created_at=created_at,
            expires_at=created_at + timedelta(days=7),
            claimed_by=None,
            claimed_at=None,
            updated_at=created_at,
        ),
        visitor_key=visitor_key,
    )


def _emit_first_result(account, *, message_id: str = "message-1") -> None:
    emit_guest_funnel_event(
        account=account,
        kind="first_useful_assistant_response_completed",
        user_id=account.user_id,
        conversation_id="conversation-1",
        message_id=message_id,
        surface="chat",
        product_capability="chat",
        terminal_outcome="completed",
    )


def test_the_same_milestone_emitted_twice_records_exactly_one_event() -> None:
    account = _guest_context(FIRST_GUEST_USER_ID)

    with patch("argus.api.guest_observability.capture_guest_funnel_event") as capture:
        _emit_first_result(account, message_id="message-1")
        _emit_first_result(account, message_id="message-2")

    assert capture.call_count == 1
    assert (
        capture.call_args_list[0].args[0] == "first_useful_assistant_response_completed"
    )
    assert capture.call_args_list[0].kwargs["message_id"] == "message-1"


def test_a_duplicate_attempt_is_a_silent_no_op() -> None:
    account = _guest_context(FIRST_GUEST_USER_ID)

    with patch("argus.api.guest_observability.capture_guest_funnel_event"):
        _emit_first_result(account)
        # A retried request must not fail because it already succeeded.
        _emit_first_result(account)


def test_workspace_renewal_does_not_reemit_a_reached_milestone() -> None:
    """Renewal mints a fresh user id; the visitor is the same person."""
    reached = _guest_context(FIRST_GUEST_USER_ID)
    renewed = _guest_context(RENEWED_GUEST_USER_ID)
    assert reached.user_id != renewed.user_id
    assert reached.visitor_key == renewed.visitor_key

    with patch("argus.api.guest_observability.capture_guest_funnel_event") as capture:
        _emit_first_result(reached)
        _emit_first_result(renewed)

    assert capture.call_count == 1


def test_a_different_visitor_still_reaches_the_same_milestone() -> None:
    reached = _guest_context(FIRST_GUEST_USER_ID)
    other = _guest_context(RENEWED_GUEST_USER_ID, visitor_key=OTHER_VISITOR_KEY)

    with patch("argus.api.guest_observability.capture_guest_funnel_event") as capture:
        _emit_first_result(reached)
        _emit_first_result(other)

    assert capture.call_count == 2


@pytest.mark.parametrize("kind", sorted(MILESTONE_EVENT_KINDS))
def test_every_milestone_kind_is_claimed_once_per_subject(kind: str) -> None:
    account = _guest_context(FIRST_GUEST_USER_ID)

    with patch("argus.api.guest_observability.capture_guest_funnel_event") as capture:
        for _ in range(3):
            emit_guest_funnel_event(
                account=account,
                kind=kind,
                user_id=account.user_id,
                surface="chat",
            )

    assert capture.call_count == 1


def test_milestone_kinds_are_part_of_the_funnel_taxonomy() -> None:
    assert MILESTONE_EVENT_KINDS <= set(GUEST_FUNNEL_EVENT_MAP)
    assert MILESTONE_EVENT_KINDS <= set(get_args(GuestFunnelEventKind))


def test_chat_turn_owner_still_records_the_first_useful_response():
    account = _guest_context(FIRST_GUEST_USER_ID)

    with (
        patch(
            "argus.api.guest_observability.current_guest_usage_count",
            return_value=1,
        ),
        patch("argus.api.guest_observability.capture_guest_funnel_event") as capture,
    ):
        emit_guest_turn_funnel_events(
            account=account,
            user_id=account.user_id,
            conversation_id="conversation-1",
            language="en",
            assistant_message_id="message-1",
            is_run_backtest_turn=False,
        )
        emit_guest_turn_funnel_events(
            account=account,
            user_id=account.user_id,
            conversation_id="conversation-1",
            language="en",
            assistant_message_id="message-2",
            is_run_backtest_turn=True,
        )

    assert [call.args[0] for call in capture.call_args_list] == [
        "first_useful_assistant_response_completed",
    ]


def test_conversion_owner_still_records_the_claim_milestone() -> None:
    with patch("argus.api.guest_observability.capture_guest_funnel_event") as capture:
        for _ in range(2):
            emit_verified_guest_funnel_event(
                "existing_account_sign_in_completed",
                user_id=FIRST_GUEST_USER_ID,
                visitor_key=VISITOR_KEY,
                conversation_id="conversation-1",
                surface="account_conversion",
                product_capability="account",
            )

    assert [call.args[0] for call in capture.call_args_list] == [
        "existing_account_sign_in_completed",
    ]
    assert "visitor_key" not in capture.call_args_list[0].kwargs


def test_the_visitor_key_never_reaches_the_emitted_event() -> None:
    """The subject is an IP-derived digest: it decides what is emitted, and is
    never part of what is emitted."""
    account = _guest_context(FIRST_GUEST_USER_ID)

    with patch("argus.api.guest_observability.capture_guest_funnel_event") as capture:
        _emit_first_result(account)

    assert capture.call_count == 1
    assert "visitor_key" not in capture.call_args_list[0].kwargs
    assert VISITOR_KEY not in str(capture.call_args_list[0])

    envelope = build_guest_funnel_event(
        "first_useful_assistant_response_completed",
        user_id=FIRST_GUEST_USER_ID,
        surface="chat",
    )
    assert VISITOR_KEY not in json.dumps(envelope.model_dump(mode="json"), default=str)


def test_an_unbound_visitor_falls_back_to_the_actor_subject() -> None:
    account = _guest_context(FIRST_GUEST_USER_ID, visitor_key=None)

    with patch("argus.api.guest_observability.capture_guest_funnel_event") as capture:
        _emit_first_result(account)
        _emit_first_result(account)

    assert capture.call_count == 1
    subject_key = milestone_subject(visitor_key=None, user_id=FIRST_GUEST_USER_ID)
    assert subject_key is not None and subject_key.startswith("actor:")
    assert (subject_key, "first_useful_assistant_response_completed") in (
        api_state.store.guest_funnel_milestones
    )
    # Namespaced apart from visitor subjects, so the two can never collide.
    assert not subject_key.startswith("visitor:")
    assert VISITOR_KEY.startswith("visitor:")


def test_a_milestone_with_no_resolvable_subject_is_suppressed() -> None:
    assert (
        milestone_emission_allowed(
            "first_useful_assistant_response_completed",
            user_id="",
            visitor_key=None,
        )
        is False
    )


def test_a_failed_claim_suppresses_the_milestone() -> None:
    """Duplicates bias the funnel one way; a lost milestone during an outage
    does not."""
    account = _guest_context(FIRST_GUEST_USER_ID)

    with (
        patch(
            "argus.api.guest_observability._claim_milestone",
            side_effect=RuntimeError("claim store unavailable"),
        ),
        patch("argus.api.guest_observability.capture_guest_funnel_event") as capture,
    ):
        _emit_first_result(account)

    capture.assert_not_called()


def test_a_bound_account_context_supplies_the_subject_without_threading() -> None:
    """emit_verified sites that only carry a user id still claim per visitor.

    Bound through the real request path rather than a patch, because that
    binding is what the admission flow relies on.
    """
    account = _guest_context(FIRST_GUEST_USER_ID)
    request = Request({"type": "http", "headers": [], "method": "POST", "path": "/"})
    store_account_context(request, account)
    assert account_context(request) is account

    with patch("argus.api.guest_observability.capture_guest_funnel_event") as capture:
        for _ in range(2):
            emit_verified_guest_funnel_event(
                "account_creation_completed",
                user_id=account.user_id,
            )

    assert capture.call_count == 1
    assert (VISITOR_KEY, "account_creation_completed") in (
        api_state.store.guest_funnel_milestones
    )


def test_a_mismatched_account_context_never_supplies_another_subject() -> None:
    other = _guest_context(RENEWED_GUEST_USER_ID, visitor_key=OTHER_VISITOR_KEY)

    with patch(
        "argus.api.guest_observability.current_account_context",
        return_value=other,
    ):
        allowed = milestone_emission_allowed(
            "first_useful_assistant_response_completed",
            user_id=FIRST_GUEST_USER_ID,
        )

    assert allowed is True
    assert (OTHER_VISITOR_KEY, "first_useful_assistant_response_completed") not in (
        api_state.store.guest_funnel_milestones
    )


def test_milestone_subject_prefers_the_visitor_over_the_user() -> None:
    assert (
        milestone_subject(visitor_key=VISITOR_KEY, user_id=FIRST_GUEST_USER_ID)
        == VISITOR_KEY
    )
    assert milestone_subject(
        visitor_key=None,
        user_id=FIRST_GUEST_USER_ID,
    ) != FIRST_GUEST_USER_ID
    assert milestone_subject(visitor_key=None, user_id=None) is None
    assert milestone_subject(visitor_key="   ", user_id=None) is None


def test_memory_claims_expire_so_the_twin_matches_the_table() -> None:
    claims: dict[tuple[str, str], datetime] = {}
    now = datetime.now(timezone.utc)

    assert claim_memory_milestone(
        claims,
        subject_key=VISITOR_KEY,
        milestone="first_result_completed",
        now=now,
    )
    assert not claim_memory_milestone(
        claims,
        subject_key=VISITOR_KEY,
        milestone="first_result_completed",
        now=now,
    )

    lapsed = now + MILESTONE_RETENTION + timedelta(seconds=1)
    assert claim_memory_milestone(
        claims,
        subject_key=VISITOR_KEY,
        milestone="first_result_completed",
        now=lapsed,
    )
    assert purge_memory_milestones(claims, before=lapsed + MILESTONE_RETENTION) == 1
    assert claims == {}
