"""Synthetic phone-link setup and the notices used in both language fixtures."""

from argus.domain.business.access import PostgresAccessStore
from faker import Faker
from psycopg_pool import ConnectionPool

from tests.business_reading_support import reading_setting

NOTICE = (
    "Al vincular tu número, aceptas que la foto o el PDF que envíes se lea con IA "
    "para saber a qué negocio va."
)


ENGLISH_NOTICE = (
    "By linking your number, you agree that the photo or PDF you send is read by AI "
    "to find which business it belongs to."
)


def prepare_phone_business(pool: ConnectionPool, space_id: str, person: str) -> None:
    with pool.connection() as db:
        db.execute(
            "update public.spaces set business_rnc=%s, business_tax_id_type='rnc'"
            " where id=%s and business_rnc is null",
            (Faker().numerify("1########"), space_id),
        )
    grant = next(g for g in PostgresAccessStore(pool).spaces_for(person) if g.space_id == space_id)
    reading = reading_setting(pool)
    status = reading.status(space_id, grant.owner_id)
    if not status["enabled"]:
        reading.set(
            space_id, grant.owner_id, actor_id=person, enabled=True,
            version=status["scope_version"], disclosure_token=status["disclosure_token"],
        )
