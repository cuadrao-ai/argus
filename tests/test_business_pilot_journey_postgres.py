"""Synthetic Business document journey through local Postgres and the real stores."""

from __future__ import annotations

import asyncio
import io
import json
from dataclasses import replace
from datetime import date
from email.message import EmailMessage
from hashlib import sha256
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from uuid import UUID, uuid4
from zipfile import ZipFile

import pytest
from argus.api.business_drafts import upload_recorder
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import ApproveExpense, ReviewDraft
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.export import ExportPeriod, export_package
from argus.domain.ingestion.documents.objects import SOURCE_BUCKET, verify_content
from argus.domain.owner_scope import BusinessSpace
from fastapi import Request
from PIL import Image

from tests import test_business_email_authorization_postgres as auth_shared
from tests import test_business_email_intake_postgres as intake_shared
from tests.business.receipt_stub import DETAILS, PURCHASE, ReceiptStub
from tests.test_business_duplicate_resolution_postgres import request_for
from tests.test_business_spaces_migration_postgres import space

actions = auth_shared.actions
users = auth_shared.users
receipts = intake_shared.receipts
email_reader_boundary = auth_shared.email_reader_boundary
pytestmark = [auth_shared.pytestmark, pytest.mark.owner_acts]


class FileSourceObjects:
    bucket = SOURCE_BUCKET

    def __init__(self, root: Path) -> None:
        self.root = root

    def _file(self, path: str) -> Path:
        parts = PurePosixPath(path)
        if parts.is_absolute() or ".." in parts.parts:
            raise ValueError("invalid source path")
        return self.root.joinpath(*parts.parts)

    def put(self, path: str, content: bytes, media_type: str) -> None:
        if path.startswith("sealed/"):
            verify_content(content, path.rsplit("/", 1)[-1])
        target = self._file(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            assert target.read_bytes() == content
        else:
            target.write_bytes(content)

    def get(self, path: str) -> bytes | None:
        target = self._file(path)
        content = target.read_bytes() if target.exists() else None
        return verify_content(content, path.rsplit("/", 1)[-1]) if path.startswith("sealed/") else content

    def delete(self, prefix: str) -> None:
        if not prefix.endswith("/"):
            raise ValueError("invalid source prefix")
        prefixes = (prefix,)
        if prefix.count("/") == 1:
            prefixes += (f"sealed/{prefix}", f"rebuilt/{prefix}")
        for file in self.root.rglob("*"):
            if file.is_file() and file.relative_to(self.root).as_posix().startswith(prefixes):
                file.unlink()

    def remove(self, path: str) -> None:
        self._file(path).unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def local_file_objects(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FileSourceObjects:
    objects = FileSourceObjects(tmp_path / "source-objects")
    monkeypatch.setattr(intake_shared, "source_objects", lambda: objects)
    return objects


def _paper(color: str) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (48, 48), color).save(output, format="PDF")
    return output.getvalue()


def _read_as(stub: ReceiptStub, *, amount: str, currency: str, merchant: str) -> None:
    stub.rows = [
        {
            **PURCHASE,
            "amount": amount,
            "currency": currency,
            "merchant": merchant,
        }
    ]
    stub.details = {
        **DETAILS,
        "total": amount,
        "currency": currency,
        "merchant": merchant,
        "items": [],
        "subtotal": None,
        "tax": None,
    }


def _upload(world: dict, content: bytes) -> str:
    request = Request(
        {"type": "http", "headers": [(b"idempotency-key", uuid4().hex.encode())]}
    )
    context = SimpleNamespace(
        service=SimpleNamespace(imports=world["documents"].hub.sink)
    )
    saved = asyncio.run(
        world["documents"].upload(
            user_id=world["owner"],
            scope=BusinessSpace(world["space"]),
            content=content,
            filename="comprobante.pdf",
            media_type="application/pdf",
            on_capture=upload_recorder(context, request),
        )
    )
    return saved.connection_id


def _email(world: dict, content: bytes) -> str:
    message = EmailMessage()
    message["From"] = world["provider"].sender
    message["Subject"] = "Comprobante sintético"
    message.set_content("Adjunto comprobante.")
    message.add_attachment(
        content, maintype="application", subtype="pdf", filename="comprobante.pdf"
    )
    world["provider"].raw = message.as_bytes()
    delivery = auth_shared._deliver_for_reader(
        world, {"dmarc": "pass", "dkim": "pass"}
    )
    assert delivery.state == "captured"
    [part] = world["store"].parts(delivery.id)
    return part.document_id


def _approve(world: dict, draft_id, amount: str) -> None:
    service, context = world["service"], world["context"]
    reviewed = service.review(
        context,
        draft_id,
        ReviewDraft(
            version=service.dossier(context, draft_id).version,
            facts={
                "amount": {"state": "known", "value": amount},
                "funding": {"state": "known", "value": {"kind": "owner_funds"}},
                "business_share": {"state": "known", "value": {"kind": "all"}},
            },
        ),
        str(uuid4()),
    )
    assert reviewed.outcome == "applied", reviewed
    approved = service.approve(
        context,
        draft_id,
        ApproveExpense(version=reviewed.version, action="record_expense"),
        str(uuid4()),
    )
    assert approved.outcome == "applied", approved


def test_upload_and_approved_mail_keep_three_originals_and_two_currencies(
    email_reader_boundary,
    local_file_objects: FileSourceObjects,
    request: pytest.FixtureRequest,
) -> None:
    world = email_reader_boundary
    stub = ReceiptStub()
    world["documents"].extractor = stub
    world["runtime"].documents.extractor = stub
    world["store"].upsert_sender(
        world["space"], "address", world["provider"].sender, "authorized"
    )
    first_bytes, repeat_bytes, mail_bytes = (
        _paper("white"),
        _paper("gray"),
        _paper("blue"),
    )

    _read_as(stub, amount="3450.00", currency="DOP", merchant="Tienda Sintética")
    first_connection = _upload(world, first_bytes)
    first, first_origin = intake_shared.prepare(world, first_connection)
    repeat_connection = _upload(world, repeat_bytes)
    repeat, repeat_origin = intake_shared.prepare(world, repeat_connection)
    assert (first_origin, repeat_origin) == ("direct", "direct")
    service, context = world["service"], world["context"]
    assert "possible_duplicate" in {b.code for b in service.dossier(context, repeat).blockers}
    decided = service.resolve_duplicate(
        context, repeat, request_for(service, context, repeat, first), str(uuid4())
    )
    assert decided.outcome == "applied", decided
    assert "possible_duplicate" not in {b.code for b in service.dossier(context, repeat).blockers}

    _read_as(stub, amount="12.40", currency="USD", merchant="Tienda Azul")
    mail_connection = _email(world, mail_bytes)
    with world["pool"].connection() as db:
        linked = db.execute(
            "select distinct l.draft_id from public.business_draft_sources l"
            " join public.business_sources s on s.id=l.source_id and s.space_id=l.space_id"
            " where s.connection_id=%s and s.origin='email'",
            (mail_connection,),
        ).fetchall()
    assert len(linked) == 1
    mailed = linked[0][0]
    assert service.dossier(context, mailed).facts.currency.value == "USD"
    with world["pool"].connection() as db:
        assert db.execute(
            "select count(*) from public.financial_activity_groups where user_id=%s",
            (world["owner"],),
        ).fetchone() == (0,)

    _approve(world, first, "3500.00")
    _approve(world, repeat, "3450.00")
    _approve(world, mailed, "12.40")
    archive = export_package(
        service.authority,
        context,
        ExportPeriod(date(2026, 10, 1), date(2026, 10, 31)),
        FileSourceObjects(local_file_objects.root),
    )
    with ZipFile(io.BytesIO(archive)) as zipfile:
        manifest = json.loads(zipfile.read("manifest.json"))
        assert {(row["amount"], row["currency"]) for row in manifest["records"]} == {
            ("3500.00", "DOP"),
            ("3450.00", "DOP"),
            ("12.40", "USD"),
        }
        assert manifest["evidence_complete"] is True
        included = {
            sha256(zipfile.read(source["file"])).hexdigest()
            for source in manifest["sources"]
            if source["availability"] == "included"
        }
    originals = {
        "upload_dop": sha256(first_bytes).hexdigest(),
        "upload_duplicate_dop": sha256(repeat_bytes).hexdigest(),
        "approved_sender_email_usd": sha256(mail_bytes).hexdigest(),
    }
    assert set(originals.values()) <= included
    request.node.user_properties.extend(
        (
            ("original_sha256", json.dumps(originals, sort_keys=True)),
            ("export_currencies", "DOP,USD"),
            (
                "transport_boundaries",
                "upload=local_service;email=signed_local_webhook_and_fake_provider;"
                "extraction=stub;authority=postgres;originals=local_files;"
                "export=real_local_package",
            ),
        )
    )


@pytest.mark.parametrize("change", ["wrong_business", "read_only", "revoked", "closed"])
def test_receipt_cannot_prepare_after_business_authority_changes(
    receipts: dict, users: dict, change: str
) -> None:
    world = receipts
    connection_id = _upload(world, _paper("green"))
    service, context = world["service"], world["context"]
    with world["pool"].connection() as db:
        if change == "wrong_business":
            other_space = space(db, users["other"])
            context = replace(
                context,
                actor=TrustedActor(
                    actor_id=context.actor.actor_id,
                    actor_kind="member",
                    space_id=other_space,
                ),
            )
        elif change == "read_only":
            db.execute(
                "update public.business_client_grants set capabilities=array['read'] where id=%s",
                (context.grant_id,),
            )
        elif change == "revoked":
            db.execute(
                "update public.business_client_grants set revoked_at=now() where id=%s",
                (context.grant_id,),
            )
        else:
            db.execute(
                "update public.spaces set closed_at=now() where id=%s",
                (world["space"],),
            )
    with pytest.raises(ActionError):
        service.capture_attachment_preparation(context, UUID(connection_id), target=None)
    with world["pool"].connection() as db:
        assert db.execute(
            "select count(*) from public.business_draft_revisions where space_id=%s",
            (world["space"],),
        ).fetchone() == (0,)
