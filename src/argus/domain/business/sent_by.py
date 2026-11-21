"""Who brought a document into the Bandeja, one answer for every channel: the
member who uploaded a file or typed a note, the address an email came from, or
the linked WhatsApp number by its last four digits, all that is stored of it.
``id`` is the same for the same sender on every row and never collides across
kinds."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import model_validator

from argus.domain.business.contracts.authority import PersonName
from argus.domain.business.contracts.facts import Contract
from argus.domain.business.people import named, people
from argus.domain.ingestion.email_intake.alignment import bare_address


class SentBy(Contract):
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
    """Who sent each receipt, by its channel. A web upload: the member on the
    first ledger row its upload wrote. An email: the sender of the earliest
    delivery that brought it. WhatsApp: the number's first link to this
    Business, so a number linked again keeps one id."""

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
        for row in tx.rows(
            "select distinct on (m.connection_id) m.connection_id::text as receipt,"
            " l.id::text as link, l.last4"
            " from public.whatsapp_inbound_messages m"
            " join public.whatsapp_sender_links l on l.wa_id_hash=m.sender_hash"
            " and l.destination_space_id=%s"
            " where m.status='captured' and m.connection_id::text = any(%s)"
            " order by m.connection_id, l.linked_at, l.id",
            (space_id, [view["id"] for view in messages]),
        ):
            sent[row["receipt"]] = SentBy(
                id=f"whatsapp:{row['link']}", kind="whatsapp", phone_last4=row["last4"]
            )
    return sent
