"""Historical scope and route describe acceptance without expiring permission.
Revocation and captured-generation identity still govern result application."""

from copy import deepcopy

import psycopg
import pytest
from argus.domain.business.authority import ActionError
from argus.domain.business.receipt_consent import BusinessReceiptConsentStore
from psycopg import errors
from psycopg.types.json import Jsonb

from tests import test_business_attachment_preparation_postgres as bridge
from tests import test_financial_accounts_postgres as database
from tests.business.test_business_reading_consent_version import SPANISH

actions = bridge.actions
prepared = bridge.prepared
users = bridge.users
pytestmark = bridge.pytestmark

ROUTE = {"gateway": "fixture", "interpretation": [{"model": "fixture-reader"}], "reply": []}
EARLIER_SPANISH = {
    1: (
        "Leer mis recibos del negocio con IA. Esto incluye los recibos que llegan por correo,"
        " WhatsApp y archivos subidos. La lectura crea borradores para revisar. Solo yo puedo"
        " aprobar un registro financiero. Al desactivar esta opción se detienen las nuevas lecturas."
    ),
    2: (
        "Leemos con inteligencia artificial los recibos que llegan por correo, por WhatsApp"
        " o que subes en Cuadrao, y preparamos un borrador de cada uno. Tú lo revisas y lo"
        " apruebas. Si lo apagas, se guardan sin leer."
    ),
}


def _agreed(db, space: str, owner: str, version: int, key: str, words: str) -> str:  # noqa: ANN001
    return db.execute(
        "insert into public.business_receipt_reading_consents"
        "(space_id,owner_id,scope_version,route,disclosure,idempotency_key,request_hash)"
        " values(%s,%s,%s,%s,%s,%s,%s) returning id::text",
        (space, owner, version, Jsonb(ROUTE), words, key, "a" * 64),
    ).fetchone()[0]


@pytest.mark.owner_acts
@pytest.mark.parametrize("earlier", [1, 2])
def test_earlier_scope_and_route_keep_the_original_consent(actions, earlier, faker):
    service, context, _ = actions
    route = {"gateway": faker.uuid4(), "interpretation": [{"model": faker.uuid4()}], "reply": []}
    store = BusinessReceiptConsentStore(service.authority.pool, lambda: route)
    space, owner = str(context.actor.space_id), str(context.owner_id)
    with service.authority.pool.connection() as db:
        agreed = _agreed(
            db, space, owner, earlier, f"scope-{earlier}-enable", EARLIER_SPANISH[earlier]
        )

    shown = store.status(space, owner, "es-419")
    assert (shown["enabled"], shown["consent_id"]) == (True, agreed)
    assert (shown["scope_version"], shown["disclosure"]) == (3, SPANISH)
    assert store.enabled(space, owner, agreed)

    accepted = store.set(
        space,
        owner,
        enabled=True,
        version=3,
        disclosure_token=shown["disclosure_token"],
        language="es-419",
    )

    assert accepted["enabled"] and accepted["consent_id"] == agreed
    assert store.enabled(space, owner, agreed)
    with service.authority.pool.connection() as db:
        rows = db.execute(
            "select scope_version,route,disclosure,revoked_at is null"
            " from public.business_receipt_reading_consents where space_id=%s order by consented_at",
            (space,),
        ).fetchall()
    assert rows == [(earlier, ROUTE, EARLIER_SPANISH[earlier], True)]
    store.set(space, owner, enabled=False, version=3)
    assert not store.enabled(space, owner, agreed)


@pytest.mark.owner_acts
@pytest.mark.parametrize("state", ["active", "revoked", "replaced"])
def test_completion_uses_the_captured_generation_after_configuration_changes(
    prepared, monkeypatch, faker, state
):
    service, context, _, connection_id, _, _ = prepared
    space, owner = str(context.actor.space_id), str(context.owner_id)
    route = deepcopy(ROUTE)
    route["gateway"] = faker.uuid4()
    route["interpretation"][0]["model"] = faker.uuid4()
    monkeypatch.setattr(
        "argus.domain.ingestion.whatsapp.receipt_consent.receipt_provider_route",
        lambda: route,
    )
    store = BusinessReceiptConsentStore(service.authority.pool, lambda: route)
    with service.authority.pool.connection() as db:
        agreed = _agreed(db, space, owner, 1, faker.uuid4(), EARLIER_SPANISH[1])
        db.execute(
            "update public.financial_document_extractions"
            " set draft=jsonb_set(draft,'{business_reading_consent_id}',%s)"
            " where connection_id=%s",
            (Jsonb(agreed), connection_id),
        )
    bridge.bind(prepared)
    if state != "active":
        store.set(space, owner, enabled=False, version=3)
    if state == "replaced":
        shown = store.status(space, owner)
        replacement = store.set(
            space, owner, enabled=True, version=3,
            disclosure_token=shown["disclosure_token"],
        )
        assert replacement["consent_id"] != agreed

    if state == "active":
        applied = bridge.finish(prepared)
        assert applied.outcome == "applied"
        assert bridge.finish(prepared).draft_id == applied.draft_id
    else:
        with pytest.raises(ActionError, match="document_reading_not_allowed"):
            bridge.finish(prepared)
        with service.authority.pool.connection() as db:
            assert db.execute(
                "select count(*) from public.business_draft_revisions where space_id=%s",
                (space,),
            ).fetchone() == (0,)


@pytest.mark.owner_acts
def test_a_scope_3_consent_stays_on_after_its_words_change(actions):
    service, context, _ = actions
    store = BusinessReceiptConsentStore(service.authority.pool, lambda: ROUTE)
    space, owner = str(context.actor.space_id), str(context.owner_id)
    with service.authority.pool.connection() as db:
        agreed = _agreed(db, space, owner, 3, "scope-3-enable", "Otras palabras del alcance 3.")

    shown = store.status(space, owner, "es-419")
    assert (shown["enabled"], shown["consent_id"], shown["disclosure"]) == (
        True,
        agreed,
        SPANISH,
    )
    assert store.enabled(space, owner, agreed)


@pytest.mark.owner_acts
def test_the_table_takes_scopes_1_to_3_and_no_other(actions):
    service, context, _ = actions
    space, owner = str(context.actor.space_id), str(context.owner_id)
    with service.authority.pool.connection() as db:
        for outside in (0, 4):
            with pytest.raises(errors.CheckViolation), db.transaction():
                _agreed(db, space, owner, outside, f"scope-{outside}-enable", SPANISH)
        _agreed(db, space, owner, 3, "scope-3-enable", SPANISH)


def test_scope_3_keeps_the_consent_table_server_only():
    table = "public.business_receipt_reading_consents"
    with psycopg.connect(database.DSN, autocommit=True) as db:
        security = db.execute(
            "select relrowsecurity, relforcerowsecurity from pg_class where oid = %s::regclass",
            (table,),
        ).fetchone()
        policies = db.execute(
            "select count(*) from pg_policies where schemaname='public'"
            " and tablename='business_receipt_reading_consents'"
        ).fetchone()[0]
        access = {
            role: db.execute(
                "select has_table_privilege(%s, %s, 'select'),"
                " has_table_privilege(%s, %s, 'insert'),"
                " has_table_privilege(%s, %s, 'update'),"
                " has_table_privilege(%s, %s, 'delete')",
                (role, table) * 4,
            ).fetchone()
            for role in ("anon", "authenticated", "service_role")
        }

    assert security == (True, False)
    assert policies == 0
    assert access == {
        "anon": (False, False, False, False),
        "authenticated": (False, False, False, False),
        "service_role": (True, True, True, True),
    }
