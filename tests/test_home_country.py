"""A home country is a declared profile setting, and a turn reads it from there.

The user picks a country in Settings; nothing infers one (decision 8). The
currency derives from the country unless the user overrides it, and only the
override is stored. Research sends the country as the reader's location.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml
from argus.api.main import app
from argus.api.schemas import ProfilePatch, User, guest_safe_user
from argus.domain.home_country import country_codes, country_currency, currency_codes
from fastapi.testclient import TestClient
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / "supabase" / "migrations" / "20260911120000_add_profile_home_country.sql"
)
SETTINGS = ("country", "currency_override", "currency")


@pytest.fixture(autouse=True)
def _memory_store(monkeypatch: pytest.MonkeyPatch):
    from argus.api import state as api_state

    monkeypatch.setattr(api_state, "supabase_gateway", None)
    yield


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    return client


def _user(**overrides: Any) -> User:
    now = datetime.now(timezone.utc)
    return User.model_validate(
        {"id": "user-1", "email": "a@b.c", "created_at": now, "updated_at": now}
        | overrides
    )


# --- the codes --------------------------------------------------------------


def test_every_country_is_a_two_letter_code() -> None:
    codes = country_codes()
    assert {"MX", "DO", "US", "ES"} <= codes
    assert all(len(code) == 2 and code.isalpha() and code.isupper() for code in codes)


@pytest.mark.parametrize("code", ["EU", "EZ", "UN", "XK", "QO", "ZZ"])
def test_a_grouping_or_user_assigned_region_is_not_a_country(code: str) -> None:
    """A location the provider may reject is never accepted as a setting."""
    assert code not in country_codes()
    with pytest.raises(ValidationError):
        ProfilePatch(country=code)


@pytest.mark.parametrize(
    ("country", "currency"),
    [("MX", "MXN"), ("DO", "DOP"), ("US", "USD"), ("ES", "EUR")],
)
def test_a_country_implies_its_currency(country: str, currency: str) -> None:
    assert _user(country=country).currency == currency


def test_an_override_wins_and_clearing_it_returns_to_the_country() -> None:
    assert _user(country="MX", currency_override="USD").currency == "USD"
    assert _user(country="MX", currency_override=None).currency == "MXN"
    assert _user(currency_override="EUR").currency == "EUR"
    assert _user().currency is None


def test_codes_are_normalized_and_a_blank_edit_clears() -> None:
    assert ProfilePatch(country=" mx ").country == "MX"
    assert ProfilePatch(currency_override="usd").currency_override == "USD"
    assert ProfilePatch(country="").country is None


@pytest.mark.parametrize(
    "patch",
    [
        {"country": "Mexico"},
        {"country": "M"},
        {"currency_override": "US"},
        {"currency_override": "XAU"},
    ],
)
def test_an_edit_names_a_real_code(patch: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        ProfilePatch(**patch)


def test_an_edit_needs_a_currency_in_tender_but_a_stored_one_still_loads() -> None:
    # Croatia replaced the kuna with the euro on 2023-01-01.
    retired = "HRK"
    assert retired not in currency_codes()
    with pytest.raises(ValidationError):
        ProfilePatch(currency_override=retired)
    assert _user(currency_override=retired).currency == retired


def test_the_offered_currencies_follow_the_record_never_the_calendar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The picker ships these codes as a file, so the API's list must not move
    on a date the deployed picker cannot see."""
    import babel.numbers

    real = babel.numbers.get_global

    def announced_changeover(key: str) -> Any:
        data = real(key)
        if key != "territory_currencies":
            return data
        # By the calendar MXN is in use for centuries and XTS has not begun;
        # the record says MXN ends and XTS has no end.
        return {
            **data,
            "MX": [
                ("MXN", (1993, 1, 1), (2999, 1, 1), True),
                ("XTS", (2999, 1, 1), None, True),
            ],
        }

    monkeypatch.setattr(babel.numbers, "get_global", announced_changeover)

    assert country_currency("MX") == "XTS"
    assert "XTS" in currency_codes()
    assert "MXN" not in currency_codes()


# --- the API ----------------------------------------------------------------


def test_a_country_and_its_currency_round_trip_through_the_api() -> None:
    client = _client()

    saved = client.patch("/api/v1/me", json={"country": "mx"})
    assert saved.status_code == 200
    assert [saved.json()["user"][key] for key in SETTINGS] == ["MX", None, "MXN"]

    overridden = client.patch("/api/v1/me", json={"currency_override": "USD"})
    assert overridden.json()["user"]["currency"] == "USD"

    read = client.get("/api/v1/me").json()["user"]
    assert [read[key] for key in SETTINGS] == ["MX", "USD", "USD"]


def test_clearing_the_country_leaves_nothing_to_send() -> None:
    client = _client()
    client.patch("/api/v1/me", json={"country": "MX"})

    cleared = client.patch("/api/v1/me", json={"country": None}).json()["user"]

    assert cleared["country"] is None
    assert cleared["currency"] is None


def test_editing_another_preference_leaves_the_country_alone() -> None:
    client = _client()
    client.patch("/api/v1/me", json={"country": "DO", "currency_override": "USD"})

    client.patch("/api/v1/me", json={"language": "es-419", "locale": "es-419"})

    read = client.get("/api/v1/me").json()["user"]
    assert [read[key] for key in SETTINGS] == ["DO", "USD", "USD"]


@pytest.mark.parametrize(
    "patch",
    [{"country": "EU"}, {"country": "Mexico"}, {"currency_override": "HRK"}],
)
def test_the_api_refuses_a_code_that_is_not_assigned(patch: dict[str, str]) -> None:
    assert _client().patch("/api/v1/me", json=patch).status_code == 422


def test_the_resolved_currency_is_not_writable() -> None:
    response = _client().patch("/api/v1/me", json={"country": "MX", "currency": "USD"})

    assert response.status_code == 200
    assert response.json()["user"]["currency"] == "MXN"


def test_the_profile_row_stores_the_override_and_never_the_resolved_currency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import state as api_state

    stored = _user(country="MX")
    written: list[dict[str, Any]] = []

    class _ProfileGateway:
        def get_or_create_mock_user(self) -> User:
            return stored

        def get_user(self, *, user_id: str) -> User:
            return stored

        def update_user(self, user_id: str, updates: dict[str, Any]) -> User:
            written.append(dict(updates))
            return User.model_validate(stored.model_dump() | updates)

    from argus.api.routers import profile

    monkeypatch.setattr(api_state, "supabase_gateway", _ProfileGateway())
    monkeypatch.setattr(profile, "_apple_identity", lambda *_: None)

    response = TestClient(app).patch("/api/v1/me", json={"currency_override": "USD"})

    assert response.status_code == 200
    assert response.json()["user"]["currency"] == "USD"
    assert len(written) == 1
    assert "currency" not in written[0]
    assert "country" not in written[0]
    assert written[0]["currency_override"] == "USD"


def test_guests_carry_no_country_or_currency() -> None:
    projected = guest_safe_user(_user(country="MX", currency_override="USD"))

    assert not set(SETTINGS) & projected.model_dump().keys()


# --- what ships beside the code ---------------------------------------------


def test_the_migration_adds_nullable_codes_off_the_guest_surface() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")

    assert "add column if not exists country text," in migration
    assert "add column if not exists currency_override text;" in migration
    assert "not null" not in migration
    assert "country ~ '^[A-Z]{2}$'" in migration
    assert "currency_override ~ '^[A-Z]{3}$'" in migration
    # The resolved currency derives from these; it is never a column.
    assert "add column if not exists currency text" not in migration
    assert migration.count("as restrictive") == 2
    assert "'is_anonymous') is distinct from 'true'" in migration


def test_the_contract_declares_the_settings_on_user_and_the_patch_only() -> None:
    openapi = yaml.safe_load(
        (ROOT / "docs" / "api" / "openapi.yaml").read_text(encoding="utf-8")
    )
    schemas = openapi["components"]["schemas"]

    assert set(SETTINGS) <= schemas["User"]["properties"].keys()
    assert schemas["User"]["properties"]["currency"]["readOnly"] is True
    assert not set(SETTINGS) & schemas["GuestUser"]["properties"].keys()
    assert {"country", "currency_override"} <= schemas["ProfilePatch"]["properties"].keys()
    assert "currency" not in schemas["ProfilePatch"]["properties"]


def test_the_settings_picker_offers_exactly_what_an_edit_may_name() -> None:
    from scripts.generate_home_country_codes import ARTIFACT, build_artifact_text

    assert ARTIFACT.read_text(encoding="utf-8") == build_artifact_text(), (
        "regenerate with: poetry run python scripts/generate_home_country_codes.py"
    )
