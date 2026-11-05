"""`preferred_name` is what to call the user, and it is not `display_name`.

`display_name` is an identity field people fill with a legal name or whatever
their email gave them, so a greeting reusing it addresses the account rather
than the person. This one is optional, stated, and separate.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from argus.api.main import app
from argus.api.schemas import (
    PREFERRED_NAME_MAX_LENGTH,
    ProfilePatch,
    User,
    guest_safe_user,
)
from fastapi.testclient import TestClient
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _memory_store(monkeypatch: pytest.MonkeyPatch):
    from argus.api import state as api_state

    monkeypatch.setattr(api_state, "supabase_gateway", None)
    yield


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    return client


def _user(**overrides) -> User:
    now = datetime.now(timezone.utc)
    return User(
        id="user-1",
        email="a@b.c",
        created_at=now,
        updated_at=now,
        **overrides,
    )


def test_it_is_a_separate_field_from_display_name() -> None:
    user = _user(display_name="Alexandra", preferred_name="Alex")

    assert user.display_name == "Alexandra"
    assert user.preferred_name == "Alex"


def test_unset_is_the_default_and_means_no_name() -> None:
    assert _user().preferred_name is None


def test_blank_and_whitespace_clear_it_rather_than_storing_a_name() -> None:
    assert _user(preferred_name="   ").preferred_name is None
    assert ProfilePatch(preferred_name="").preferred_name is None
    assert ProfilePatch(preferred_name="  Alex  ").preferred_name == "Alex"


def test_it_is_bounded() -> None:
    with pytest.raises(ValidationError):
        ProfilePatch(preferred_name="x" * (PREFERRED_NAME_MAX_LENGTH + 1))
    assert (
        ProfilePatch(preferred_name="x" * PREFERRED_NAME_MAX_LENGTH).preferred_name
        is not None
    )


@pytest.mark.parametrize(
    "raw",
    [
        " " + "x" * PREFERRED_NAME_MAX_LENGTH,
        "x" * PREFERRED_NAME_MAX_LENGTH + " ",
        "  " + "x" * PREFERRED_NAME_MAX_LENGTH + "  ",
        "\t" + "x" * PREFERRED_NAME_MAX_LENGTH + "\n",
    ],
)
def test_the_bound_measures_the_name_not_what_was_typed_around_it(raw: str) -> None:
    # The exact defect: as an after-validator the trim ran too late, so
    # max_length measured the padding and a legal forty-character name 422'd.
    assert len(raw) > PREFERRED_NAME_MAX_LENGTH
    assert len(raw.strip()) == PREFERRED_NAME_MAX_LENGTH

    for model in (ProfilePatch, _user):
        value = (
            model(preferred_name=raw).preferred_name
            if model is ProfilePatch
            else _user(preferred_name=raw).preferred_name
        )
        assert value == "x" * PREFERRED_NAME_MAX_LENGTH


def test_padding_cannot_smuggle_a_name_past_the_bound() -> None:
    too_long = "x" * (PREFERRED_NAME_MAX_LENGTH + 1)
    with pytest.raises(ValidationError):
        ProfilePatch(preferred_name=f"   {too_long}   ")


def test_the_read_model_and_the_patch_state_the_rule_once() -> None:
    # Two copies of "normalize, then bound" would be two things that can drift.
    from argus.api import schemas

    assert schemas.User.model_fields["preferred_name"].annotation == (
        schemas.ProfilePatch.model_fields["preferred_name"].annotation
    )
    source = Path(schemas.__file__).read_text(encoding="utf-8")
    assert source.count("BeforeValidator(_blank_preferred_name_is_no_name)") == 1
    assert "preferred_name: PreferredName" in source


def test_guests_do_not_carry_one() -> None:
    # Guests have no profile and fall back to the nameless pool.
    projected = guest_safe_user(_user(preferred_name="Alex")).model_dump()

    assert "preferred_name" not in projected


def test_patch_round_trips_through_the_api() -> None:
    client = _client()

    saved = client.patch("/api/v1/me", json={"preferred_name": "  Alex  "})
    assert saved.status_code == 200
    assert saved.json()["user"]["preferred_name"] == "Alex"

    read = client.get("/api/v1/me")
    assert read.json()["user"]["preferred_name"] == "Alex"


def test_clearing_it_is_a_supported_edit() -> None:
    client = _client()
    client.patch("/api/v1/me", json={"preferred_name": "Alex"})

    cleared = client.patch("/api/v1/me", json={"preferred_name": ""})

    assert cleared.status_code == 200
    assert cleared.json()["user"]["preferred_name"] is None


def test_a_patch_that_omits_it_leaves_it_alone() -> None:
    # Partial update semantics: editing the language must not wipe the name.
    client = _client()
    client.patch("/api/v1/me", json={"preferred_name": "Alex"})

    client.patch("/api/v1/me", json={"language": "es-419", "locale": "es-419"})

    assert client.get("/api/v1/me").json()["user"]["preferred_name"] == "Alex"


def test_an_over_long_name_is_rejected_by_the_api() -> None:
    response = _client().patch(
        "/api/v1/me",
        json={"preferred_name": "x" * (PREFERRED_NAME_MAX_LENGTH + 1)},
    )

    assert response.status_code == 422


def test_a_padded_full_length_name_is_accepted_by_the_api() -> None:
    # End to end, over the wire: this returned 422 before the bound moved behind
    # the normalizer.
    padded = " " + "x" * PREFERRED_NAME_MAX_LENGTH

    response = _client().patch("/api/v1/me", json={"preferred_name": padded})

    assert response.status_code == 200
    assert response.json()["user"]["preferred_name"] == "x" * PREFERRED_NAME_MAX_LENGTH


def test_the_contract_declares_it_on_user_but_not_on_guest_user() -> None:
    openapi = yaml.safe_load(
        (ROOT / "docs" / "api" / "openapi.yaml").read_text(encoding="utf-8")
    )
    schemas = openapi["components"]["schemas"]

    assert "preferred_name" in schemas["User"]["properties"]
    assert "preferred_name" not in schemas["GuestUser"]["properties"]
    assert "preferred_name" in schemas["ProfilePatch"]["properties"]


def test_the_migration_bounds_it_and_keeps_it_off_the_guest_surface() -> None:
    migration = (
        ROOT / "supabase" / "migrations" / "20260809140000_add_preferred_name.sql"
    ).read_text(encoding="utf-8")

    assert "add column if not exists preferred_name text" in migration
    assert f"between 1 and {PREFERRED_NAME_MAX_LENGTH}" in migration
    # Anonymous Auth users share the authenticated role, so the restrictive
    # policies read the trusted JWT claim rather than the role.
    assert migration.count("as restrictive") == 2
    assert "'is_anonymous') is distinct from 'true'" in migration


def test_nothing_infers_a_preferred_name_from_conversation() -> None:
    # This is a setting, never a memory. Guessing a nickname from how someone
    # types would be the creepiest thing in the product. Only profile creation
    # writes it, and only for a new row, from the name typed at sign-up.
    writers = [
        path
        for path in (ROOT / "src").rglob("*.py")
        if "preferred_name" in path.read_text(encoding="utf-8")
    ]

    assert {path.relative_to(ROOT).as_posix() for path in writers} == {
        "src/argus/api/schemas.py",
        "src/argus/domain/supabase_gateway.py",
    }
