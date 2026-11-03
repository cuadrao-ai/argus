"""Sign-up fills `preferred_name` from the first word of the name the person typed.

The profile row is created in one place, `get_or_create_profile_for_auth_user`.
It writes the greeting name once, at creation, so a name the person chose or
cleared afterwards is never written over.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from argus.api.schemas import PREFERRED_NAME_MAX_LENGTH
from argus.domain.supabase_gateway import SupabaseGateway
from faker import Faker

fake = Faker()
USER_ID = "00000000-0000-0000-0000-000000000009"


def _profile_row(**overrides: Any) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": USER_ID,
        "email": "alpha@example.test",
        "username": None,
        "display_name": None,
        "preferred_name": None,
        "language": "es-419",
        "locale": "es-419",
        "is_admin": False,
        "created_at": now,
        "updated_at": now,
        **overrides,
    }


class _Profiles:
    """Stands in for the `profiles` table: an upsert that ignores duplicates."""

    def __init__(self, existing: dict[str, Any] | None = None) -> None:
        self.row = existing
        self.upserts: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []

    def table(self, name: str) -> MagicMock:
        assert name == "profiles"
        table = MagicMock()
        table.upsert.side_effect = self._upsert
        table.update.side_effect = self._update
        return table

    def _upsert(self, payload: dict[str, Any], **_: Any) -> SimpleNamespace:
        self.upserts.append(payload)
        created = self.row is None
        if created:
            self.row = _profile_row(**payload)
        return SimpleNamespace(
            execute=lambda: SimpleNamespace(data=[self.row] if created else [])
        )

    def _update(self, payload: dict[str, Any]) -> MagicMock:
        self.updates.append(payload)
        return MagicMock()


def _gateway(profiles: _Profiles) -> SupabaseGateway:
    client = MagicMock()
    client.table.side_effect = profiles.table
    gateway = SupabaseGateway(client=client)
    gateway.private_alpha_role_for_email = MagicMock(return_value="user")
    gateway.get_user = MagicMock(
        side_effect=lambda user_id: None if profiles.row is None else _user(profiles.row)
    )
    return gateway


def _user(row: dict[str, Any]) -> Any:
    from argus.api.schemas import User

    return User.model_validate(row)


def _auth_user(display_name: Any = None, **extra: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {"language": "es-419"}
    if display_name is not None:
        metadata["display_name"] = display_name
    return {
        "id": USER_ID,
        "email": "alpha@example.test",
        "user_metadata": metadata,
        **extra,
    }


def test_sign_up_greets_by_the_first_name_typed() -> None:
    first, last = fake.first_name(), fake.last_name()
    profiles = _Profiles()
    created = _gateway(profiles).get_or_create_profile_for_auth_user(
        _auth_user(f"{first} {last}")
    )
    assert created.display_name == f"{first} {last}"
    assert created.preferred_name == first
    assert profiles.upserts[0]["preferred_name"] == first


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("Ana", "Ana"),
        ("  María   José Pérez  ", "María"),
        ("Ana\tMaría\nPérez", "Ana"),
        ("李 小龍", "李"),
        ("x" * PREFERRED_NAME_MAX_LENGTH, "x" * PREFERRED_NAME_MAX_LENGTH),
    ],
)
def test_first_word_of_the_typed_name(typed: str, expected: str) -> None:
    created = _gateway(_Profiles()).get_or_create_profile_for_auth_user(_auth_user(typed))
    assert created.preferred_name == expected


@pytest.mark.parametrize(
    "typed",
    [None, "", "   ", "\n\t", "x" * (PREFERRED_NAME_MAX_LENGTH + 1)],
)
def test_no_usable_first_name_leaves_it_empty(typed: Any) -> None:
    profiles = _Profiles()
    created = _gateway(profiles).get_or_create_profile_for_auth_user(_auth_user(typed))
    assert created.preferred_name is None
    assert profiles.upserts[0].get("preferred_name") is None


def test_apple_sign_in_with_no_name_leaves_it_empty() -> None:
    profiles = _Profiles()
    apple = _auth_user(app_metadata={"provider": "apple", "providers": ["apple"]})
    created = _gateway(profiles).get_or_create_profile_for_auth_user(apple)
    assert created.display_name is None
    assert created.preferred_name is None


def test_a_guest_has_no_greeting_name() -> None:
    profiles = _Profiles()
    guest = {**_auth_user("Ana Pérez"), "email": None, "is_anonymous": True}
    created = _gateway(profiles).get_or_create_profile_for_auth_user(guest)
    assert created.preferred_name is None


@pytest.mark.parametrize("chosen", ["Lucho", None])
def test_a_name_the_person_chose_or_cleared_is_never_overwritten(
    chosen: str | None,
) -> None:
    profiles = _Profiles(_profile_row(display_name="Lucas Garcés", preferred_name=chosen))
    reread = _gateway(profiles).get_or_create_profile_for_auth_user(
        _auth_user("Lucas Garcés")
    )
    assert reread.preferred_name == chosen
    assert profiles.upserts == []
    assert profiles.updates == []


def test_a_lost_creation_race_keeps_the_winner_row() -> None:
    profiles = _Profiles(_profile_row(display_name="Ana Pérez", preferred_name="Anita"))
    gateway = _gateway(profiles)
    gateway.get_user = MagicMock(side_effect=[None, _user(profiles.row)])
    created = gateway.get_or_create_profile_for_auth_user(_auth_user("Ana Pérez"))
    assert created.preferred_name == "Anita"
    assert profiles.row["preferred_name"] == "Anita"
