"""Row and Storage object counts for one owner, Personal and Business apart. Counts and ids only, never content."""

from __future__ import annotations

import hashlib
import json
import sys

from rig import db

SPLIT = {
    "financial_accounts": "select count(*) from public.financial_accounts where user_id=%s and {s}",
    "financial_source_connections": "select count(*) from public.financial_source_connections where user_id=%s and {s}",
    "financial_import_events": "select count(*) from public.financial_import_events where user_id=%s and {s}",
    "conversations": "select count(*) from public.conversations where user_id=%s and {s}",
}
SCOPES = {"personal": "owner_space_id is null", "business": "owner_space_id is not null"}
FLAT = {
    "auth_users": "select count(*) from auth.users where id=%s",
    "spaces": "select count(*) from public.spaces where created_by=%s",
    "financial_records": "select count(*) from public.financial_records where user_id=%s",
    "financial_document_extractions": "select count(*) from public.financial_document_extractions where user_id=%s",
    "financial_import_observations": "select count(*) from public.financial_import_observations where user_id=%s",
    "whatsapp_link_codes": "select count(*) from public.whatsapp_link_codes where destination_owner_id=%s",
    "whatsapp_sender_links": "select count(*) from public.whatsapp_sender_links where destination_owner_id=%s",
    "whatsapp_inbound_messages_to_owner": "select count(*) from public.whatsapp_inbound_messages where destination_owner_id=%s",
    "storage_objects": "select count(*) from storage.objects where bucket_id='financial-document-sources' and starts_with(name, %s::text || '/')",
}


def counts(owner: str, sender_hashes: list[str] | None = None) -> dict:
    with db() as c:
        out = {name: c.execute(sql, (owner,)).fetchone()[0] for name, sql in FLAT.items()}
        for name, sql in SPLIT.items():
            for scope, where in SCOPES.items():
                out[f"{name}.{scope}"] = c.execute(sql.format(s=where), (owner,)).fetchone()[0]
        hashes = sender_hashes if sender_hashes is not None else link_hashes(owner)
        out["whatsapp_inbound_messages_from_owner_links"] = c.execute(
            "select count(*) from public.whatsapp_inbound_messages where sender_hash = any(%s)", (hashes,)
        ).fetchone()[0]
    return out


def link_hashes(owner: str) -> list[bytes]:
    with db() as c:
        return [r[0] for r in c.execute(
            "select wa_id_hash from public.whatsapp_sender_links where destination_owner_id=%s", (owner,)).fetchall()]


def business_links(owner: str) -> dict:
    """Each Business import event: its receipt, state and the expense it became."""
    with db() as c:
        rows = c.execute(
            """select o.connection_id::text, e.state, e.activity_id::text, d.draft->>'status'
                 from public.financial_import_events e
                 join public.financial_import_observations o on o.event_id = e.id
                 left join public.financial_document_extractions d on d.connection_id = o.connection_id
                where e.user_id=%s and e.owner_space_id is not null order by 1""", (owner,)).fetchall()
        receipts = c.execute(
            """select c.id::text, c.status, d.draft->>'status', d.source_sha256
                 from public.financial_source_connections c
                 left join public.financial_document_extractions d on d.connection_id = c.id
                where c.user_id=%s and c.owner_space_id is not null order by 1""", (owner,)).fetchall()
    return {"events": [list(r) for r in rows], "receipts": [list(r) for r in receipts]}


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]


if __name__ == "__main__":
    print(json.dumps(counts(sys.argv[1]), indent=1))
