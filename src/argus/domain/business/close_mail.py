"""Close notifications committed with the Business command, never live in tests."""

from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from babel.dates import format_date
from psycopg.types.json import Jsonb

from argus.domain import resend_email
from argus.domain.business.transfer_mail import _origin

_ARTIFACT = Path(__file__).with_name("business_closed_email.generated.json")
_RETRY_WINDOW = timedelta(hours=23)


def render_close_mail(context: dict[str, str]) -> dict[str, str]:
    artifact = json.loads(_ARTIFACT.read_text())
    if artifact["schemaVersion"] != 1:
        raise ValueError("Unsupported close mail artifact")
    address = (os.getenv("MARKETING_POSTAL_ADDRESS") or "").strip()
    if (
        not address
        or re.fullmatch(r"Cuadrao LLC[,\s]*", address, flags=re.I)
        or "\n" in address
        or "\r" in address
    ):
        raise ValueError("Email postal address configuration is required")
    local = ZoneInfo("America/Santo_Domingo")
    closed = datetime.fromisoformat(context["closedAt"]).astimezone(local)
    values = {
        "businessName": context["businessName"],
        "ownerName": context["ownerName"],
        "closedDate": format_date(closed, "long", locale="es_DO"),
        "purgeDate": format_date(
            datetime.fromisoformat(context["purgeAt"]).astimezone(local),
            "long",
            locale="es_DO",
        ),
        "postalAddress": address
        if re.match(r"Cuadrao LLC(?:,|$)", address)
        else f"Cuadrao LLC, {address}",
        "assetOrigin": _origin(
            os.getenv("CUADRAO_EMAIL_ASSET_ORIGIN") or "https://cuadrao.ai"
        ),
    }
    if any(
        not value.strip() or "\n" in value or "\r" in value for value in values.values()
    ):
        raise ValueError("Close mail fields must be nonempty single-line values")
    replacements = {token: values[key] for key, token in artifact["tokens"].items()}
    pattern = re.compile("|".join(re.escape(token) for token in replacements))
    return {
        field: pattern.sub(
            lambda match, field=field: html.escape(replacements[match[0]], quote=True)
            if field == "html"
            else replacements[match[0]],
            artifact[field],
        )
        for field in ("subject", "html", "text")
    }


def enqueue_close_mail(
    db, space_id: str, owner_id: str, name: str, closed_at: datetime
) -> None:
    owner = db.execute(
        "select coalesce(nullif(btrim(display_name),''),username,'Member') from public.profiles where id=%s",
        (owner_id,),
    ).fetchone()
    context = {
        "businessName": name,
        "ownerName": owner[0] if owner else "Member",
        "closedAt": closed_at.isoformat(),
        "purgeAt": (closed_at + timedelta(days=30)).isoformat(),
    }
    db.execute(
        "insert into public.business_close_mail_outbox(space_id,closed_at,owner_id,recipient_id,recipient_email,context)"
        " select distinct g.space_id,%s,%s::uuid,u.id,u.email,%s from public.business_client_grants g join auth.users u on u.id=g.grantee_id"
        " where g.space_id=%s and g.grantee_id<>%s and g.revoked_at is null and (g.expires_at is null or g.expires_at>clock_timestamp())"
        " and 'read'=any(g.capabilities) and u.email is not null and u.email_confirmed_at is not null"
        " and coalesce(u.is_anonymous,false)=false and (u.banned_until is null or u.banned_until<=clock_timestamp())"
        " and not exists(select 1 from argus_private.account_deletion_runs d where d.user_id=u.id) on conflict do nothing",
        (closed_at, owner_id, Jsonb(context), space_id, owner_id),
    )


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
                " s.closed_at=o.closed_at and exists(select 1 from auth.users u where u.id=o.recipient_id and u.email=o.recipient_email"
                " and u.email_confirmed_at is not null and coalesce(u.is_anonymous,false)=false"
                " and (u.banned_until is null or u.banned_until<=clock_timestamp())"
                " and not exists(select 1 from argus_private.account_deletion_runs d where d.user_id=u.id))"
                " from public.business_close_mail_outbox o join public.spaces s on s.id=o.space_id where o.id=%s for update of o",
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
            if row[1] is None:
                try:
                    payload = render_close_mail(row[0])
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
                " s.closed_at=o.closed_at and exists(select 1 from auth.users u where u.id=o.recipient_id and u.email=o.recipient_email"
                " and u.email_confirmed_at is not null and coalesce(u.is_anonymous,false)=false and (u.banned_until is null or u.banned_until<=clock_timestamp())"
                " and not exists(select 1 from argus_private.account_deletion_runs d where d.user_id=u.id))"
                " from public.business_close_mail_outbox o join public.spaces s on s.id=o.space_id where o.id=%s for update of o",
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
