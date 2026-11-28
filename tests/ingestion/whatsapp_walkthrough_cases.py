"""The signed founder walkthrough. Opt in with the disposable DB and local Storage."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from hashlib import sha256
from io import StringIO
from pathlib import Path
from typing import Any

import httpx
import pytest
from argus.api import whatsapp
from argus.domain.business.access import PostgresAccessStore
from argus.domain.ingestion.documents.service import (
    DocumentOutcome,
    DocumentServiceError,
)
from argus.domain.ingestion.email_intake.budget import next_business_day
from argus.domain.ingestion.whatsapp import document_step, reply_groups_postgres
from argus.domain.ingestion.whatsapp.intake import MediaSource
from argus.domain.ingestion.whatsapp.media import FetchedMedia
from argus.domain.ingestion.whatsapp.reply_groups import (
    BatchOutcomes,
    ReplyAttempt,
    ReplyGroup,
)
from argus.domain.ingestion.whatsapp.reply_groups_postgres import PostgresReplyGroups
from loguru import logger
from psycopg import Connection

from scripts.qa.whatsapp_walkthrough import (
    Receipt,
)
from tests.ingestion import whatsapp_walkthrough_support as support
from tests.ingestion.whatsapp_support import encode, fixture, sign
from tests.ingestion.whatsapp_walkthrough_support import (
    BUSINESS_NAMES,
    LINK,
    ScheduledSweeps,
    SignedForward,
)
from workflows.read_resume import ReadResume

desk = support.desk
read_limit = support.read_limit
reads_finish_inside_the_request = support.reads_finish_inside_the_request
reply_language = support.reply_language
scheduler = support.scheduler
signed = support.signed
sweep_interval = support.sweep_interval


@pytest.mark.asyncio
async def test_signed_founder_walkthrough(
    signed: SignedForward,
    caplog: pytest.LogCaptureFixture,
    record_property,
) -> None:
    w, desk = signed, signed.desk
    captured = StringIO()
    sink = logger.add(captured, format="{message} {extra}")
    try:
        with caplog.at_level(logging.INFO):
            await run_cases(w)
    finally:
        logger.remove(sink)
    assert (
        w.link_reply
        == "Listo, este WhatsApp quedó conectado. Envía aquí la foto o el PDF de tus facturas."
    )
    public = "\n".join([*w.responses, *w.replies, captured.getvalue(), caplog.text])
    for private in (desk.private_business_name, desk.spaces["C"]):
        assert (
            private not in public
        ), "An inaccessible Business appeared in a response or log"
    w.proof.append(
        "Privacy | inaccessible Business name and ID absent from HTTP, replies and logs"
    )
    for line in w.proof:
        record_property("walkthrough", line)


async def run_cases(w: SignedForward) -> None:
    d, r = w.desk, w.desk.rnc
    sales = [Receipt(f"Venta-{n}", r["A"], None) for n in (1, 2)]
    purchases = [Receipt(f"Compra-{n}", r["vendor"], r["B"]) for n in (1, 2)]
    unplaced = [
        Receipt("Sin-comprador", r["vendor"], None),
        Receipt("Compra-3", r["vendor"], r["C"]),
        Receipt("Compra-4", r["vendor"], r["X"]),
    ]
    connections = await w.forward(*sales)
    d.clock.now += timedelta(seconds=10)
    connections.extend(await w.forward(*purchases))
    d.clock.now += timedelta(seconds=10)
    connections.extend(await w.forward(*unplaced))
    assert w.read_ids == [f"wamid.W9.{100000000000000+n}" for n in range(7)]
    assert w.replies == []
    for cid in connections:
        assert await w.read(cid) == "prepared"
    await w.sweep()
    assert w.replies == [
        "Recibimos 7 facturas, gracias.\nYa están en la Bandeja:\n"
        "• Colmado Doña Rosa: 2\n• Taller Hermanos Peña: 2\n"
        "3 quedaron sin negocio. Te esperan en Cuadrao."
    ]
    w.proof.append("1 | 3 signed deliveries | 7 read receipts after save | one reply after 1 quiet minute")
    w.proof.append(w.replies[0])
    assert w.reads == Counter(receipt.name for receipt in [*sales, *purchases, *unplaced])
    for key, expected, kind in (("A", sales, "venta"), ("B", purchases, "recibo")):
        rows = await w.inbox(key)
        assert {k: row["document_type"] for k, row in rows.items()} == {
            receipt.name + ".png": kind for receipt in expected
        }
    by_file = {
        d.service.store.draft(
            user_id=d.ana, connection_id=item.connection_id
        ).filename: item
        for item in w.held()
    }
    assert {name: row.reason for name, row in by_file.items()} == {
        "Sin-comprador.png": "no_buyer_rnc",
        "Compra-3.png": "no_match",
        "Compra-4.png": "no_match",
    }
    assert (await w.request("GET", LINK, headers=d.auth))["held_count"] == 3
    w.evidence(
        "1 | A=2 ventas, B=2 compras | held=no_buyer_rnc,no_match,no_match", (7, 2, 2, 3)
    )

    before = w.row_counts()
    sale = sales[0]
    original = (await w.inbox("A"))[sale.name + ".png"]["id"]
    [duplicate] = await w.forward(sale)
    assert duplicate == original, "Resending the file should refer to A's existing sale"
    assert len(w.read_ids) == 7 and len(w.replies) == 1
    await w.sweep()
    assert w.replies[1:] == ["Esta ya la teníamos, gracias. No se guardó dos veces."]
    assert await w.read(duplicate) is None
    assert w.row_counts() == before
    w.evidence(
        "6 | duplicate acknowledged once, without a link | new drafts=0 new held rows=0",
        (7, 2, 2, 3),
    )

    def assign(name: str, key: str) -> DocumentOutcome:
        return d.service.adopt(
            user_id=d.ana, held_id=by_file[name].id, business_id=d.spaces[key]
        )

    assigned = assign("Sin-comprador.png", "A")
    assert (await w.inbox("A"))["Sin-comprador.png"]["id"] == assigned.connection_id
    assert await w.read(assigned.connection_id) is None
    assert len(w.held()) == 2
    w.evidence("2 | assigned to A with room | channel=whatsapp", (7, 3, 2, 2))
    assigned = assign("Compra-3.png", "A")
    assert (await w.inbox("A"))["Compra-3.png"]["id"] == assigned.connection_id
    assert await w.read(assigned.connection_id) is None
    assert len(w.held()) == 1
    w.evidence("2 | assigned at A's cap | channel=whatsapp", (7, 3, 2, 2))

    PostgresAccessStore(d.pool).revoke_grant(d.spaces["B"], d.users["B"], d.grants["B"])
    with pytest.raises(DocumentServiceError, match="business_permission_denied"):
        assign("Compra-4.png", "B")
    status = await w.request("GET", LINK, headers=d.auth)
    assert [row["space_id"] for row in status["receiving_businesses"]] == [d.spaces["A"]]
    assert status["held_count"] == 1
    w.evidence(
        "3 | revoked B absent from picker | assignment=business_permission_denied",
        (7, 3, 2, 2),
    )

    single = Receipt("Directo", r["vendor"], None)
    before = w.row_counts()
    [direct] = await w.forward(single)
    assert w.row_counts() == (before[0] + 1, before[1])
    assert await w.read(direct) == "business_read_budget_day"
    row = (await w.inbox("A"))["Directo.png"]
    assert (row["id"], row["attention"]) == (direct, "read_budget_day")
    resume = ReadResume(d.service)
    assert await asyncio.to_thread(resume.run, d.clock()) == {"due": 0, "requeued": 0}
    w.evidence(
        "4 | one eligible, no buyer | new held rows=0 | Bandeja=read_budget_day",
        (7, 3, 2, 2),
    )
    d.clock.now = next_business_day(d.clock()) + timedelta(seconds=1)
    assert await asyncio.to_thread(resume.run, d.clock()) == {"due": 1, "requeued": 1}
    assert await w.read(direct) == "prepared"
    assert (await w.inbox("A"))["Directo.png"]["status"] == "review_ready"
    w.evidence("4 | next Santo Domingo day | resumed=1", (8, 1, 0, 0))

    with d.pool.connection() as db:
        triggers = db.execute(
            "select tgname from pg_trigger t join pg_proc p on p.oid=t.tgfoid"
            " where not tgisinternal and (tgname=any(%s) or p.proname=any(%s))",
            (
                ["fill_sender_link_space", "whatsapp_capture_same_space"],
                ["fill_sender_link_space", "require_whatsapp_capture_same_space"],
            ),
        ).fetchall()
    assert not triggers, triggers
    search = subprocess.run(
        [
            "git",
            "grep",
            "-n",
            r"resolve_business_scope\|business_space_of",
            "--",
            "src/argus/api/whatsapp.py",
            "src/argus/domain/ingestion/whatsapp",
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        check=False,
    )
    assert search.returncode == 1, search.stdout.decode() or search.stderr.decode()
    w.proof.append("7 | default lookup matches=0 | Business-pin triggers=0")


@pytest.mark.asyncio
@pytest.mark.parametrize("read_limit", [10])
async def test_mixed_ten_share_one_reply(signed: SignedForward) -> None:
    w, r = signed, signed.desk.rnc
    sales = [Receipt(f"Venta-{n}", r["A"], None) for n in range(4)]
    purchases = [Receipt(f"Compra-{n}", r["vendor"], r["B"]) for n in range(2)]
    saved = await w.forward(*sales, *purchases, Receipt("Sin-RNC", r["vendor"], None))
    for cid in saved:
        assert await w.read(cid) == "prepared"
    await w.forward(sales[0])
    for n in range(2):
        await w.post(
            fixture(
                "image_message.json",
                id=f"wamid.INVALID{n}",
                image={"id": f"99900000000000{n}", "mime_type": "image/gif"},
            )
        )
    assert len(w.read_ids) == 7
    assert w.replies == []
    await w.sweep()
    assert w.replies == [
        "Recibimos 10 facturas, gracias.\nYa están en la Bandeja:\n"
        "• Colmado Doña Rosa: 4\n• Taller Hermanos Peña: 2\n"
        "1 quedó sin negocio. Te espera en Cuadrao.\n1 ya la teníamos.\n"
        "Disculpa, no pudimos recibir 2 archivos:\n• foto enviada a las 5:20 p. m.\n"
        "• foto enviada a las 5:20 p. m.\nEnvíalos como foto o PDF."
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("desk", [tuple(BUSINESS_NAMES)], indirect=True)
@pytest.mark.parametrize("read_limit", [40])
async def test_forty_files_in_nine_businesses_name_five(signed: SignedForward) -> None:
    w, r = signed, signed.desk.rnc
    receipts = [
        Receipt(f"Venta-{key}-{n}", r[key], None)
        for key, count in zip(BUSINESS_NAMES, (8, 6, 5, 5, 4, 3, 3, 2, 2), strict=True)
        for n in range(count)
    ]
    receipts.extend(Receipt(f"Sin-{n}", r["vendor"], None) for n in range(2))
    for cid in await w.forward(*receipts):
        assert await w.read(cid) == "prepared"
    assert len(w.read_ids) == 40
    assert w.replies == []
    await w.sweep()
    assert w.replies == [
        "Recibimos 40 facturas, gracias.\nYa están en la Bandeja:\n"
        "• Colmado Doña Rosa: 8\n• Taller Hermanos Peña: 6\n• Farmacia San Miguel: 5\n"
        "• Ferretería El Progreso: 5\n• Cafetería La Esquina: 4\n"
        "y 4 negocios más: 10 facturas\n2 quedaron sin negocio. Te esperan en Cuadrao."
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("read_limit", [12])
async def test_slow_reads_close_at_three_minutes_without_followup(
    signed: SignedForward,
) -> None:
    w, r = signed, signed.desk.rnc
    receipts = [
        Receipt(f"Venta-{key}-{n}", r[key], None)
        for key, count in (("A", 6), ("B", 4))
        for n in range(count)
    ]
    receipts.extend(Receipt(f"Pendiente-{n}", r["A"], None) for n in range(2))
    connections = await w.forward(*receipts)
    for cid in connections[:-2]:
        assert await w.read(cid) == "prepared"
    for _ in range(2):
        await w.sweep()
        assert w.replies == []
    await w.sweep()
    expected = [
        "Recibimos 12 facturas, gracias.\nYa están en la Bandeja:\n"
        "• Colmado Doña Rosa: 6\n• Taller Hermanos Peña: 4\n"
        "Las demás se están leyendo. Puedes seguirlas en Cuadrao."
    ]
    assert w.replies == expected
    for cid in connections[-2:]:
        assert await w.read(cid) == "prepared"
    await w.sweep()
    assert w.replies == expected


async def interrupt_download(
    fetcher: MediaSource,
    deliver: Callable[[], Awaitable[httpx.Response]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def interrupted(media_id: str) -> FetchedMedia:
        raise asyncio.CancelledError

    with monkeypatch.context() as patch:
        patch.setattr(fetcher, "fetch", interrupted)
        try:
            response = await deliver()
        except asyncio.CancelledError:
            return
        assert response.status_code >= 500


@pytest.mark.asyncio
@pytest.mark.parametrize("redeliver", [False, True])
async def test_failed_capture_commit_sends_no_status_or_reply(
    signed: SignedForward,
    scheduler: ScheduledSweeps,
    monkeypatch: pytest.MonkeyPatch,
    redeliver: bool,
) -> None:
    w = signed
    intake = whatsapp.whatsapp_runtime().intake
    prepare = intake.destination.prepare
    media_id, message_id = "100000000000000", "wamid.ROLLBACK"
    key = intake.keys.message(message_id)
    w.media[media_id] = Receipt("Sin-commit", w.desk.rnc["A"], None).png()
    body = fixture(
        "image_message.json",
        id=message_id,
        image={"id": media_id, "mime_type": "image/png"},
    )
    raw = encode(body, w.desk.clock.now)
    leases = []

    async def deliver() -> httpx.Response:
        return await w.client.post(
            whatsapp.WEBHOOK_PATH, content=raw, headers={"X-Hub-Signature-256": sign(raw)}
        )

    if redeliver:
        await interrupt_download(intake.media, deliver, monkeypatch)
        await scheduler.advance(175)
        assert intake.store.inbound(key).claim_until < w.desk.clock.now
        assert w.read_ids == w.replies == []

    def fail_at_commit(connection, *args, **kwargs):
        result = prepare(connection, *args, **kwargs)
        connection.execute(
            "create temp table failed_commit (id int primary key, parent int "
            "references failed_commit(id) deferrable initially deferred) on commit drop"
        )
        connection.execute("insert into failed_commit values (1, 2)")
        leases.append(intake.store.inbound(key).claim_until)
        return result

    monkeypatch.setattr(intake.destination, "prepare", fail_at_commit)
    errors = []
    sink = logger.add(
        lambda message: errors.append(message.record["extra"].get("failure_mode"))
    )
    try:
        response = await deliver()
    finally:
        logger.remove(sink)
    assert response.status_code == 503 and "ForeignKeyViolation" in errors
    [lease] = leases
    if redeliver:
        assert lease > scheduler.start + timedelta(seconds=180)
    await scheduler.advance(180)
    await scheduler.advance(300)
    assert w.read_ids == w.replies == []
    inbound = intake.store.inbound(key)
    assert (inbound.status, inbound.claim_until, inbound.connection_id) == (
        "failed",
        None,
        None,
    )
    assert await w.inbox("A") == await w.inbox("B") == {}
    assert w.held() == []
    assert w.usage() == (0, 0, 0, 0)
    with w.desk.pool.connection() as db:
        assert not db.execute(
            "select 1 from public.whatsapp_reply_days where owner_id=%s", (w.desk.ana,)
        ).fetchone()


@pytest.mark.asyncio
async def test_daily_failure_cap_keeps_saved_file_counts(
    signed: SignedForward,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    w = signed
    monkeypatch.setenv("CUADRAO_WHATSAPP_REPLY_DAILY_LIMIT", "2")

    async def unsupported(n: int) -> None:
        await w.post(
            fixture(
                "image_message.json",
                id=f"wamid.INVALID{n}",
                image={"id": f"99900000000000{n}", "mime_type": "image/gif"},
            )
        )

    await unsupported(1)
    await w.sweep()
    assert w.replies == [
        "Disculpa, no pudimos recibir este archivo.\n• foto enviada a las 5:20 p. m.\n"
        "Envíalo como foto o PDF."
    ]
    await unsupported(2)
    await w.sweep()
    assert w.replies[1:] == [
        "Por hoy no avisaremos más sobre archivos que no podamos recibir. Las facturas válidas siguen entrando."
    ]
    await unsupported(3)
    [cid] = await w.forward(Receipt("Cada-válida", w.desk.rnc["A"], None))
    assert await w.read(cid) == "prepared"
    await w.sweep()
    assert w.replies[2:] == [
        "Recibimos 2 facturas, gracias.\nYa está en la Bandeja:\n• Colmado Doña Rosa: 1"
    ]
    await unsupported(4)
    await w.sweep()
    assert len(w.replies) == 3


@pytest.mark.asyncio
async def test_window_elapsed_before_worker_runs(signed: SignedForward) -> None:
    w = signed
    [cid] = await w.forward(Receipt("Con-ventana", w.desk.rnc["A"], None))
    assert await w.read(cid) == "prepared"
    assert len(w.read_ids) == 1
    await w.sweep(24 * 60 * 60)
    assert w.replies == []


@pytest.mark.asyncio
@pytest.mark.parametrize("delay_seconds", [0.5, 1])
async def test_window_during_final_database_authorization(
    signed: SignedForward, monkeypatch: pytest.MonkeyPatch, delay_seconds: float
) -> None:
    w = signed
    [cid] = await w.forward(Receipt("Último-segundo", w.desk.rnc["A"], None))
    assert await w.read(cid) == "prepared"
    await w.post(
        fixture(
            "document_forwarded.json",
            id="wamid.WINDOW-FAILED",
            document={"id": "999000000000008", "filename": "archivo.gif", "mime_type": "image/gif"},
        )
    )
    checked_at = []
    outcomes = reply_groups_postgres._outcomes

    def read_outcomes(db: Connection, group: ReplyGroup, *, now: datetime) -> BatchOutcomes:
        result = outcomes(db, group, now=now)
        # Claim reads outcomes before inserting the attempt. Authorization reads them
        # again with that committed attempt locked, immediately before dispatch.
        reservation = db.execute(
            "select d.reserved_count from public.whatsapp_reply_attempts a "
            "join public.whatsapp_reply_days d using (sender_hash,day) where a.sender_hash=%s",
            (group.sender_hash,),
        ).fetchone()
        if reservation:
            assert reservation == (1,)
            checked_at.append(w.desk.clock.now - group.last_sent_at)
            w.desk.clock.now += timedelta(seconds=delay_seconds)
        return result

    monkeypatch.setattr(reply_groups_postgres, "_outcomes", read_outcomes)
    await w.sweep(24 * 60 * 60 - 1)
    assert checked_at == [timedelta(hours=24, seconds=-1)]
    await w.sweep()
    sent = delay_seconds < 1
    expected = (
        "Recibimos 2 facturas, gracias.\nYa está en la Bandeja:\n• Colmado Doña Rosa: 1\n"
        "Disculpa, no pudimos recibir este archivo.\n• archivo.gif\nEnvíalo como foto o PDF."
    )
    assert w.replies == ([expected] if sent else [])
    with w.desk.pool.connection() as db:
        assert db.execute(
            "select sent_count,reserved_count from public.whatsapp_reply_days where owner_id=%s",
            (w.desk.ana,),
        ).fetchall() == [(int(sent), 0)]
        assert db.execute(
            "select 1 from public.whatsapp_reply_attempts where owner_id=%s "
            "union all select 1 from public.whatsapp_reply_groups where owner_id=%s",
            (w.desk.ana, w.desk.ana),
        ).fetchall() == []


@pytest.mark.asyncio
async def test_window_drop_releases_daily_guidance(
    signed: SignedForward, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = signed
    await w.post(fixture("audio_message.json"))
    authorize = w.upkeep.store.authorized

    def expire(attempt: ReplyAttempt, *, now: datetime) -> bool:
        assert authorize(attempt, now=now)
        assert now - attempt.group.last_sent_at == timedelta(hours=24, seconds=-1)
        w.desk.clock.now += timedelta(seconds=1)
        return True

    with monkeypatch.context() as patch:
        patch.setattr(w.upkeep.store, "authorized", expire)
        await w.sweep(24 * 60 * 60 - 1)
    assert w.replies == []
    with w.desk.pool.connection() as db:
        assert db.execute(
            "select guidance_reserved from public.whatsapp_reply_days where owner_id=%s",
            (w.desk.ana,),
        ).fetchall() == [(False,)]
    await w.post(fixture("audio_message.json", id="wamid.FRESH-GUIDANCE"))
    await w.sweep()
    assert len(w.replies) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("link_in_envelope", [False, True])
async def test_same_envelope_files_share_arrival_before_second_claim(
    signed: SignedForward, monkeypatch: pytest.MonkeyPatch, link_in_envelope: bool
) -> None:
    w = signed
    intake = whatsapp.whatsapp_runtime().intake
    send = intake.transport.send
    first_saved, resume = asyncio.Event(), asyncio.Event()
    first_id, second_id = (f"wamid.W9.{100000000000000 + i}" for i in range(2))
    if link_in_envelope:
        w.desk.clock.now += timedelta(days=1)  # A fresh daily linking-reply allowance.
        assert (await w.client.delete(LINK, headers=w.desk.auth)).status_code == 204
        status = await w.request("GET", LINK, headers=w.desk.auth)
        code = await w.request(
            "POST", LINK + "-codes", headers=w.desk.auth,
            json={"disclosure_token": status["disclosure_token"]},
        )
        post = w.post

        async def link_then_forward(body: dict) -> None:
            link = fixture("text_link_code.json", id="wamid.SAME-LINK", text=code["message_text"])
            body["entry"][0]["changes"][0]["value"]["messages"][:0] = (
                link["entry"][0]["changes"][0]["value"]["messages"]
            )
            await post(body)

        monkeypatch.setattr(w, "post", link_then_forward)

    arrival = w.desk.clock.now

    async def after_read_receipt(payload: dict[str, Any]) -> None:
        await send(payload)
        if payload.get("message_id") == first_id:
            first_saved.set()
            await resume.wait()

    monkeypatch.setattr(intake.transport, "send", after_read_receipt)
    delivery = asyncio.create_task(
        w.forward(
            Receipt("Primera-en-sobre", w.desk.rnc["A"], None),
            Receipt("Segunda-en-sobre", w.desk.rnc["B"], None),
        )
    )
    try:
        await asyncio.wait_for(first_saved.wait(), timeout=5)
        if link_in_envelope:
            assert w.replies == [w.link_reply]
            w.replies.clear()
        first = intake.store.inbound(intake.keys.message(first_id))
        second = intake.store.inbound(intake.keys.message(second_id))
        assert await w.read(first.connection_id) == "prepared"
        await w.sweep(60)
        early = list(w.replies)
    finally:
        resume.set()
        connections = await delivery
    assert await w.read(connections[1]) == "prepared"
    await w.sweep(60)
    await w.sweep(60)
    assert early == []
    assert w.replies == [
        "Recibimos 2 facturas, gracias.\nYa están en la Bandeja:\n• Colmado Doña Rosa: 1\n• Taller Hermanos Peña: 1"
    ]
    assert second is not None and second.received_at == first.received_at == arrival
    assert second.status == "received" and second.claim_until is None
    assert second.connection_id is None and w.read_ids == [first_id, second_id]


@pytest.mark.asyncio
async def test_grant_revoked_before_reply_hides_business(signed: SignedForward) -> None:
    w, d = signed, signed.desk
    [cid] = await w.forward(Receipt("Revocado", d.rnc["vendor"], d.rnc["B"]))
    assert await w.read(cid) == "prepared"
    PostgresAccessStore(d.pool).revoke_grant(d.spaces["B"], d.users["B"], d.grants["B"])
    await w.sweep()
    assert w.replies == [
        "Recibimos tu factura, gracias.\n1 quedó sin negocio. Te espera en Cuadrao."
    ]


@pytest.mark.asyncio
async def test_text_audio_and_video_get_one_daily_reply(signed: SignedForward) -> None:
    w = signed
    await w.post(fixture("text_message.json", text="Buenas"))
    w.desk.clock.now += timedelta(seconds=60)
    await w.post(fixture("audio_message.json"))
    await w.sweep(0)
    assert w.replies == []
    await w.post(
        fixture(
            "audio_message.json",
            id="wamid.VIDEO",
            type="video",
            video={"id": "700000000000003"},
        )
    )
    assert w.read_ids == w.replies == []
    await w.sweep()
    greeting = "Hola. Por aquí no respondemos mensajes, solo recibimos facturas. Envía aquí la foto o el PDF de tus facturas."
    assert w.replies == [greeting]
    await w.post(fixture("audio_message.json", id="wamid.GUIDANCE3"))
    await w.sweep()
    assert w.replies == [greeting]


@pytest.mark.asyncio
@pytest.mark.parametrize("read_limit", [1])
async def test_three_files_wait_for_tomorrows_read_budget(signed: SignedForward) -> None:
    w, d = signed, signed.desk
    PostgresAccessStore(d.pool).revoke_grant(d.spaces["B"], d.users["B"], d.grants["B"])
    [first] = await w.forward(Receipt("Primera", d.rnc["A"], None))
    assert await w.read(first) == "prepared"
    await w.sweep()
    assert w.replies == [
        "Recibimos tu factura, gracias.\nYa está en la Bandeja:\n• Colmado Doña Rosa: 1"
    ]
    for cid in await w.forward(
        *(Receipt(f"Mañana-{n}", d.rnc["A"], None) for n in range(3))
    ):
        assert await w.read(cid) == "business_read_budget_day"
    assert len(w.read_ids) == 4
    await w.sweep()
    assert w.replies[1:] == [
        "Recibimos 3 facturas, gracias.\nYa están en la Bandeja:\n• Colmado Doña Rosa: 3\n"
        "Hoy llegamos al límite de lecturas. 3 se leerán mañana y no hace falta enviarlas de nuevo."
    ]


@asynccontextmanager
async def pause_download(
    w: SignedForward, receipt: Receipt, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[asyncio.Task[list[str]]]:
    started, release = asyncio.Event(), asyncio.Event()
    media = whatsapp.whatsapp_runtime().intake.media
    fetch = media.fetch

    async def delayed(media_id: str) -> FetchedMedia:
        started.set()
        await release.wait()
        return await fetch(media_id)

    with monkeypatch.context() as patch:
        patch.setattr(media, "fetch", delayed)
        delivery = asyncio.create_task(w.forward(receipt))
        try:
            await asyncio.wait_for(started.wait(), timeout=5)
            yield delivery
        finally:
            release.set()
            await delivery


@pytest.mark.asyncio
async def test_read_finishes_during_next_files_download(
    signed: SignedForward, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = signed
    [first] = await w.forward(Receipt("Venta-primera", w.desk.rnc["A"], None))
    await w.sweep(60)
    assert w.replies == []

    w.desk.clock.now += timedelta(seconds=30)
    async with pause_download(
        w, Receipt("Venta-segunda", w.desk.rnc["A"], None), monkeypatch
    ) as second:
        w.desk.clock.now += timedelta(seconds=20)
        assert await w.read(first) == "prepared"
        await w.sweep(10)
        assert w.replies == []
    [pending] = await second
    assert await w.read(pending) == "prepared"
    await w.sweep(60)
    expected = [
        "Recibimos 2 facturas, gracias.\nYa están en la Bandeja:\n• Colmado Doña Rosa: 2"
    ]
    assert w.replies == expected
    await w.sweep(60)
    assert w.replies == expected


@pytest.mark.asyncio
async def test_inflight_second_file_extends_first_files_deadline(
    signed: SignedForward, monkeypatch: pytest.MonkeyPatch
) -> None:
    w, clock = signed, signed.desk.clock
    [first] = await w.forward(Receipt("Pendiente-A", w.desk.rnc["A"], None))
    await w.sweep(60)
    await w.sweep(60)
    assert w.replies == []

    intake = whatsapp.whatsapp_runtime().intake
    clock.now += timedelta(seconds=20)
    arrival = clock.now
    async with pause_download(
        w, Receipt("Pendiente-B", w.desk.rnc["B"], None), monkeypatch
    ) as second:
        # The signed webhook has committed B's inbound claim but has no file to count yet.
        key = intake.keys.message("wamid.W9.100000000000001")
        inbound = intake.store.inbound(key)
        assert inbound.status == "received" and inbound.connection_id is None
        assert inbound.received_at == arrival
        clock.now += timedelta(seconds=30)
        assert await w.read(first) == "prepared"
        await w.sweep(10)  # t=180, 40 seconds after B arrived
        early = list(w.replies)
        clock.now += timedelta(seconds=20)
        assert clock.now < inbound.claim_until
    [last] = await second
    assert await w.read(last) == "prepared"
    w.upkeep = document_step.FailureReplyUpkeep(
        PostgresReplyGroups(w.desk.pool), clock=clock
    )
    await w.sweep(40)  # t=240, 100 seconds after B arrived
    completed = list(w.replies)
    await w.sweep(60)
    await w.sweep(60)
    summary = "Recibimos 2 facturas, gracias.\nYa están en la Bandeja:\n• Colmado Doña Rosa: 1\n• Taller Hermanos Peña: 1"
    assert (early, completed, w.replies) == ([], [summary], [summary])


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_second", [179, 180.5])
async def test_off_phase_read_finishes_before_deadline(
    signed: SignedForward, scheduler: ScheduledSweeps, finish_second: float
) -> None:
    w = signed
    await scheduler.advance(1)
    first, second = await w.forward(
        Receipt("Lista", w.desk.rnc["A"], None), Receipt("Ultima", w.desk.rnc["B"], None)
    )
    assert await w.read(first) == "prepared"
    await scheduler.advance(finish_second)
    assert w.replies == []
    assert await w.read(second) == "prepared"
    await scheduler.advance(181)
    expected = [
        "Recibimos 2 facturas, gracias.\nYa están en la Bandeja:\n• Colmado Doña Rosa: 1\n• Taller Hermanos Peña: 1"
    ]
    assert w.replies == expected
    await scheduler.advance(301)
    assert w.replies == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("sweep_interval", [30, 600])
async def test_off_phase_slow_reply_waits_until_exact_deadline(
    signed: SignedForward, scheduler: ScheduledSweeps
) -> None:
    w = signed
    await scheduler.advance(1)
    [slow] = await w.forward(Receipt("Lectura-lenta", w.desk.rnc["B"], None))
    await scheduler.advance(180.999)
    assert w.replies == []
    await scheduler.advance(181)
    expected = [
        "Recibimos tu factura, gracias.\nLa otra se está leyendo. Puedes seguirla en Cuadrao."
    ]
    assert w.replies == expected
    assert await w.read(slow) == "prepared"
    await scheduler.advance(301)
    assert w.replies == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("sweep_interval", [600])
async def test_long_document_sleep_still_closes_at_quiet_after_new_file(
    signed: SignedForward, scheduler: ScheduledSweeps
) -> None:
    w = signed
    await scheduler.advance(1)
    [first] = await w.forward(Receipt("Anterior", w.desk.rnc["A"], None))
    await scheduler.advance(90)
    assert w.replies == []
    [second] = await w.forward(Receipt("Nueva", w.desk.rnc["B"], None))
    assert await w.read(first) == await w.read(second) == "prepared"
    await scheduler.advance(149.999)
    assert w.replies == []
    await scheduler.advance(150)
    assert w.replies == [
        "Recibimos 2 facturas, gracias.\nYa están en la Bandeja:\n• Colmado Doña Rosa: 1\n• Taller Hermanos Peña: 1"
    ]


@pytest.mark.asyncio
async def test_blocked_worker_resumes_one_late_send(
    signed: SignedForward, scheduler: ScheduledSweeps
) -> None:
    w = signed
    await scheduler.advance(1)
    [slow] = await w.forward(Receipt("Barrido-tardío", w.desk.rnc["A"], None))
    await scheduler.advance(179)
    assert not w.replies
    # Simulate a stopped CPU. Only this test intentionally releases a requested sleep late.
    w.desk.clock.now = scheduler.start + timedelta(seconds=186)
    assert scheduler.wake_at <= w.desk.clock.now
    scheduler.release.set()
    await scheduler.wait_for_sleep()
    expected = [
        "Recibimos tu factura, gracias.\nLa otra se está leyendo. Puedes seguirla en Cuadrao."
    ]
    assert w.replies == expected
    assert await w.read(slow) == "prepared"
    await scheduler.advance(301)
    assert w.replies == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reply_language", "retry_active"),
    [("es-419", True), ("en", True), ("es-419", False)],
)
async def test_file_saved_after_its_own_deadline_never_starts_another_reply(
    signed: SignedForward,
    scheduler: ScheduledSweeps,
    monkeypatch: pytest.MonkeyPatch,
    reply_language: str,
    retry_active: bool,
    record_property,
) -> None:
    w, clock = signed, signed.desk.clock
    [first] = await w.forward(Receipt("Ya-guardada", w.desk.rnc["A"], None))
    assert await w.read(first) == "prepared"
    receipt = Receipt("Pendiente-de-descargar", w.desk.rnc["B"], None)
    media_id, message_id = "100000000000001", "wamid.OWN-DEADLINE"
    content = w.media[media_id] = receipt.png()
    w.receipts[sha256(content).hexdigest()] = receipt
    raw = encode(
        fixture(
            "image_message.json",
            id=message_id,
            image={"id": media_id, "mime_type": "image/png"},
        ),
        clock.now,
    )

    async def deliver() -> httpx.Response:
        return await w.client.post(
            whatsapp.WEBHOOK_PATH, content=raw, headers={"X-Hub-Signature-256": sign(raw)}
        )

    # The first process stops after admitting B. The provider repeats the identical signed delivery.
    intake = whatsapp.whatsapp_runtime().intake
    fetch = intake.media.fetch

    await interrupt_download(intake.media, deliver, monkeypatch)
    key = intake.keys.message(message_id)
    inbound = intake.store.inbound(key)
    assert inbound.status == "received" and inbound.connection_id is None
    await scheduler.advance(60)
    assert w.replies == []
    await scheduler.advance(115)
    assert clock.now > inbound.claim_until

    async def reach_cutoff() -> list[str]:
        await scheduler.advance(179.999)
        assert w.replies == []
        await scheduler.advance(180)
        before_save = list(w.replies)
        assert (clock.now - inbound.received_at).total_seconds() == 180
        waiting = intake.store.inbound(key)
        assert waiting.status == "received" and waiting.connection_id is None
        assert (clock.now < waiting.claim_until) == retry_active
        assert w.read_ids == ["wamid.W9.100000000000000"]
        await scheduler.advance(185)
        return before_save

    if retry_active:
        fetching, release = asyncio.Event(), asyncio.Event()

        async def retry_download(media_id: str) -> FetchedMedia:
            fetching.set()
            await release.wait()
            return await fetch(media_id)

        with monkeypatch.context() as patch:
            patch.setattr(intake.media, "fetch", retry_download)
            retry = asyncio.create_task(deliver())
            try:
                await asyncio.wait_for(fetching.wait(), timeout=5)
                before_save = await reach_cutoff()
            finally:
                release.set()
                result = await retry
    else:
        before_save = await reach_cutoff()
        result = await deliver()
    assert result.status_code == 200
    assert w.read_ids == ["wamid.W9.100000000000000", message_id]
    assert (clock.now - inbound.received_at).total_seconds() == 185
    assert await w.read(intake.store.inbound(key).connection_id) == "prepared"
    await scheduler.advance(300)
    expected = (
        "Recibimos 2 facturas, gracias.\nYa está en la Bandeja:\n• Colmado Doña Rosa: 1\nLa otra se está leyendo. Puedes seguirla en Cuadrao."
        if reply_language == "es-419"
        else "We received 2 invoices, thank you.\nIt's in your Inbox:\n• Colmado Doña Rosa: 1\nThe other one is still being read. You can follow it in Cuadrao."
    )
    assert before_save == w.replies == [expected]
    record_property(
        "walkthrough",
        f"{reply_language} | uncommitted at 180 s, saved and marked read at 185 s | "
        f"retry active={retry_active} | replies by deadline={len(before_save)} | follow-ups=0",
    )
