"""How a person reads to one viewer of a Business, read live from the
profile: a ledger row keeps only who acted. The screen picks the words; a
server-sent email uses ``mail_name``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from argus.domain.business.contracts.authority import ActorView, PersonName
from argus.domain.business.contracts.deletion import DeletedDocument

if TYPE_CHECKING:
    from argus.domain.business.authority import Authorization

#: ``member``: the person holds a live grant on the Business, as Equipo lists
#: them. A departure alias is an erased account.
_PEOPLE = """
    select i.id, p.id is not null as known, p.display_name, u.email,
           exists (
               select 1 from public.business_client_grants g
               where g.space_id = %(space_id)s and g.grantee_id = i.id
                 and g.revoked_at is null
                 and (g.expires_at is null or g.expires_at > now())
           ) as member,
           d.actor_id is not null or r.deleted_actor_id is not null as erased
    from unnest(%(ids)s::uuid[]) as i(id)
    left join public.profiles p on p.id = i.id
    left join auth.users u on u.id = i.id
    left join argus_private.business_departure_aliases d
           on d.space_id = %(space_id)s and d.actor_id = i.id
    left join argus_private.business_custody_reservations r
           on r.space_id = %(space_id)s and r.deleted_actor_id = i.id
"""

FORMER = PersonName(display_name=None, shown_as="former")


def profile_name(value: str | None) -> str | None:
    return (value or "").strip() or None


def person_name(
    display_name: str | None, email: str | None, *, member: bool, sees_email: bool
) -> PersonName:
    """A person by their profile name. With none, someone who left is a former
    member, and the email shows only to a viewer allowed to see it."""

    name = profile_name(display_name)
    if name:
        return PersonName(display_name=name, shown_as="name")
    if not member:
        return FORMER
    if sees_email and email:
        return PersonName(display_name=None, email=email, shown_as="email")
    return PersonName(display_name=None, shown_as="member")


def person_label(person: PersonName | None) -> str | None:
    """A person in one line of server text: what the viewer may read of them."""

    return person and (person.display_name or person.email)


def mail_name(display_name: str | None, email: str) -> str:
    """How an email the server sends names a person: their name, else their email."""

    return profile_name(display_name) or email


def people(
    connection: Connection, viewer: Authorization, ids: Iterable[UUID | str | None]
) -> dict[str, PersonName | None]:
    """Each person by id as ``viewer`` reads them now in the viewer's Business;
    ``None`` for an id with no profile and no departure record. A viewer who
    manages the Business reads an unnamed member's email; so does that member."""

    wanted = sorted({str(i) for i in ids if i})
    if not wanted:
        return {}
    space_id = viewer.context.actor.space_id
    manages = "manage" in viewer.permissions
    me = str(viewer.context.actor.actor_id)
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_PEOPLE, {"space_id": str(space_id), "ids": wanted})
        rows = cursor.fetchall()
    found: dict[str, PersonName | None] = {}
    for row in rows:
        person = str(row["id"])
        found[person] = (
            FORMER
            if row["erased"]
            else person_name(
                row["display_name"],
                row["email"],
                member=row["member"],
                sees_email=manages or person == me,
            )
            if row["known"]
            else None
        )
    return found


def named(found: Mapping[str, PersonName | None], person: UUID | str) -> PersonName:
    return found.get(str(person)) or FORMER


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
        shown_as=person.shown_as,
        issuer_display_name=issuer.display_name,
        issuer_email=issuer.email,
        issuer_shown_as=issuer.shown_as,
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
        update=person.model_dump(include={"display_name", "email", "shown_as"})
    )
    return marker.model_copy(update={"actor": actor})
