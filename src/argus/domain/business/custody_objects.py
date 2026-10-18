"""Prepare tracked, verified receipt copies without moving or deleting records."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from uuid import uuid4

from psycopg_pool import ConnectionPool

from argus.domain.account_deletion.auth_admin import AuthAdmin, placeholder_email
from argus.domain.ingestion.documents.objects import SourceObjects, source_path


class CustodyCopyError(RuntimeError):
    pass


@dataclass(frozen=True)
class CustodyReservation:
    space_id: str
    custodian_id: str
    deleted_actor_id: str


@dataclass(frozen=True)
class CustodyObject:
    source: str
    destination: str
    digest: str
    size: int
    media_type: str


class PostgresBusinessCustodyCopies:
    def __init__(
        self, pool: ConnectionPool, objects: SourceObjects, auth: AuthAdmin
    ) -> None:
        self.pool, self.objects, self.auth = pool, objects, auth

    def prepare(self, *, space_id: str, departing_user_id: str) -> CustodyReservation:
        reservation = self._reserve(space_id, departing_user_id)
        if not self.auth.user_exists(reservation.custodian_id):
            self.auth.create_placeholder(
                user_id=reservation.custodian_id,
                email=placeholder_email(reservation.custodian_id),
            )
        with self.pool.connection() as db:
            db.execute(
                "update argus_private.business_custody_reservations set auth_ready_at=coalesce(auth_ready_at,clock_timestamp()) where space_id=%s",
                (space_id,),
            )
        for item in self._manifest(reservation, departing_user_id):
            original = self.objects.get(item.source)
            self._verify(original, item)
            self.objects.put(item.destination, original, item.media_type)
            self._verify(self.objects.get(item.destination), item)
            with self.pool.connection() as db:
                db.execute(
                    "update argus_private.business_custody_objects set verified_at=clock_timestamp() where space_id=%s and source_path=%s and destination_path=%s and sha256=%s and size_bytes=%s",
                    (space_id, item.source, item.destination, item.digest, item.size),
                )
        return reservation

    def _reserve(self, space_id: str, departing_user_id: str) -> CustodyReservation:
        with self.pool.connection() as db, db.transaction():
            row = db.execute(
                "select current_owner_id::text,closed_at from public.spaces where id=%s and created_by=%s and kind='business' for update",
                (space_id, departing_user_id),
            ).fetchone()
            if not row:
                raise CustodyCopyError("business_record_not_found")
            if row == (departing_user_id, None):
                raise CustodyCopyError("business_owner_must_exit")
            db.execute(
                "insert into argus_private.business_custody_reservations(space_id,custodian_id,deleted_actor_id) values(%s,%s,%s) on conflict(space_id) do nothing",
                (space_id, uuid4(), uuid4()),
            )
            saved = db.execute(
                "select space_id::text,custodian_id::text,deleted_actor_id::text from argus_private.business_custody_reservations where space_id=%s",
                (space_id,),
            ).fetchone()
            db.execute(
                "insert into argus_private.account_placeholders(id) values(%s) on conflict do nothing",
                (saved[1],),
            )
            return CustodyReservation(*saved)

    def _manifest(
        self, reservation: CustodyReservation, user_id: str
    ) -> tuple[CustodyObject, ...]:
        with self.pool.connection() as db, db.transaction():
            rows = db.execute(
                "select d.source_path,d.source_sha256,d.source_size_bytes,d.source_media_type,d.source_bucket,d.rebuilt_path,d.rebuilt_sha256,d.rebuilt_size_bytes,d.rebuilt_media_type,d.rebuilt_bucket,d.draft->>'sha256',d.source_bytes from public.financial_document_extractions d join public.financial_source_connections c on c.id=d.connection_id and c.user_id=d.user_id where c.owner_space_id=%s and c.user_id=%s order by d.connection_id for share of c,d",
                (reservation.space_id, user_id),
            ).fetchall()
            for row in rows:
                if row[11] is not None:
                    if sha256(bytes(row[11])).hexdigest() != row[10]:
                        raise CustodyCopyError("business_source_integrity_failed")
                for offset, kind in ((0, "sealed"), (5, "rebuilt")):
                    old, digest, size, media, bucket = row[offset : offset + 5]
                    if old is None:
                        continue
                    if bucket != self.objects.bucket or not all(
                        value is not None for value in (digest, size, media, row[10])
                    ):
                        raise CustodyCopyError("business_source_metadata_missing")
                    if not old.startswith((f"{user_id}/", f"{kind}/{user_id}/")):
                        raise CustodyCopyError("business_source_scope_mismatch")
                    path = source_path(
                        user_id=reservation.custodian_id, sha256=row[10], kind=kind
                    )
                    db.execute(
                        "insert into argus_private.business_custody_objects(space_id,source_path,destination_path,sha256,size_bytes,media_type) values(%s,%s,%s,%s,%s,%s) on conflict(space_id,source_path) do nothing",
                        (reservation.space_id, old, path, digest, size, media),
                    )
                    saved = db.execute(
                        "select destination_path,sha256,size_bytes,media_type from argus_private.business_custody_objects where space_id=%s and source_path=%s",
                        (reservation.space_id, old),
                    ).fetchone()
                    if saved != (path, digest, size, media):
                        raise CustodyCopyError("business_source_manifest_changed")
            objects = db.execute(
                "select source_path,destination_path,sha256,size_bytes,media_type from argus_private.business_custody_objects where space_id=%s order by source_path",
                (reservation.space_id,),
            ).fetchall()
            return tuple(CustodyObject(*row) for row in objects)

    @staticmethod
    def _verify(content: bytes | None, item: CustodyObject) -> None:
        if (
            content is None
            or len(content) != item.size
            or sha256(content).hexdigest() != item.digest
        ):
            raise CustodyCopyError("business_source_integrity_failed")
