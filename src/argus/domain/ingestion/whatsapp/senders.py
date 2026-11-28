"""Current memberships and Business setup for a person's WhatsApp link."""

from collections.abc import Callable
from dataclasses import dataclass

from psycopg import Connection

from argus.domain.business.access import AccessStore, GrantedSpace, PostgresAccessStore
from argus.domain.business.contracts.dgii import TaxId
from argus.domain.business.receipt_consent import BusinessReceiptConsentStore
from argus.domain.postgres_connection import BorrowedConnection


def preparing_businesses(access: AccessStore, person_id: str) -> tuple[GrantedSpace, ...]:
    return tuple(
        grant for grant in access.spaces_for(person_id) if "prepare" in grant.permissions
    )


@dataclass(frozen=True)
class SenderBusinesses:
    access: AccessStore
    tax_id: Callable[[str], TaxId | None]
    reading_status: Callable[[GrantedSpace], dict]

    def eligible_businesses(self, person_id: str) -> tuple[GrantedSpace, ...]:
        return tuple(grant for grant, _ in self.with_tax_ids(person_id))

    def with_tax_ids(self, person_id: str) -> tuple[tuple[GrantedSpace, TaxId], ...]:
        return tuple(
            (grant, tax_id)
            for grant in preparing_businesses(self.access, person_id)
            if (tax_id := self.tax_id(grant.space_id)) is not None
            and "prepare" in self.access.capabilities(grant.space_id, person_id)
            and self.reading_status(grant)["enabled"]
        )


def postgres_senders(db: Connection) -> SenderBusinesses:
    pool = BorrowedConnection(db)
    reading = BusinessReceiptConsentStore(pool)
    access = PostgresAccessStore(pool)

    def tax_id(space_id: str) -> TaxId | None:
        row = db.execute(
            "select business_tax_id_type, business_rnc from public.spaces"
            " where id=%s and business_rnc is not null for share",
            (space_id,),
        ).fetchone()
        return TaxId(type=row[0], value=row[1]) if row else None

    def reading_status(grant: GrantedSpace) -> dict:
        # The receipt store takes its storage partition from the grant.
        return reading.status_on_connection(db, grant.space_id, grant.owner_id, lock=True)

    return SenderBusinesses(access, tax_id, reading_status)
