"""The setup step list: its one owner decides the steps, which are required and
whether each is done; a step whose feature is off is not sent."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from argus.api.routers import business_setup
from argus.domain.business.setup import SetupFacts, setup_steps
from faker import Faker

fake = Faker()


def _facts(**overrides: bool | None) -> SetupFacts:
    values = {
        "fiscal_identity": False,
        "receiving_address": False,
        "receipt_reading": False,
        "first_document": False,
        "team": False,
        "whatsapp": False,
    }
    return SetupFacts(**{**values, **overrides})


def test_steps_keep_their_order_and_which_are_required():
    assert [(step["key"], step["required"]) for step in setup_steps(_facts())] == [
        ("created", True),
        ("fiscal_identity", True),
        ("receiving_address", True),
        ("receipt_reading", True),
        ("first_document", False),
        ("team", False),
        ("whatsapp", False),
    ]
    assert setup_steps(_facts())[0]["done"] is True, "the Business exists"


@pytest.mark.parametrize("off", ["receiving_address", "receipt_reading", "team", "whatsapp"])
def test_a_step_whose_feature_is_off_is_not_sent(off: str):
    keys = [step["key"] for step in setup_steps(_facts(**{off: None}))]
    assert off not in keys
    assert len(keys) == 6


@pytest.mark.parametrize(
    ("fact", "done"),
    [("fiscal_identity", True), ("receipt_reading", True), ("first_document", True), ("team", True), ("whatsapp", False)],
)
def test_each_step_carries_its_own_fact(fact: str, done: bool):
    [step] = [step for step in setup_steps(_facts(**{fact: done})) if step["key"] == fact]
    assert step["done"] is done


def _context(*, reading: dict | None, sources: tuple = ()):  # noqa: ANN202
    space_id, person_id = fake.uuid4(), fake.uuid4()
    consent = None if reading is None else SimpleNamespace(status=lambda *_: reading)
    hub = SimpleNamespace(connections=SimpleNamespace(list=lambda **_: list(sources)))
    return SimpleNamespace(
        scope=SimpleNamespace(
            owner=SimpleNamespace(space_id=space_id),
            person_id=person_id,
            acting_person_id=person_id,
        ),
        service=SimpleNamespace(documents=SimpleNamespace(business_receipt_consent=consent, hub=hub)),
    )


def _wire(monkeypatch, *, email: bool | None, invitations: bool, whatsapp_linked: bool | None, grants: tuple, tax_id):  # noqa: ANN001, ANN202
    monkeypatch.setattr(business_setup, "receiving_address_ready", lambda space_id: email)
    monkeypatch.setattr(business_setup, "invitations_available", lambda: invitations)
    monkeypatch.setattr(
        business_setup,
        "business_access",
        lambda: SimpleNamespace(list=lambda *_: SimpleNamespace(grants=grants, invites=())),
    )
    if whatsapp_linked is None:
        monkeypatch.setattr(business_setup, "whatsapp_runtime", lambda: None)
    else:
        link = object() if whatsapp_linked else None
        store = SimpleNamespace(destination_link=lambda **_: link)
        monkeypatch.setattr(business_setup, "whatsapp_runtime", lambda: SimpleNamespace(intake=SimpleNamespace(store=store)))
        monkeypatch.setattr(business_setup, "whatsapp_receiving_available", lambda scope: True)
    monkeypatch.setattr(
        business_setup,
        "read_profile",
        lambda *_: {"name": fake.company(), "tax_id": tax_id, "can_edit": True},
    )


def _read(context) -> dict[str, dict]:  # noqa: ANN001
    drafts = SimpleNamespace(service=SimpleNamespace(authority=None), for_space=lambda *_: None)
    facts = business_setup._facts(SimpleNamespace(), context, drafts, SimpleNamespace(spaces=None))
    return {step["key"]: step for step in setup_steps(facts)}


def test_every_feature_on_reads_each_fact_from_its_owner(monkeypatch):
    owner = SimpleNamespace(owner=True)
    accountant = SimpleNamespace(owner=False)
    _wire(monkeypatch, email=True, invitations=True, whatsapp_linked=True, grants=(owner, accountant), tax_id={"type": "rnc", "value": "131245678"})
    received = SimpleNamespace(source="statement", status="ready")
    steps = _read(_context(reading={"available": True, "enabled": False}, sources=(received,)))
    assert {key: step["done"] for key, step in steps.items()} == {
        "created": True,
        "fiscal_identity": True,
        "receiving_address": True,
        "receipt_reading": False,
        "first_document": True,
        "team": True,
        "whatsapp": True,
    }


def test_every_feature_off_sends_only_the_business_and_its_identity(monkeypatch):
    _wire(monkeypatch, email=None, invitations=False, whatsapp_linked=None, grants=(SimpleNamespace(owner=True),), tax_id=None)
    steps = _read(_context(reading={"available": False, "enabled": False}))
    assert {key: step["done"] for key, step in steps.items()} == {"created": True, "fiscal_identity": False, "first_document": False}
    assert _read(_context(reading=None)).keys() == {"created", "fiscal_identity", "first_document"}


def test_the_owners_own_grant_is_not_a_team(monkeypatch):
    _wire(monkeypatch, email=None, invitations=True, whatsapp_linked=None, grants=(SimpleNamespace(owner=True),), tax_id=None)
    assert _read(_context(reading=None))["team"]["done"] is False


def test_a_default_name_is_not_a_legal_name(monkeypatch):
    _wire(monkeypatch, email=None, invitations=False, whatsapp_linked=None, grants=(), tax_id={"type": "rnc", "value": "131245678"})
    monkeypatch.setattr(business_setup, "read_profile", lambda *_: {"name": "Mi negocio", "tax_id": {"type": "rnc", "value": "131245678"}})
    assert _read(_context(reading=None))["fiscal_identity"]["done"] is False


@pytest.mark.parametrize(
    ("source", "status", "done"),
    [("statement", "ready", True), ("statement", "disconnected", False), ("bank", "ready", False)],
)
def test_only_a_received_document_completes_the_first_document(monkeypatch, source: str, status: str, done: bool):
    _wire(monkeypatch, email=None, invitations=False, whatsapp_linked=None, grants=(), tax_id=None)
    connection = SimpleNamespace(source=source, status=status)
    assert _read(_context(reading=None, sources=(connection,)))["first_document"]["done"] is done
