"""The Business's own RNC against the registry, and the legal name a person who
manages the Business confirms for it. Real Postgres with every migration
applied; registry rows are synthetic and deleted after each test."""

from __future__ import annotations

import random
from datetime import date
from uuid import uuid4

import pytest
from argus.domain.business.activity.queries import read_activity
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.fiscal_profile import (
    FiscalProfileChange,
    LegalNameChange,
    RegistryQuery,
    lookup_registry,
    read_profile,
    set_legal_name,
    set_profile,
)
from faker import Faker
from psycopg import Connection
from psycopg.errors import CheckViolation
from psycopg.rows import dict_row

from tests import test_business_actions_postgres as shared
from tests.test_business_spaces_migration_postgres import owned_space

users = shared.users
actions = shared.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]
fake = Faker("es")
FILE_DATE = date(2026, 10, 20)


def _rnc() -> str:
    return "".join(str(random.randint(1, 9)) for _ in range(9))


@pytest.fixture
def registry():
    """One active RNC, one suspended RNC and one the registry never published."""

    rows = {
        "active": (_rnc(), f"{fake.company().upper()} SRL", "ACTIVO"),
        "suspended": (_rnc(), f"{fake.company().upper()} SRL", "SUSPENDIDO"),
    }
    with Connection.connect(shared.shared.DSN) as db:
        for rnc, name, status in rows.values():
            db.execute(
                "insert into public.dgii_rnc (rnc, name, trade_name, status, file_date)"
                " values (%s, %s, null, %s, %s)",
                (rnc, name, status, FILE_DATE),
            )
    try:
        yield {**rows, "missing": (_rnc(), None, None)}
    finally:
        with Connection.connect(shared.shared.DSN) as db:
            db.execute(
                "delete from public.dgii_rnc where rnc = any(%s)",
                ([rnc for rnc, _, _ in rows.values()],),
            )


def _rnc_id(value: str) -> dict:
    return {"type": "rnc", "value": value}


def _save_rnc(service, context, value: str | None, previous: str | None = None):
    name = read_profile(service.authority, context)["name"]
    return set_profile(
        service.authority,
        context,
        FiscalProfileChange(
            name=name,
            previous_name=name,
            tax_id=None if value is None else _rnc_id(value),
            previous_tax_id=None if previous is None else _rnc_id(previous),
        ),
        str(uuid4()),
    )


def _confirm(service, context, rnc: str, name: str | None, previous=None, key=None):
    return set_legal_name(
        service.authority,
        context,
        LegalNameChange(
            legal_name=name,
            previous_legal_name=previous,
            tax_id=_rnc_id(rnc),
            confirmed=name is not None,
        ),
        key or str(uuid4()),
    )


def _accountant(service, context, users):
    with service.authority.pool.connection() as db:
        grant = db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " values(%s,%s,%s,array['read','prepare']) returning id",
            (context.actor.space_id, users["other"], users["owner"]),
        ).fetchone()[0]
    return service.resolve_actor(
        TrustedActor(
            actor_id=users["other"], actor_kind="member", space_id=context.actor.space_id
        ),
        grant_id=grant,
    )


@pytest.mark.parametrize(
    ("case", "verification", "status"),
    [
        ("active", "verificado", "ACTIVO"),
        ("suspended", "no_activo", "SUSPENDIDO"),
        ("missing", "sin_verificar", None),
    ],
)
def test_the_lookup_answers_with_the_counterparty_words(
    actions, registry, case, verification, status
):
    service, context, _ = actions
    rnc, name, _ = registry[case]
    printed = f"{rnc[0]}-{rnc[1:3]}-{rnc[3:8]}-{rnc[8]}"
    answer = lookup_registry(
        service.authority,
        context,
        RegistryQuery(tax_id={"type": "rnc", "value": printed}),
    )
    assert answer["tax_id"].value == rnc
    assert answer["verification"] == verification
    assert answer["checked_at"] is not None
    if status is None:
        assert answer["record"] is None
    else:
        assert answer["record"] == {
            "rnc": rnc,
            "name": name,
            "trade_name": None,
            "status": status,
            "file_date": FILE_DATE,
        }


def test_people_who_cannot_manage_can_neither_look_up_nor_confirm(
    actions, registry, users
):
    service, context, _ = actions
    rnc, name, _ = registry["active"]
    _save_rnc(service, context, rnc)
    accountant = _accountant(service, context, users)
    with pytest.raises(ActionError, match="business_permission_denied"):
        lookup_registry(
            service.authority, accountant, RegistryQuery(tax_id=_rnc_id(rnc))
        )
    with pytest.raises(ActionError, match="business_permission_denied"):
        _confirm(service, accountant, rnc, name)
    assert read_profile(service.authority, context)["legal_name"] is None


def test_a_legal_name_needs_the_confirmation_and_a_registry_row(actions, registry):
    service, context, _ = actions
    rnc, name, _ = registry["active"]
    _save_rnc(service, context, rnc)
    with pytest.raises(ValueError, match="legal_name_confirmation_required"):
        LegalNameChange(
            legal_name=name,
            previous_legal_name=None,
            tax_id=_rnc_id(rnc),
            confirmed=False,
        )
    missing = registry["missing"][0]
    _save_rnc(service, context, missing, rnc)
    with pytest.raises(ActionError, match="legal_name_not_in_registry"):
        _confirm(service, context, missing, fake.company())
    assert read_profile(service.authority, context)["legal_name"] is None


def test_a_confirmed_legal_name_saves_reloads_and_is_one_activity_entry(
    actions, registry
):
    service, context, _ = actions
    rnc, name, _ = registry["suspended"]
    _save_rnc(service, context, rnc)
    typed = f"  {name.title()}  "
    saved = _confirm(service, context, rnc, typed, key="legal-name")
    assert saved["legal_name"]["value"] == name.title()
    assert _confirm(service, context, rnc, typed, key="legal-name") == saved
    reloaded = read_profile(service.authority, context)
    assert reloaded == saved
    with service.authority.pool.connection() as db:
        row = (
            db.cursor(row_factory=dict_row)
            .execute(
                "select business_legal_name_confirmed_by as who,"
                " business_legal_name_confirmed_at as at from public.spaces where id=%s",
                (context.actor.space_id,),
            )
            .fetchone()
        )
        receipts = db.execute(
            "select count(*) from public.business_action_receipts"
            " where space_id=%s and command->>'action'='set_business_legal_name'",
            (context.actor.space_id,),
        ).fetchone()[0]
    assert row["who"] == context.actor.actor_id
    assert row["at"] == reloaded["legal_name"]["confirmed_at"]
    assert receipts == 1
    page = read_activity(service.authority, context, limit=25)
    assert [item.action for item in page.items].count("set_business_legal_name") == 1

    with pytest.raises(ActionError, match="stale_version"):
        _confirm(service, context, rnc, name, previous=None)
    cleared = _confirm(service, context, rnc, None, previous=name.title())
    assert cleared["legal_name"] is None


def test_the_legal_name_belongs_to_the_tax_id_it_was_confirmed_for(actions, registry):
    service, context, _ = actions
    rnc, name, _ = registry["active"]
    other, _, _ = registry["suspended"]
    _save_rnc(service, context, rnc)
    _confirm(service, context, rnc, name)
    with pytest.raises(ActionError, match="stale_version"):
        _confirm(service, context, other, name, previous=name)
    current = read_profile(service.authority, context)["name"]
    renamed = set_profile(
        service.authority,
        context,
        FiscalProfileChange(
            name=f"{current} Norte",
            previous_name=current,
            tax_id=_rnc_id(rnc),
            previous_tax_id=_rnc_id(rnc),
        ),
        str(uuid4()),
    )
    assert renamed["legal_name"]["value"] == name
    assert _save_rnc(service, context, other, rnc)["legal_name"] is None
    _confirm(service, context, other, name)
    assert _save_rnc(service, context, None, other)["legal_name"] is None


def test_the_columns_stay_server_only_and_one_business_never_sees_another(
    actions, registry, users
):
    service, context, _ = actions
    rnc, name, _ = registry["active"]
    _save_rnc(service, context, rnc)
    _confirm(service, context, rnc, name)
    with Connection.connect(shared.shared.DSN) as db:
        for role in ("anon", "authenticated"):
            for column in (
                "business_legal_name",
                "business_legal_name_confirmed_by",
                "business_legal_name_confirmed_at",
            ):
                for privilege in ("SELECT", "INSERT", "UPDATE"):
                    assert (
                        db.execute(
                            "select has_column_privilege(%s,'public.spaces',%s,%s)",
                            (role, column, privilege),
                        ).fetchone()[0]
                        is False
                    )
        other_space = owned_space(db, users["other"])
        with pytest.raises(CheckViolation), db.transaction():
            db.execute(
                "update public.spaces set business_legal_name=%s,"
                " business_legal_name_confirmed_at=now() where id=%s",
                (name, other_space),
            )
        with pytest.raises(CheckViolation), db.transaction():
            db.execute(
                "update public.spaces set business_legal_name_confirmed_at=null"
                " where id=%s",
                (context.actor.space_id,),
            )
    their_own = service.resolve_actor(
        TrustedActor(actor_id=users["other"], actor_kind="member", space_id=other_space)
    )
    assert read_profile(service.authority, their_own)["legal_name"] is None
    assert read_profile(service.authority, context)["legal_name"]["value"] == name


def _client(service, context, grant):
    from argus.api.business import BusinessPerson, require_business_person
    from argus.api.business_drafts import DraftContext, require_drafts
    from argus.api.routers.business_fiscal import router
    from argus.domain.business.spaces import PostgresSpaceStore
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        service, context.actor.actor_id, str(context.actor.space_id), grant
    )
    app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        str(context.actor.actor_id), PostgresSpaceStore(service.authority.pool)
    )

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "legal-name-synthetic-api"
        return await call_next(request)

    return TestClient(app)


def test_the_routes_answer_the_form_and_refuse_with_named_codes(actions, registry):
    service, context, grant = actions
    rnc, name, _ = registry["active"]
    _save_rnc(service, context, rnc)
    with _client(service, context, grant) as client:
        looked = client.post(
            "/business/fiscal-profile/registry",
            json={"tax_id": {"type": "rnc", "value": rnc}},
        )
        assert looked.status_code == 200, looked.text
        assert looked.headers["cache-control"] == "no-store"
        assert looked.json()["verification"] == "verificado"
        assert looked.json()["record"]["name"] == name
        malformed = client.post(
            "/business/fiscal-profile/registry",
            json={"tax_id": {"type": "rnc", "value": "12345"}},
        )
        assert malformed.status_code == 422
        assert malformed.json()["detail"]["code"] == "tax_id_length"
        body = {
            "legal_name": name,
            "previous_legal_name": None,
            "tax_id": {"type": "rnc", "value": rnc},
        }
        unconfirmed = client.put(
            "/business/fiscal-profile/legal-name",
            json=body,
            headers={"Idempotency-Key": "unconfirmed"},
        )
        assert unconfirmed.status_code == 422
        assert unconfirmed.json()["detail"]["code"] == "legal_name_confirmation_required"
        saved = client.put(
            "/business/fiscal-profile/legal-name",
            json={**body, "confirmed": True},
            headers={"Idempotency-Key": "confirmed"},
        )
        assert saved.status_code == 200, saved.text
        assert saved.headers["cache-control"] == "no-store"
        assert saved.json()["legal_name"]["value"] == name
        reloaded = client.get("/business/fiscal-profile")
        assert reloaded.json()["legal_name"] == saved.json()["legal_name"]
        stale = client.put(
            "/business/fiscal-profile/legal-name",
            json={**body, "confirmed": True},
            headers={"Idempotency-Key": "stale"},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "stale_version"
