"""Durable per-recipient mail for transfer commands, using the shared Resend path."""

from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from babel.dates import format_date, format_time
from psycopg import Connection
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from argus.domain import resend_email

_TIME_ZONE = "America/Santo_Domingo"
_RETRY_WINDOW = timedelta(hours=23)
_ARTIFACT = Path(__file__).with_name("business_transfer_email.generated.json")


def _origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or any(char.isspace() for char in value)
    ):
        raise ValueError("Email origin must be an HTTPS origin")
    return value.rstrip("/")


def render_transfer_mail(variant: str, context: dict[str, str]) -> dict[str, str]:
    artifact = json.loads(_ARTIFACT.read_text())
    if artifact["schemaVersion"] != 1:
        raise ValueError("Unsupported transfer mail artifact")
    app_origin = _origin(
        os.getenv("CUADRAO_APP_ORIGIN") or os.getenv("ARGUS_APP_ORIGIN") or ""
    )
    from zoneinfo import ZoneInfo

    local = ZoneInfo(_TIME_ZONE)
    occurred = datetime.fromisoformat(context["occurredAt"]).astimezone(local)
    expires = datetime.fromisoformat(context["expiresAt"]).astimezone(local)
    data = {
        "businessName": context["businessName"],
        "ownerName": context["ownerName"],
        "targetName": context["targetName"],
        "eventDate": format_date(occurred, "long", locale="es_DO"),
        "eventTime": format_time(occurred, "h:mm a", locale="es_DO"),
        "expiresDate": format_date(expires, "long", locale="es_DO"),
        "transferUrl": app_origin
        + "/biz?"
        + urlencode({"transfer": context["transferId"]}),
        "businessUrl": app_origin
        + "/biz?"
        + urlencode({"transfer": context["transferId"]}),
        "assetOrigin": _origin(
            os.getenv("CUADRAO_EMAIL_ASSET_ORIGIN") or "https://cuadrao.ai"
        ),
        # The shared layout adds a postal line only beside an unsubscribe link.
        "postalAddress": "Cuadrao LLC",
    }
    if any(
        not value.strip() or "\r" in value or "\n" in value for value in data.values()
    ):
        raise ValueError("Transfer email fields must be nonempty and single-line")
    replacements = {token: data[key] for key, token in artifact["tokens"].items()}
    pattern = re.compile("|".join(re.escape(token) for token in replacements))
    return {
        field: pattern.sub(
            lambda match, field=field: (
                html.escape(replacements[match[0]], quote=True)
                if field == "html"
                else replacements[match[0]]
            ),
            template,
        )
        for field, template in artifact["templates"][variant].items()
    }


def enqueue_transfer_mail(db: Connection, transfer_id: str, status: str) -> None:
    variants = {
        "pending": (("requested", "target_id"),),
        "declined": (("declined", "owner_id"),),
        "accepted": (("acceptedOwner", "owner_id"), ("acceptedTarget", "target_id")),
        "cancelled": (("withdrawn", "target_id"),),
    }
    row = db.execute(
        "select t.owner_id::text,t.target_id::text,t.space_id::text,s.name,"
        " coalesce(nullif(btrim(p.display_name),''),p.username,'Member'),"
        " coalesce(nullif(btrim(q.display_name),''),q.username,'Member'),"
        " coalesce(t.resolved_at,t.created_at),t.expires_at"
        " from public.business_ownership_transfers t join public.spaces s on s.id=t.space_id"
        " left join public.profiles p on p.id=t.owner_id"
        " left join public.profiles q on q.id=t.target_id where t.id=%s",
        (transfer_id,),
    ).fetchone()
    context = dict(
        businessName=row[3],
        ownerName=row[4],
        targetName=row[5],
        occurredAt=row[6].isoformat(),
        expiresAt=row[7].isoformat(),
        transferId=transfer_id,
        spaceId=row[2],
    )
    people = {"owner_id": row[0], "target_id": row[1]}
    for variant, role in variants.get(status, ()):
        db.execute(
            "insert into public.business_transfer_mail_outbox"
            " (transfer_id,variant,recipient_id,owner_id,target_id,recipient_email,context)"
            " select %s,%s,u.id,%s,%s,u.email,%s from auth.users u where u.id=%s"
            " and u.email is not null and u.email_confirmed_at is not null"
            " and coalesce(u.is_anonymous,false)=false on conflict do nothing",
            (transfer_id, variant, row[0], row[1], Jsonb(context), people[role]),
        )


def deliver_transfer_mail(pool: ConnectionPool, transfer_id: str) -> int:
    """Replays use the same frozen content and provider key within its 24h TTL.

    The reservation commits before SMTP. A crash after provider acceptance cannot
    reset that clock. Ambiguity after 23h requires reconciliation, never a resend.
    """
    if not (os.getenv(resend_email.SMTP_PASSWORD_ENV) or "").strip():
        return 0
    with pool.connection() as db:
        ids = db.execute(
            "select id::text from public.business_transfer_mail_outbox where transfer_id=%s"
            " and sent_at is null and suppressed_at is null and uncertain_at is null order by created_at,id",
            (transfer_id,),
        ).fetchall()
    sent = 0
    for (mail_id,) in ids:
        with pool.connection() as db, db.transaction():
            row = db.execute(
                "select o.variant,o.context,o.first_attempt_at,o.sent_at,o.suppressed_at,o.uncertain_at,"
                " u.email=o.recipient_email and coalesce(u.is_anonymous,false)=false"
                " and (u.banned_until is null or u.banned_until<=clock_timestamp())"
                " and not exists(select 1 from argus_private.account_deletion_runs d where d.user_id=u.id),"
                " t.status,t.expires_at,clock_timestamp()"
                " from public.business_transfer_mail_outbox o"
                " join public.business_ownership_transfers t on t.id=o.transfer_id"
                " left join auth.users u on u.id=o.recipient_id where o.id=%s for update of o",
                (mail_id,),
            ).fetchone()
            if not row or any(value is not None for value in row[3:6]):
                continue
            if not row[6] or (
                row[0] == "requested" and (row[7] != "pending" or row[8] <= row[9])
            ):
                db.execute(
                    "update public.business_transfer_mail_outbox set suppressed_at=clock_timestamp() where id=%s",
                    (mail_id,),
                )
                continue
            if row[2] is None:
                try:
                    payload = render_transfer_mail(row[0], row[1])
                except ValueError:
                    continue
                db.execute(
                    "update public.business_transfer_mail_outbox set first_attempt_at=clock_timestamp(),payload=%s where id=%s",
                    (Jsonb(payload), mail_id),
                )
        with pool.connection() as db, db.transaction():
            row = db.execute(
                "select o.recipient_email,o.payload,o.sent_at,o.suppressed_at,o.uncertain_at,o.first_attempt_at,clock_timestamp(),"
                " (o.variant<>'requested' or (t.status='pending' and t.expires_at>clock_timestamp())),"
                " exists(select 1 from auth.users u where u.id=o.recipient_id and u.email=o.recipient_email"
                " and coalesce(u.is_anonymous,false)=false and (u.banned_until is null or u.banned_until<=clock_timestamp())"
                " and not exists(select 1 from argus_private.account_deletion_runs d where d.user_id=u.id))"
                " from public.business_transfer_mail_outbox o join public.business_ownership_transfers t on t.id=o.transfer_id"
                " where o.id=%s for update of o",
                (mail_id,),
            ).fetchone()
            if not row or any(value is not None for value in row[2:5]):
                continue
            if not row[7] or not row[8]:
                db.execute(
                    "update public.business_transfer_mail_outbox set suppressed_at=clock_timestamp() where id=%s",
                    (mail_id,),
                )
                continue
            if row[6] >= row[5] + _RETRY_WINDOW:
                db.execute(
                    "update public.business_transfer_mail_outbox set uncertain_at=clock_timestamp() where id=%s",
                    (mail_id,),
                )
                continue
            try:
                receipt = resend_email.send_resend_email(
                    recipient=row[0],
                    subject=row[1]["subject"],
                    plain_text=row[1]["text"],
                    html=row[1]["html"],
                    idempotency_key=f"business-transfer/{mail_id}",
                )
            except (OSError, RuntimeError):
                continue
            db.execute(
                "update public.business_transfer_mail_outbox set sent_at=clock_timestamp(),provider_receipt=%s where id=%s",
                (receipt[:256], mail_id),
            )
            sent += 1
    return sent
