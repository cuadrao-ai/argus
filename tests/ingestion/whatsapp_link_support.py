"""Synthetic phone-link setup and the notices used in both language fixtures."""

from argus.domain.business.access import PostgresAccessStore
from argus.domain.business.contracts.dgii import TaxId
from argus.domain.ingestion.whatsapp.ai_consent import LINK_DISCLOSURES
from faker import Faker
from psycopg_pool import ConnectionPool

from tests.business_reading_support import reading_setting

SYNTHETIC_TAX_ID = TaxId(type="rnc", value="131456782")
NOTICE = LINK_DISCLOSURES["es-419"]
ENGLISH_NOTICE = LINK_DISCLOSURES["en"]


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
