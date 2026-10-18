"""Receipt alias, sender standing, alignment, and the daily hold."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4

import pytest
from argus.domain.ingestion.documents.config import SOURCE_MAX_BYTES
from argus.domain.ingestion.email_intake.alias import (
    ALIAS_UNAVAILABLE,
    fold_variants,
    inspect_alias,
    judge_normalized,
    suggest_alias,
)
from argus.domain.ingestion.email_intake.alignment import assess, sign_relaxed
from argus.domain.ingestion.email_intake.budget import (
    DailyEmailBudget,
    business_day,
    next_business_day,
)
from argus.domain.ingestion.email_intake.routing import (
    FIRST_SCAN_LABEL,
    UNVERIFIED_NOTE,
    bounce_copy,
    decide,
)
from argus.domain.ingestion.email_intake.words import ANYWHERE_WORDS, domain_is_free
from cryptography.hazmat.primitives.asymmetric import rsa

from tests.ingestion.test_email_intake_service import RECIPIENT, rig

_DOMAIN = re.compile(r"(?<![A-Za-z0-9_-])receipts\.[a-z0-9-]+\.[a-z]{2,}")
_ROOT = Path(__file__).resolve().parents[2]
_DR_NAMES = (
    ("Ferretería Núñez", "ferreterianunez"),
    ("Ferretería Núñez S.R.L.", "ferreterianunez"),
    ("Ferretería Núñez E.I.R.L.", "ferreterianunez"),
    ("Colmado Rodríguez S.A.", "colmadorodriguez"),
    ("Supermercado Nacional", "supermercadonacional"),
    ("Farmacia Pérez", "farmaciaperez"),
    ("Pinturas García", "pinturasgarcia"),
    ("Papelería Martínez", "papeleriamartinez"),
    ("Taller Santana", "tallersantana"),
    ("Panadería Peña", "panaderiapena"),
    ("Boutique Cruz", "boutiquecruz"),
    ("Ferretería Santiago", "ferreteriasantiago"),
    ("Colmado La Vega", "colmadolavega"),
    ("Farmacia La Romana", "farmacialaromana"),
    ("Taller Puerto Plata", "tallerpuertoplata"),
)


def _open(alias: str) -> dict:
    return inspect_alias(alias, lambda candidate: False)


def test_suggestion_drops_marks_and_trailing_legal_forms():
    for name, expected in _DR_NAMES:
        alias = suggest_alias(name)
        assert alias == expected, name
        assert _open(alias)["status"] == "available", name


@pytest.mark.parametrize("alias", ["infotecsrl", "legalconsult", "pagosfacil"])
def test_ordinary_business_names_pass(alias: str):
    assert _open(alias)["status"] == "available"


@pytest.mark.parametrize("alias", ["micuadraostore", "cuadra0", "micuadrao1x"])
def test_product_name_and_unambiguous_folds_are_refused(alias: str):
    report = _open(alias)
    assert report["status"] == "refused"
    assert report["message"] == ALIAS_UNAVAILABLE


def test_digit_one_is_checked_both_ways_and_disagreement_is_review():
    assert set(fold_variants("sh1t")) == {"shit", "shlt"}
    assert judge_normalized("sh1t", taken=False) == "review"
    report = _open("sh1t")
    assert report["available"] is True
    assert report["review_required"] is True
    assert report["message"] is None


def test_a_taken_name_and_a_refused_name_say_the_same_thing():
    taken = inspect_alias("ferreterianunez", lambda alias: alias == "ferreterianunez")
    refused = _open("cuadra0")
    assert taken["message"] == refused["message"] == ALIAS_UNAVAILABLE
    assert "recipient" not in taken
    assert "ferreterianunez@" not in str(taken)
    suggestions = taken["suggestions"]
    assert 2 <= len(suggestions) <= 3
    assert "ferreterianunez" not in suggestions
    assert all(_open(item)["status"] == "available" for item in suggestions)


def test_an_allow_listed_word_covers_only_its_own_span(monkeypatch):
    import argus.domain.ingestion.email_intake.alias as alias_module
    import argus.domain.ingestion.email_intake.words as words

    monkeypatch.setattr(words, "ANYWHERE_WORDS", frozenset({"nune"}) | ANYWHERE_WORDS)
    monkeypatch.setattr(alias_module, "ANYWHERE_WORDS", words.ANYWHERE_WORDS)
    assert judge_normalized("nunez", taken=False) == "available"
    assert judge_normalized("nunezshit", taken=False) == "refused"


def test_a_system_name_stays_refused_when_it_is_also_allow_listed(monkeypatch):
    import argus.domain.ingestion.email_intake.alias as alias_module
    import argus.domain.ingestion.email_intake.words as words

    monkeypatch.setattr(words, "ALLOW_WORDS", words.ALLOW_WORDS | {"admin"})
    monkeypatch.setattr(alias_module, "ALLOW_WORDS", words.ALLOW_WORDS)
    assert judge_normalized("admin", taken=False) == "refused"
    assert judge_normalized("infotec", taken=False) == "available"


def test_surnames_and_towns_are_not_false_rejects():
    from argus.domain.ingestion.email_intake.words import ALLOW_SURNAMES, ALLOW_TOWNS

    for alias in ALLOW_SURNAMES | ALLOW_TOWNS:
        assert judge_normalized(alias, taken=False) == "available", alias


def test_no_inbound_domain_is_hardcoded_outside_config():
    hits = []
    for folder in ("src", "tests", "docs", "supabase", "scripts"):
        for path in (_ROOT / folder).rglob("*"):
            if path.suffix.lower() not in {".py", ".md", ".yaml", ".yml", ".sql", ".json"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if _DOMAIN.search(text):
                hits.append(str(path.relative_to(_ROOT)))
    assert hits == []
    package = _ROOT / "src/argus/domain/ingestion/email_intake"
    for path in package.glob("*.py"):
        assert "receipts." not in path.read_text(encoding="utf-8"), path.name


def test_free_mail_domains_and_their_subdomains_cannot_be_whole_rules():
    assert domain_is_free("gmail.com")
    assert domain_is_free("mail.gmail.com")
    assert domain_is_free("live.com.do")
    assert not domain_is_free("gmail.com.example.test")
    assert not domain_is_free("tienda.test")


def test_routing_never_approves_and_keeps_unverified_mail_in_the_tray():
    new = decide("new", "unknown", first_authorized=False)
    assert (new.group, new.approved, new.skip) == ("remitentes_nuevos", False, False)
    aligned = decide("authorized", "aligned", first_authorized=True)
    assert (aligned.group, aligned.note, aligned.first_scan, aligned.approved) == (
        "bandeja",
        None,
        True,
        False,
    )
    pending = decide("authorized", "unknown", first_authorized=False)
    assert (pending.group, pending.note, pending.skip) == (
        "bandeja",
        UNVERIFIED_NOTE,
        False,
    )
    assert FIRST_SCAN_LABEL == "Prueba recibida"


def _letter(sender: str = "proveedor@example.test") -> bytes:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = RECIPIENT
    message["Subject"] = "Factura"
    message["Date"] = "Mon, 12 Oct 2026 12:00:00 +0000"
    message.set_content("Adjunto la factura.")
    return message.as_bytes()


def test_alignment_is_in_app_and_ignores_a_header_that_claims_a_pass():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signed, public = sign_relaxed(
        _letter(), private, domain="example.test", selector="mail"
    )

    def keys(domain: str, selector: str):
        if domain == "example.test" and selector == "mail":
            return public
        return None

    assert assess(signed, keys) == "aligned"
    separator = b"\r\n\r\n" if b"\r\n\r\n" in signed else b"\n\n"
    head, body = signed.split(separator, 1)
    tampered = head + separator + body.replace(b"factura", b"facturx", 1)
    assert assess(tampered, keys) == "failed"
    other, _public = sign_relaxed(
        _letter(), private, domain="other.test", selector="mail"
    )
    assert assess(other, keys) == "failed"
    assert assess(_letter(), keys) == "unknown"
    claimed = (
        b"Authentication-Results: example.test; dkim=pass\r\n" + _letter()
    )
    assert assess(claimed, keys) == "unknown"
    assert assess(signed, lambda _domain, _selector: None) == "failed"


@pytest.mark.asyncio
async def test_changing_the_alias_leaves_the_receipt_and_bounces_the_old_address():
    world = rig()
    delivery = world.enqueue()
    assert await world.runtime.next()
    old = world.route.recipient
    domain = old.split("@", 1)[1]
    world.store.change_address(
        world.route.id,
        alias="ferreterianunez",
        alias_normalized="ferreterianunez",
        recipient=f"ferreterianunez@{domain}",
        review_required=False,
    )
    saved = world.store.get(delivery.id, world.route.space_id)
    assert saved.route_id == world.route.id
    assert saved.recipients == (old,)
    assert saved.approved is False
    bounced = world.runtime.enqueue_resend(str(uuid4()), (old,))
    assert (bounced.state, bounced.error_code) == ("rejected", "email_alias_retired")
    assert bounced.bounce_text == bounce_copy()
    assert "ferreterianunez" not in bounced.bounce_text
    assert "Reportar dirección" in bounced.bounce_text
    from argus.domain.ingestion.email_intake.store import RecipientTaken

    with pytest.raises(RecipientTaken):
        world.store.create_route(
            recipient=old,
            space_id=str(uuid4()),
            principal_id=str(uuid4()),
            granted_by=str(uuid4()),
            grant_id=str(uuid4()),
            alias="tallerpena",
            alias_normalized="tallerpena",
        )


@pytest.mark.asyncio
async def test_the_101st_unauthorized_message_is_held_until_the_next_business_day():
    world = rig()
    world.store.budget = DailyEmailBudget(100, 100 * SOURCE_MAX_BYTES)
    for _ in range(100):
        admitted = world.runtime.enqueue_resend(str(uuid4()), (RECIPIENT,))
        admitted = world.store.gate_unauthorized(admitted)
        world.store._deliveries[admitted.id] = replace(admitted, state="captured")
    extra = world.runtime.enqueue_resend(str(uuid4()), (RECIPIENT,))
    assert extra.error_code is None
    assert await world.runtime.next()
    held = world.store.get(extra.id, world.route.space_id)
    assert (held.state, held.error_code) == ("received", "email_daily_message_budget")
    assert world.provider.calls == 0
    assert world.store.claim(delivery_id=extra.id) is None
    world.clock.now = next_business_day(world.clock.now)
    assert await world.runtime.next()
    assert world.store.get(extra.id, world.route.space_id).state == "captured"
    assert world.provider.calls == 1


@pytest.mark.asyncio
async def test_authorized_mail_is_not_counted_or_held_when_the_cap_is_full():
    world = rig()
    world.store.budget = DailyEmailBudget(1, 100 * SOURCE_MAX_BYTES)
    filled = world.enqueue()
    world.store._deliveries[filled.id] = replace(
        world.store.get(filled.id, world.route.space_id), state="captured"
    )
    world.store.upsert_sender(
        world.route.space_id, "address", "proveedor@example.test", "authorized"
    )
    incoming = world.runtime.enqueue_resend(str(uuid4()), (RECIPIENT,))
    assert await world.runtime.next()
    saved = world.store.get(incoming.id, world.route.space_id)
    assert saved.state == "captured"
    assert saved.cap_exempt is True
    assert saved.inbox_group == "bandeja"
    assert saved.review_note == UNVERIFIED_NOTE
    assert saved.first_scan is True
    assert saved.approved is False
    day = business_day(world.clock())
    assert world.store._usage[(world.route.id, day)] == [1, 0]
    again = world.runtime.enqueue_resend(str(uuid4()), (RECIPIENT,))
    assert await world.runtime.next()
    second = world.store.get(again.id, world.route.space_id)
    assert second.first_scan is False
    assert world.store._usage[(world.route.id, day)][0] == 1


def test_the_santo_domingo_boundary_opens_a_new_allowance():
    world = rig()
    world.store.budget = DailyEmailBudget(1, 100 * SOURCE_MAX_BYTES)
    world.clock.now = datetime(2026, 10, 12, 3, 59, 59, tzinfo=timezone.utc)
    assert world.enqueue().error_code is None
    waiting = world.enqueue()
    assert waiting.error_code == "email_daily_message_budget"
    world.clock.advance(2)
    assert world.enqueue().error_code is None
    assert world.store.claim(delivery_id=waiting.id) is not None
    assert business_day(world.clock.now) == datetime(2026, 10, 12).date()


@pytest.mark.asyncio
async def test_a_blocked_sender_is_rejected_and_a_new_sender_is_not_approved():
    world = rig()
    world.store.upsert_sender(
        world.route.space_id, "domain", "example.test", "authorized"
    )
    world.store.upsert_sender(
        world.route.space_id, "address", "proveedor@example.test", "blocked"
    )
    blocked = world.runtime.enqueue_resend(str(uuid4()), (RECIPIENT,))
    assert await world.runtime.next()
    saved = world.store.get(blocked.id, world.route.space_id)
    assert (saved.state, saved.error_code) == ("rejected", "email_sender_blocked")
    assert world.provider.calls == 0
    world.store.upsert_sender(
        world.route.space_id, "address", "proveedor@example.test", "authorized"
    )
    # The address rule already consumed nothing. A different sender is new.
    fresh_raw = EmailMessage()
    fresh_raw["From"] = "otro@tienda.test"
    fresh_raw["To"] = RECIPIENT
    fresh_raw["Subject"] = "Otra factura"
    fresh_raw.set_content("Adjunto otra factura.")
    world.provider.raw = fresh_raw.as_bytes()
    world.provider.sender = "otro@tienda.test"
    fresh = world.runtime.enqueue_resend(str(uuid4()), (RECIPIENT,))
    assert await world.runtime.next()
    landed = world.store.get(fresh.id, world.route.space_id)
    assert landed.state == "captured"
    assert landed.inbox_group == "remitentes_nuevos"
    assert landed.approved is False
    replay = world.runtime.enqueue_resend(fresh.external_id, (RECIPIENT,))
    assert replay.id == fresh.id


def test_deactivate_is_not_retirement():
    world = rig()
    old = world.route.recipient
    world.store.deactivate_routes(world.route.space_id)
    rejected = world.runtime.enqueue_resend(str(uuid4()), (old,))
    assert rejected.error_code == "email_route_unavailable"
    assert rejected.bounce_text is None
