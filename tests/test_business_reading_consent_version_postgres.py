"""An owner who agreed to the scope 1 wording is asked again: reading stays off
for them, and a read bound to that agreement is refused, until they accept the
scope 2 sentence. Accepting it ends the scope 1 generation."""

import pytest
from argus.domain.business.receipt_consent import BusinessReceiptConsentStore
from psycopg import errors
from psycopg.types.json import Jsonb

from tests import test_business_attachment_preparation_postgres as bridge
from tests.business.test_business_reading_consent_version import SPANISH

actions = bridge.actions
users = bridge.users
pytestmark = bridge.pytestmark

ROUTE = {"gateway": "fixture", "interpretation": [{"model": "fixture-reader"}], "reply": []}
SCOPE_1_SPANISH = (
    "Leer mis recibos del negocio con IA. Esto incluye los recibos que llegan por correo,"
    " WhatsApp y archivos subidos. La lectura crea borradores para revisar. Solo yo puedo"
    " aprobar un registro financiero. Al desactivar esta opción se detienen las nuevas lecturas."
)


def _agreed(db, space: str, owner: str, version: int, key: str) -> str:  # noqa: ANN001
    return db.execute(
        "insert into public.business_receipt_reading_consents"
        "(space_id,owner_id,scope_version,route,disclosure,idempotency_key,request_hash)"
        " values(%s,%s,%s,%s,%s,%s,%s) returning id::text",
        (space, owner, version, Jsonb(ROUTE), SCOPE_1_SPANISH, key, "a" * 64),
    ).fetchone()[0]


@pytest.mark.owner_acts
def test_an_owner_who_agreed_to_scope_1_is_asked_again(actions):
    service, context, _ = actions
    store = BusinessReceiptConsentStore(service.authority.pool, lambda: ROUTE)
    space, owner = str(context.actor.space_id), str(context.owner_id)
    with service.authority.pool.connection() as db:
        earlier = _agreed(db, space, owner, 1, "scope-1-enable")

    shown = store.status(space, owner, "es-419")
    assert (shown["enabled"], shown["consent_id"]) == (False, earlier)
    assert (shown["scope_version"], shown["disclosure"]) == (2, SPANISH)
    assert not store.enabled(space, owner, earlier)

    accepted = store.set(
        space,
        owner,
        enabled=True,
        version=2,
        disclosure_token=shown["disclosure_token"],
        language="es-419",
    )

    assert accepted["enabled"] and accepted["consent_id"] != earlier
    assert store.enabled(space, owner, accepted["consent_id"])
    assert not store.enabled(space, owner, earlier)
    with service.authority.pool.connection() as db:
        rows = db.execute(
            "select scope_version,disclosure,revoked_at is null"
            " from public.business_receipt_reading_consents where space_id=%s order by consented_at",
            (space,),
        ).fetchall()
    assert rows == [(1, SCOPE_1_SPANISH, False), (2, SPANISH, True)]


@pytest.mark.owner_acts
def test_the_table_takes_scope_1_and_2_and_no_other(actions):
    service, context, _ = actions
    space, owner = str(context.actor.space_id), str(context.owner_id)
    with service.authority.pool.connection() as db:
        with pytest.raises(errors.CheckViolation), db.transaction():
            _agreed(db, space, owner, 3, "scope-3-enable")
        _agreed(db, space, owner, 2, "scope-2-enable")
