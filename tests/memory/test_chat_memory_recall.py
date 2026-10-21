"""The post-turn recall annotation respects every gate and never breaks turns.

S10 shape: this helper is called only after the turn's interpretation,
routing, and simulation are complete; these tests pin that it stays inert for
guests, opted-out conversations, and unexposed accounts, and that recall
errors degrade to no annotation instead of a failed turn.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import cast

import pytest
from api_matrix import REGISTERED_EMAIL, REGISTERED_USER_ID
from argus.api.chat.memory_recall import memory_recalls_for_turn
from argus.api.guest_access import (
    guest_account_context,
    registered_account_context,
)
from argus.api.message_store import memory_conversation
from argus.api.personalization_memory import configure_memory_service
from argus.api.schemas import OnboardingState, User
from argus.domain.guest_workspaces import GuestWorkspace
from argus.domain.owner_scope import PERSONAL
from argus.memory.contracts import (
    MemoryCandidateDraft,
    MemoryCategory,
    MemoryOperationContext,
    MemoryProposalTrigger,
    MemoryProvenance,
    MemorySourceKind,
    SensitivityAssessment,
    SensitivityStatus,
)
from argus.memory.service import MemoryService, MemoryServiceConfig
from argus.memory.store import InMemoryCanonicalMemoryStore
from argus.memory.subject import MemoryAccountKind, MemorySubject


class _ExplodingMemoryService:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"MemoryService.{name} must not be touched")


def _user() -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=REGISTERED_USER_ID,
        email=REGISTERED_EMAIL,
        username=None,
        display_name=None,
        language="en",
        locale="en-US",
        is_admin=False,
        onboarding=OnboardingState(),
        created_at=now,
        updated_at=now,
    )


def _guest_account():
    now = datetime.now(timezone.utc)
    return guest_account_context(
        GuestWorkspace(
            user_id=REGISTERED_USER_ID,
            conversation_id=None,
            status="active",
            created_at=now,
            expires_at=now + timedelta(days=7),
            claimed_by=None,
            claimed_at=None,
            updated_at=now,
        )
    )


def _seeded_service() -> MemoryService:
    service = MemoryService(
        store=InMemoryCanonicalMemoryStore(),
        config=MemoryServiceConfig(available=True),
    )
    subject = MemorySubject(
        owner_id=REGISTERED_USER_ID,
        kind=MemoryAccountKind.REGISTERED,
    )
    service.enable(subject, frozenset({MemoryCategory.EXPLICIT_DECISION_NOTE}))
    proposal = service.propose(
        subject,
        MemoryCandidateDraft(
            category=MemoryCategory.EXPLICIT_DECISION_NOTE,
            value="Rejected the higher-drawdown version of the ETH idea.",
            label="ETH drawdown decision",
            future_benefit="Argus can revisit and compare this saved decision later.",
            provenance=(
                MemoryProvenance(
                    source_kind=MemorySourceKind.DECISION_NOTE,
                    source_id="decision-note-1",
                    source_version="1",
                ),
            ),
            trigger=MemoryProposalTrigger.EXPLICIT_REQUEST,
            sensitivity=SensitivityAssessment(status=SensitivityStatus.CLEAR),
        ),
        MemoryOperationContext.ORDINARY,
    )
    assert proposal is not None
    confirmation = service.confirm(
        subject,
        proposal.candidate.id,
        context=MemoryOperationContext.ORDINARY,
    )
    assert confirmation.created is True
    return service


@pytest.fixture(autouse=True)
def _reset_service_and_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ARGUS_ENABLE_PERSONALIZATION_MEMORY", raising=False)
    configure_memory_service(None)
    yield
    configure_memory_service(None)


def _memory_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from argus.api import state as api_state

    monkeypatch.setattr(api_state, "supabase_gateway", None)


def _personal_conversation_id() -> str:
    return memory_conversation(
        title="ETH idea",
        title_source="system_default",
        language="en",
        scope=PERSONAL,
        user_id=REGISTERED_USER_ID,
    ).id


def test_flag_off_returns_none_without_touching_the_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _memory_mode(monkeypatch)
    configure_memory_service(cast(MemoryService, _ExplodingMemoryService()))

    assert (
        memory_recalls_for_turn(
            conversation_id=_personal_conversation_id(),
            user=_user(),
            account=registered_account_context(REGISTERED_USER_ID),
            user_message="what did I decide about ETH?",
            memory_opt_out=False,
        )
        is None
    )


def test_guest_account_returns_none_without_touching_the_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _memory_mode(monkeypatch)
    monkeypatch.setenv("ARGUS_ENABLE_PERSONALIZATION_MEMORY", "true")
    configure_memory_service(cast(MemoryService, _ExplodingMemoryService()))

    assert (
        memory_recalls_for_turn(
            conversation_id=_personal_conversation_id(),
            user=_user(),
            account=_guest_account(),
            user_message="what did I decide about ETH?",
            memory_opt_out=False,
        )
        is None
    )


def test_memory_opt_out_returns_none_without_touching_the_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _memory_mode(monkeypatch)
    monkeypatch.setenv("ARGUS_ENABLE_PERSONALIZATION_MEMORY", "true")
    configure_memory_service(cast(MemoryService, _ExplodingMemoryService()))

    assert (
        memory_recalls_for_turn(
            conversation_id=_personal_conversation_id(),
            user=_user(),
            account=registered_account_context(REGISTERED_USER_ID),
            user_message="what did I decide about ETH?",
            memory_opt_out=True,
        )
        is None
    )


def test_exposed_turn_gets_bounded_recalls(monkeypatch: pytest.MonkeyPatch) -> None:
    _memory_mode(monkeypatch)
    monkeypatch.setenv("ARGUS_ENABLE_PERSONALIZATION_MEMORY", "true")
    configure_memory_service(_seeded_service())

    recalls = memory_recalls_for_turn(
        conversation_id=_personal_conversation_id(),
        user=_user(),
        account=registered_account_context(REGISTERED_USER_ID),
        user_message="what did I decide about the ETH drawdown version?",
        memory_opt_out=False,
    )

    assert recalls is not None
    assert len(recalls) == 1
    assert recalls[0]["label"] == "ETH drawdown decision"
    assert recalls[0]["category"] == "explicit_decision_note"
    assert set(recalls[0]) == {"record_id", "label", "value", "category"}


def test_recall_errors_degrade_to_no_annotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RaisingService:
        def retrieve(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("retrieval backend down")

    _memory_mode(monkeypatch)
    monkeypatch.setenv("ARGUS_ENABLE_PERSONALIZATION_MEMORY", "true")
    configure_memory_service(cast(MemoryService, _RaisingService()))

    assert (
        memory_recalls_for_turn(
            conversation_id=_personal_conversation_id(),
            user=_user(),
            account=registered_account_context(REGISTERED_USER_ID),
            user_message="what did I decide about ETH?",
            memory_opt_out=False,
        )
        is None
    )


def test_a_failed_side_lookup_degrades_to_no_annotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.chat import memory_recall

    def _unreachable(**_: object) -> object:
        raise ConnectionError("database unavailable")

    _memory_mode(monkeypatch)
    monkeypatch.setenv("ARGUS_ENABLE_PERSONALIZATION_MEMORY", "true")
    monkeypatch.setattr(memory_recall, "conversation_scope", _unreachable)
    configure_memory_service(_seeded_service())

    assert (
        memory_recalls_for_turn(
            conversation_id=_personal_conversation_id(),
            user=_user(),
            account=registered_account_context(REGISTERED_USER_ID),
            user_message="what did I decide about ETH?",
            memory_opt_out=False,
        )
        is None
    )
