"""Close notifications committed with the Business command, never live in tests.

Member close notices, owner close confirmations, day-23 reminders and member
reopen notices are approved for delivery.
"""

from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

from babel.dates import format_date
from psycopg.types.json import Jsonb

from argus.domain import resend_email
from argus.domain.business.lifecycle import REOPEN_WINDOW
from argus.domain.business.transfer_mail import _origin

MailKind = Literal["member_closed", "owner_closed", "purge_reminder", "member_reopened"]
_ARTIFACT = Path(__file__).with_name("business_closed_email.generated.json")
#: Delivery activation is separate from template approval.
_APPROVED_KINDS = frozenset(
    {"member_closed", "owner_closed", "purge_reminder", "member_reopened"}
)
_RETRY_WINDOW = timedelta(hours=23)
#: The owner's reminder goes out a week before the purge deadline.
REMINDER_AFTER = timedelta(days=23)
# A recipient who can still receive personal mail.
_REACHABLE = (
    " u.email is not null and u.email_confirmed_at is not null"
    " and coalesce(u.is_anonymous,false)=false and (u.banned_until is null or u.banned_until<=clock_timestamp())"
    " and not exists(select 1 from argus_private.account_deletion_runs d where d.user_id=u.id)"
)
_MEMBERS = (
    " from public.business_client_grants g join auth.users u on u.id=g.grantee_id"
    " where g.space_id=%(space)s and g.grantee_id<>%(owner)s and g.revoked_at is null"
    " and (g.expires_at is null or g.expires_at>clock_timestamp()) and 'read'=any(g.capabilities) and"
    + _REACHABLE
)
_OWNER = " from auth.users u where u.id=%(owner)s and" + _REACHABLE
# A queued event still holds while the Business is at that close instant (or
# open again, for a reopen notice), an owner notice still reaches the current
# owner, and the recipient can still receive personal mail.
_STILL_DUE = (
    " case when o.kind='member_reopened' then s.closed_at is null else s.closed_at=o.closed_at end"
    " and (o.kind not in ('owner_closed','purge_reminder') or s.current_owner_id=o.recipient_id)"
    " and exists(select 1 from auth.users u where u.id=o.recipient_id and u.email=o.recipient_email and"
    + _REACHABLE
    + ")"
)


def reopen_path(space_id: str) -> str:
    """Where the owner reopens a closed Business in the web app."""
    return "/biz?" + urlencode({"lifecycle": "manage", "business": space_id})


def _local_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Close mail dates must include a timezone")
    return parsed.astimezone(ZoneInfo("America/Santo_Domingo"))


def _application_link(context: dict[str, str], kind: MailKind) -> str:
    origin = os.getenv("CUADRAO_APP_ORIGIN") or os.getenv("ARGUS_APP_ORIGIN") or ""
    if any(character in origin for character in "\\?#"):
        raise ValueError("Email origin must be an HTTPS origin")
    origin = _origin(origin)
    _ = urlsplit(origin).port
    if kind == "member_reopened":
        return origin + "/biz"
    path = context.get("reopenPath", "")
    parsed = urlsplit(path)
    parameters = parse_qsl(parsed.query, keep_blank_values=True)
    query = dict(parameters)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.path != "/biz"
        or "#" in path
        or "\\" in path
        or any(character.isspace() for character in path)
        or len(parameters) != 2
        or set(query) != {"lifecycle", "business"}
        or query["lifecycle"] != "manage"
        or str(UUID(query["business"])) != query["business"].lower()
    ):
        raise ValueError("Close mail link must navigate to business management")
    return origin + path


def render_close_mail(
    context: dict[str, str],
    *,
    kind: MailKind = "member_closed",
    locale: Literal["es-419", "en"] = "es-419",
) -> dict[str, str]:
    artifact = json.loads(_ARTIFACT.read_text())
    if (
        artifact["schemaVersion"] != 1
        or kind
        not in ("member_closed", "owner_closed", "purge_reminder", "member_reopened")
        or locale not in ("es-419", "en")
    ):
        raise ValueError("Unsupported close mail artifact")
    if any(
        not value.strip() or re.search(r"[\x00-\x1f\x7f]", value)
        for value in context.values()
    ):
        raise ValueError("Close mail fields must be nonempty single-line values")
    closed = _local_timestamp(context["closedAt"])
    purge = _local_timestamp(context["purgeAt"])
    date_locale = "en_US" if locale == "en" and kind != "member_closed" else "es_DO"
    values = {
        "businessName": context["businessName"],
        "ownerName": context["ownerName"],
        "closedDate": format_date(closed, "long", locale=date_locale),
        "purgeDate": format_date(purge, "long", locale=date_locale),
        "purgeTime": purge.strftime("%H:%M:%S"),
        # The shared layout adds a postal line only beside an unsubscribe link.
        "postalAddress": "Cuadrao LLC",
        "assetOrigin": _origin(
            os.getenv("CUADRAO_EMAIL_ASSET_ORIGIN") or "https://cuadrao.ai"
        ),
    }
    if kind != "member_closed":
        values["businessUrl" if kind == "member_reopened" else "actionUrl"] = (
            _application_link(context, kind)
        )
    if any(
        not value.strip() or "\n" in value or "\r" in value for value in values.values()
    ):
        raise ValueError("Close mail fields must be nonempty single-line values")
    template = (
        artifact if kind == "member_closed" else artifact["templates"][locale][kind]
    )
    rendered = {}
    for field in ("subject", "html", "text"):
        escape = (
            (lambda value: html.escape(value, quote=True)) if field == "html" else str
        )
        replacements = {
            escape(token): escape(values[key])
            for key, token in artifact["tokens"].items()
            if key in values
        }
        pattern = re.compile("|".join(re.escape(token) for token in replacements))
        rendered[field] = pattern.sub(
            lambda match, replacements=replacements: replacements[match[0]],
            template[field],
        )
    return rendered


def _context(db, space_id: str, owner_id: str, name: str, closed_at: datetime) -> dict:
    owner = db.execute(
        "select coalesce(nullif(btrim(display_name),''),username,'Member') from public.profiles where id=%s",
        (owner_id,),
    ).fetchone()
    return {
        "businessName": name,
        "ownerName": owner[0] if owner else "Member",
        "closedAt": closed_at.isoformat(),
        "purgeAt": (closed_at + REOPEN_WINDOW).isoformat(),
        "reopenPath": reopen_path(space_id),
    }


def _queue(db, kind: MailKind, recipients: str, **event) -> None:
    """One row per recipient for this close instant and kind, once."""
    db.execute(
        "insert into public.business_close_mail_outbox(kind,space_id,closed_at,owner_id,recipient_id,recipient_email,context)"
        " select distinct %(kind)s::text,%(space)s::uuid,%(closed)s,%(owner)s::uuid,u.id,u.email,%(context)s"
        + recipients
        + " on conflict do nothing",
        {"kind": kind, **event},
    )


def enqueue_close_mail(
    db, space_id: str, owner_id: str, name: str, closed_at: datetime
) -> None:
    context = Jsonb(_context(db, space_id, owner_id, name, closed_at))
    event = dict(space=space_id, closed=closed_at, owner=owner_id, context=context)
    _queue(db, "member_closed", _MEMBERS, **event)
    _queue(db, "owner_closed", _OWNER, **event)


def enqueue_reopen_mail(
    db, space_id: str, owner_id: str, name: str, closed_at: datetime
) -> None:
    """Members whose access returns, for the close instant that was undone."""
    context = Jsonb(_context(db, space_id, owner_id, name, closed_at))
    _queue(
        db,
        "member_reopened",
        _MEMBERS,
        space=space_id,
        closed=closed_at,
        owner=owner_id,
        context=context,
    )


def enqueue_purge_reminders(pool) -> tuple[str, ...]:
    """Queue the current owner's day-23 reminder for each closed Business
    still inside its reopen window; returns the Businesses reminded now."""
    with pool.connection() as db, db.transaction():
        rows = db.execute(
            "select id::text,name,current_owner_id::text,closed_at from public.spaces"
            " where kind='business' and current_owner_id is not null"
            " and closed_at<=clock_timestamp()-%s and closed_at>clock_timestamp()-%s"
            " order by closed_at,id",
            (REMINDER_AFTER, REOPEN_WINDOW),
        ).fetchall()
        for space_id, name, owner_id, closed_at in rows:
            _queue(
                db,
                "purge_reminder",
                _OWNER,
                space=space_id,
                closed=closed_at,
                owner=owner_id,
                context=Jsonb(_context(db, space_id, owner_id, name, closed_at)),
            )
    return tuple(row[0] for row in rows)


def deliver_close_mail(pool, space_id: str) -> int:
    if not (os.getenv(resend_email.SMTP_PASSWORD_ENV) or "").strip():
        return 0
    with pool.connection() as db:
        ids = db.execute(
            "select id::text from public.business_close_mail_outbox where space_id=%s and sent_at is null and suppressed_at is null and uncertain_at is null order by created_at,id",
            (space_id,),
        ).fetchall()
    sent = 0
    for (mail_id,) in ids:
        with pool.connection() as db, db.transaction():
            db.execute("set local lock_timeout='5s'; set local statement_timeout='60s'")
            db.execute("select id from public.spaces where id=%s for update", (space_id,))
            row = db.execute(
                "select o.context,o.first_attempt_at,o.payload,o.sent_at,o.suppressed_at,o.uncertain_at,clock_timestamp(),"
                + _STILL_DUE
                + ",o.kind from public.business_close_mail_outbox o join public.spaces s on s.id=o.space_id where o.id=%s for update of o",
                (mail_id,),
            ).fetchone()
            if not row or any(value is not None for value in row[3:6]):
                continue
            if not row[7]:
                db.execute(
                    "update public.business_close_mail_outbox set suppressed_at=clock_timestamp() where id=%s",
                    (mail_id,),
                )
                continue
            if row[8] not in _APPROVED_KINDS:
                continue
            if row[1] is None:
                try:
                    payload = render_close_mail(row[0], kind=row[8])
                except ValueError:
                    continue
                db.execute(
                    "update public.business_close_mail_outbox set first_attempt_at=clock_timestamp(),payload=%s where id=%s",
                    (Jsonb(payload), mail_id),
                )
        with pool.connection() as db, db.transaction():
            db.execute("set local lock_timeout='5s'; set local statement_timeout='60s'")
            db.execute("select id from public.spaces where id=%s for update", (space_id,))
            row = db.execute(
                "select o.recipient_email,o.payload,o.first_attempt_at,o.sent_at,o.suppressed_at,o.uncertain_at,clock_timestamp(),"
                + _STILL_DUE
                + ",o.kind from public.business_close_mail_outbox o join public.spaces s on s.id=o.space_id where o.id=%s for update of o",
                (mail_id,),
            ).fetchone()
            if not row or any(value is not None for value in row[3:6]):
                continue
            if row[8] not in _APPROVED_KINDS:
                continue
            if not row[7]:
                db.execute(
                    "update public.business_close_mail_outbox set suppressed_at=clock_timestamp() where id=%s",
                    (mail_id,),
                )
                continue
            if row[6] >= row[2] + _RETRY_WINDOW:
                db.execute(
                    "update public.business_close_mail_outbox set uncertain_at=clock_timestamp() where id=%s",
                    (mail_id,),
                )
                continue
            try:
                receipt = resend_email.send_resend_email(
                    recipient=row[0],
                    subject=row[1]["subject"],
                    plain_text=row[1]["text"],
                    html=row[1]["html"],
                    idempotency_key=f"business-close/{mail_id}",
                )
            except (OSError, RuntimeError):
                continue
            db.execute(
                "update public.business_close_mail_outbox set sent_at=clock_timestamp(),provider_receipt=%s where id=%s",
                (receipt[:256], mail_id),
            )
            sent += 1
    return sent
