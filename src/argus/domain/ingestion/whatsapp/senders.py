"""Current memberships and Business setup for a person's WhatsApp link."""

from collections.abc import Callable
from dataclasses import dataclass

from psycopg import Connection

from argus.domain.business.access import AccessStore, GrantedSpace, PostgresAccessStore
from argus.domain.business.receipt_consent import BusinessReceiptConsentStore
from argus.domain.postgres_connection import BorrowedConnection


def preparing_businesses(access: AccessStore, person_id: str) -> tuple[GrantedSpace, ...]:
    return tuple(
        grant for grant in access.spaces_for(person_id) if "prepare" in grant.permissions
    )


@dataclass(frozen=True)
class SenderBusinesses:
    access: AccessStore
    has_tax_id: Callable[[str], bool]
    reading_status: Callable[[GrantedSpace], dict]

    def eligible_businesses(self, person_id: str) -> tuple[GrantedSpace, ...]:
        return tuple(
            grant
            for grant in preparing_businesses(self.access, person_id)
            if self.has_tax_id(grant.space_id)
            and "prepare" in self.access.capabilities(grant.space_id, person_id)
            and self.reading_status(grant)["enabled"]
        )


def postgres_senders(db: Connection) -> SenderBusinesses:
    pool = BorrowedConnection(db)
    reading = BusinessReceiptConsentStore(pool)
    access = PostgresAccessStore(pool)

    def has_tax_id(space_id: str) -> bool:
        return bool(
            db.execute(
                "select 1 from public.spaces where id=%s and business_rnc is not null for share",
                (space_id,),
            ).fetchone()
        )

    def reading_status(grant: GrantedSpace) -> dict:
        # The receipt store takes its storage partition from the grant.
        return reading.status_on_connection(db, grant.space_id, grant.owner_id, lock=True)

    return SenderBusinesses(access, has_tax_id, reading_status)
