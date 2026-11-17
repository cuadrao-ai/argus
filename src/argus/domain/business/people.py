"""How a person reads to the members of one Business, read live from the
profile: a ledger row keeps only who acted. The screen picks the words; a
server-sent email uses ``mail_name``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from argus.domain.business.contracts.authority import ActorView, PersonName
from argus.domain.business.contracts.deletion import DeletedDocument
from argus.domain.business.custody_graph import ERASED_NAME

#: The email stands in for a missing name only while the person holds a live
#: grant on the Business, as Equipo lists them; a departure alias reads as the
#: erased name.
_PEOPLE = """
    select i.id, p.id is not null as known, p.display_name,
           case when exists (
               select 1 from public.business_client_grants g
               where g.space_id = %(space_id)s and g.grantee_id = i.id
                 and g.revoked_at is null
                 and (g.expires_at is null or g.expires_at > now())
           ) then u.email end as email,
           d.actor_id is not null or r.deleted_actor_id is not null as erased
    from unnest(%(ids)s::uuid[]) as i(id)
    left join public.profiles p on p.id = i.id
    left join auth.users u on u.id = i.id
    left join argus_private.business_departure_aliases d
           on d.space_id = %(space_id)s and d.actor_id = i.id
    left join argus_private.business_custody_reservations r
           on r.space_id = %(space_id)s and r.deleted_actor_id = i.id
"""


def profile_name(value: str | None) -> str | None:
    return (value or "").strip() or None


def person_name(display_name: str | None, email: str | None) -> PersonName:
    """A member named by their profile; the email only stands in for no name."""

    name = profile_name(display_name)
    return PersonName(display_name=name, email=None if name else email)


def person_label(person: PersonName | None) -> str | None:
    """A person in one line of server text: their name, else their email."""

    return person and (person.display_name or person.email)


def mail_name(display_name: str | None, email: str) -> str:
    """How an email the server sends names a person: their name, else their email."""

    return profile_name(display_name) or email


def people(
    connection: Connection, space_id: UUID | str, ids: Iterable[UUID | str | None]
) -> dict[str, PersonName | None]:
    """Each person by id as this Business's members read them now; ``None``
    for an id with no profile and no departure record."""

    wanted = sorted({str(i) for i in ids if i})
    if not wanted:
        return {}
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_PEOPLE, {"space_id": str(space_id), "ids": wanted})
        rows = cursor.fetchall()
    found: dict[str, PersonName | None] = {}
    for row in rows:
        found[str(row["id"])] = (
            PersonName(display_name=ERASED_NAME, email=None)
            if row["erased"]
            else person_name(row["display_name"], row["email"])
            if row["known"]
            else None
        )
    return found


def named(found: Mapping[str, PersonName | None], person: UUID | str) -> PersonName:
    return found.get(str(person)) or PersonName(display_name=None, email=None)


def actor_view(
    actor: Mapping[str, Any], found: Mapping[str, PersonName | None]
) -> ActorView:
    """A stored actor with both people named live, never by its stored labels."""

    person, issuer = named(found, actor["actor_id"]), named(found, actor["issuer_id"])
    return ActorView(
        actor_id=actor["actor_id"],
        actor_kind=actor["actor_kind"],
        grant_id=actor["grant_id"],
        issuer_id=actor["issuer_id"],
        display_name=person.display_name,
        email=person.email,
        issuer_display_name=issuer.display_name,
        issuer_email=issuer.email,
    )


def actor_ids(actors: Iterable[Mapping[str, Any]]) -> set[str]:
    return {str(a[key]) for a in actors for key in ("actor_id", "issuer_id")}


def named_deletion(
    marker: DeletedDocument | None, found: Mapping[str, PersonName | None]
) -> DeletedDocument | None:
    """A deletion marker with its person named live from ``found``."""

    if marker is None:
        return None
    person = named(found, marker.actor.actor_id)
    actor = marker.actor.model_copy(
        update={"display_name": person.display_name, "email": person.email}
    )
    return marker.model_copy(update={"actor": actor})
