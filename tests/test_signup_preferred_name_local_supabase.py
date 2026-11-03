"""Real-database proof that sign-up fills `preferred_name` once and never again."""

from __future__ import annotations

import os
import secrets
from contextlib import suppress

import psycopg
import pytest
from faker import Faker

from tests.local_supabase_support import local_supabase_gateway

fake = Faker()
DATABASE_URL = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not all(
        os.getenv(name, "").strip()
        for name in (
            "ARGUS_LOCAL_SUPABASE_URL",
            "ARGUS_LOCAL_SUPABASE_ANON_KEY",
            "ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY",
            "ARGUS_DISPOSABLE_DATABASE_URL",
        )
    ),
    reason="local Supabase is not configured",
)


def _stored(user_id: str) -> tuple[str | None, str | None]:
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "select display_name, preferred_name from public.profiles where id=%s",
            (user_id,),
        ).fetchone()
    assert row is not None
    return row


def _register(gateway, metadata: dict) -> dict:  # noqa: ANN001
    created = gateway.client.auth.admin.create_user(
        {
            "email": f"preferred-{secrets.token_hex(6)}@example.test",
            "password": f"Pw-{secrets.token_urlsafe(18)}",
            "email_confirm": True,
            "user_metadata": metadata,
        }
    )
    assert created.user is not None
    return created.user.model_dump(mode="json")


def test_first_profile_gets_the_first_name_and_a_later_choice_survives() -> None:
    gateway = local_supabase_gateway()
    first, last = fake.first_name(), fake.last_name()
    auth_user = _register(
        gateway, {"display_name": f"{first} {last}", "language": "es-419"}
    )
    user_id = auth_user["id"]
    try:
        profile = gateway.get_or_create_profile_for_auth_user(auth_user)
        assert profile.preferred_name == first
        assert _stored(user_id) == (f"{first} {last}", first)

        gateway.update_user(user_id, {"preferred_name": None})
        gateway.get_or_create_profile_for_auth_user(auth_user)
        assert _stored(user_id) == (f"{first} {last}", None)

        gateway.update_user(user_id, {"preferred_name": "Lucho"})
        gateway.get_or_create_profile_for_auth_user(auth_user)
        assert _stored(user_id) == (f"{first} {last}", "Lucho")
    finally:
        with suppress(Exception):
            gateway.delete_auth_user(user_id)


def test_a_sign_in_with_no_name_stores_no_greeting_name() -> None:
    gateway = local_supabase_gateway()
    auth_user = _register(gateway, {"language": "es-419"})
    user_id = auth_user["id"]
    try:
        profile = gateway.get_or_create_profile_for_auth_user(auth_user)
        assert profile.preferred_name is None
        assert _stored(user_id) == (None, None)
    finally:
        with suppress(Exception):
            gateway.delete_auth_user(user_id)
