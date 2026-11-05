from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row


class AppleIdentityUnavailable(RuntimeError):
    """Auth identities could not establish one unambiguous subject."""


@dataclass(frozen=True)
class LinkedAppleIdentity:
    subject: str = field(repr=False)


def parse_linked_apple_identity(
    identities: Iterable[Mapping[str, Any]],
) -> LinkedAppleIdentity | None:
    subjects: set[str] = set()
    for identity in identities:
        if not isinstance(identity, Mapping) or not isinstance(
            identity.get("provider"), str
        ):
            raise AppleIdentityUnavailable("malformed_identity")
        if identity["provider"] != "apple":
            continue
        data = identity.get("identity_data")
        subject = data.get("sub") if isinstance(data, Mapping) else None
        provider_id = identity.get("provider_id")
        if (
            not isinstance(subject, str)
            or not 1 <= len(subject) <= 512
            or any(character.isspace() or ord(character) < 32 for character in subject)
            or not isinstance(provider_id, str)
            or provider_id != subject
        ):
            raise AppleIdentityUnavailable("malformed_apple_identity")
        subjects.add(subject)
    if len(subjects) > 1:
        raise AppleIdentityUnavailable("conflicting_apple_identities")
    return LinkedAppleIdentity(subjects.pop()) if subjects else None


def linked_apple_identity(
    connection: Connection, user_id: str, *, lock: bool = False
) -> LinkedAppleIdentity | None:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            "select provider, provider_id, identity_data from auth.identities "
            "where user_id = %s::uuid" + (" for share" if lock else ""),
            (user_id,),
        )
        return parse_linked_apple_identity(cursor.fetchall())
