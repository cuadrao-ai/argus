"""Who brought a document into the Bandeja, with a stable sender filter id."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import model_validator

from argus.domain.business.contracts.authority import PersonName
from argus.domain.business.contracts.facts import Contract
from argus.domain.business.people import named, people
from argus.domain.ingestion.email_intake.alignment import bare_address


class SentBy(Contract):
    """A person's sender id is shared across channels. An unnamed WhatsApp sender shows only the last four digits."""

    id: str
    kind: Literal["member", "email", "whatsapp"]
    #: The member, named for the viewer as ``people`` reads them.
    person: PersonName | None = None
    address: str | None = None
    phone_last4: str | None = None

    @model_validator(mode="after")
    def _one_sender(self) -> SentBy:
        shown = {
            "member": self.person,
            "email": self.address,
            "whatsapp": self.phone_last4,
        }
        if [kind for kind, value in shown.items() if value is not None] != [self.kind]:
            raise ValueError("a sender carries exactly what its kind names")
        return self


def member_sender(actor_id: UUID | str, person: PersonName) -> SentBy:
    return SentBy(id=f"member:{actor_id}", kind="member", person=person)


def email_sender(sender: str | None) -> SentBy | None:
    """The address an email came from; none when it carries no usable one."""

    address = bare_address(sender)
    return address and SentBy(id=f"email:{address}", kind="email", address=address)


def receipt_senders(tx, views: list[dict]) -> dict[str, SentBy]:  # noqa: ANN001
    """Read the uploader, earliest email delivery, or earliest WhatsApp capture."""

    space_id = tx.context.actor.space_id
    by_channel: dict[str, list[dict]] = {}
    for view in views:
        by_channel.setdefault(view.get("channel"), []).append(view)
    sent: dict[str, SentBy] = {}
    if uploads := by_channel.get("web"):
        rows = tx.rows(
            "select distinct on (subject) subject, actor_id"
            " from public.business_action_receipts,"
            " jsonb_array_elements_text(command->'subjects') subject"
            " where space_id=%s and command->>'action'='receipt_upload'"
            " and outcome->>'outcome'='applied' and subject = any(%s)"
            " order by subject, created_at",
            (space_id, [view["id"] for view in uploads]),
        )
        found = people(tx.connection, tx.authorization, [row["actor_id"] for row in rows])
        for row in rows:
            actor = row["actor_id"]
            sent[row["subject"]] = member_sender(actor, named(found, actor))
    first = {
        view["id"]: view["email_delivery_ids"][0]
        for view in by_channel.get("email", [])
        if view.get("email_delivery_ids")
    }
    if first:
        senders = {
            row["id"]: email_sender(row["sender"])
            for row in tx.rows(
                "select id::text as id, sender from public.business_email_deliveries"
                " where space_id=%s and id::text = any(%s)",
                (space_id, sorted(set(first.values()))),
            )
        }
        for receipt, delivery in first.items():
            if sender := senders.get(delivery):
                sent[receipt] = sender
    if messages := by_channel.get("whatsapp"):
        rows = tx.rows(
            "select m.receipt, l.id as link, l.destination_owner_id as actor, l.last4"
            " from (select distinct on (i.connection_id) i.connection_id::text as receipt,"
            " i.sender_link_id from public.whatsapp_inbound_messages i"
            " join public.financial_source_connections c on c.id=i.connection_id"
            " where c.owner_space_id=%s and i.status='captured' and c.id=any(%s::uuid[])"
            " order by i.connection_id, i.received_at, i.id) m"
            " join public.whatsapp_sender_links l on l.id=m.sender_link_id",
            (space_id, [view["id"] for view in messages]),
        )
        found = people(tx.connection, tx.authorization, (row["actor"] for row in rows))
        for row in rows:
            actor = row["actor"]
            person = found.get(str(actor))
            if person and person.display_name:
                sent[row["receipt"]] = member_sender(actor, person)
            else:
                sent[row["receipt"]] = SentBy(
                    id=f"member:{actor}" if actor else f"whatsapp:{row['link']}",
                    kind="whatsapp",
                    phone_last4=row["last4"],
                )
    return sent
