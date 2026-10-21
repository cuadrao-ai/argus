"""Import, suggestion, decline memory, and the sin comprobante count."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from argus.domain.business.bank.matching import derive_confidence, score_parts
from argus.domain.business.bank.model import (
    AccountRef,
    BankLine,
    BankMatchingError,
    ScoreParts,
)
from argus.domain.business.bank.service import (
    BankMatchingService,
    configure_bank_matching,
    unmatched_charge_count,
)
from argus.domain.business.bank.store import MemoryBankStore
from argus.domain.business.bank.targets import (
    RecordedTarget,
    StaticCatalog,
    receipt_target_from_event,
)
from faker import Faker

Faker.seed(17)
_NAMES = [Faker("es_ES").company() for _ in range(5)]
SPACE = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OWNER = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
ACCOUNT = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
OTHER = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
PREPARE = frozenset({"read", "prepare", "approve"})
READ = frozenset({"read"})
WHEN = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


def _popular(rows: list[tuple[str, str, str, str]]) -> bytes:
    buf = io.StringIO()
    buf.write("# synthetic\n")
    writer = csv.writer(buf)
    writer.writerow(["Fecha", "Descripcion", "Debito", "Credito", "Moneda"])
    for day, name, debit, credit in rows:
        writer.writerow([day, name, debit, credit, "DOP"])
    return buf.getvalue().encode()


def _world(targets: tuple[RecordedTarget, ...] = ()):
    known = {ACCOUNT: "DOP", OTHER: "DOP"}

    def account_of(space_id, owner_id, account_id):  # noqa: ANN001
        del space_id, owner_id
        currency = known.get(account_id)
        if currency is None:
            return None
        return AccountRef(account_id, currency)

    service = BankMatchingService(
        MemoryBankStore(clock=lambda: WHEN),
        StaticCatalog(targets),
        account_of,
        clock=lambda: WHEN,
    )
    return service


def _import(service, content: bytes, key: str = "import-1", account=ACCOUNT):
    return service.import_statement(
        space_id=SPACE,
        actor_id=OWNER,
        owner_id=OWNER,
        capabilities=PREPARE,
        content=content,
        account_id=account,
        reader_id=None,
        mapping=None,
        idempotency_key=key,
    )


def _target(kind: str, amount: str, day: str, merchant: str, approved: bool = True):
    return RecordedTarget(
        id=str(uuid4()),
        kind=kind,  # type: ignore[arg-type]
        amount=Decimal(amount),
        currency="DOP",
        occurred_on=date.fromisoformat(day),
        merchant=merchant,
        approved=approved,
    )


def test_a_repeat_import_returns_the_same_lines_and_does_not_rewrite_them() -> None:
    content = _popular([("01/10/2026", _NAMES[0], "10.00", "")])
    service = _world()
    first = _import(service, content, "same")
    again = _import(service, content, "same")
    assert first.created is True
    assert again.created is False
    assert again.lines[0].id == first.lines[0].id
    assert again.lines[0].raw_line == first.lines[0].raw_line
    third = _import(service, content, "other-key")
    assert third.bank_import.inserted_count == 0
    assert third.bank_import.unchanged_count == 1
    assert third.lines[0].id == first.lines[0].id


def test_the_same_key_with_different_bytes_conflicts() -> None:
    service = _world()
    _import(service, _popular([("01/10/2026", "A", "10.00", "")]), "same")
    with pytest.raises(BankMatchingError) as raised:
        _import(service, _popular([("01/10/2026", "B", "10.00", "")]), "same")
    assert raised.value.code == "idempotency_conflict"


def test_identical_raw_rows_stay_distinct() -> None:
    content = _popular(
        [
            ("01/10/2026", "Same", "10.00", ""),
            ("01/10/2026", "Same", "10.00", ""),
        ]
    )
    result = _import(_world(), content)
    assert result.bank_import.inserted_count == 2
    assert result.lines[0].line_hash != result.lines[1].line_hash


def test_nothing_auto_matches_and_a_declined_pair_is_not_offered_again() -> None:
    merchant = _NAMES[0]
    decoy = _target("receipt", "1500.00", "2026-10-01", merchant)
    real = _target("receipt", "1500.00", "2026-10-01", merchant)
    service = _world((decoy, real))
    content = _popular([("01/10/2026", merchant, "1500.00", "")])
    first = _import(service, content, "one")
    assert {row.status for row in first.suggestions} == {"pending"}
    assert all(
        derive_confidence(row.parts) == Decimal("1.000") for row in first.suggestions
    )
    declined = next(row for row in first.suggestions if row.target_id == decoy.id)
    service.decline_suggestion(
        space_id=SPACE,
        actor_id=OWNER,
        capabilities=PREPARE,
        suggestion_id=declined.id,
        idempotency_key="decline-1",
    )
    second = _import(service, content, "two")
    assert decoy.id not in {row.target_id for row in second.suggestions}
    still = service.list_suggestions(space_id=SPACE, capabilities=READ, status="declined")
    assert [row.target_id for row in still] == [decoy.id]


def test_one_confirmed_suggestion_per_line_and_confirming_a_decline_is_refused() -> None:
    merchant = _NAMES[1]
    first_target = _target("receipt", "800.00", "2026-10-03", merchant)
    second_target = _target("receipt", "800.00", "2026-10-03", merchant)
    service = _world((first_target, second_target))
    imported = _import(service, _popular([("03/10/2026", merchant, "800.00", "")]))
    chosen, other = imported.suggestions
    service.confirm_suggestion(
        space_id=SPACE,
        actor_id=OWNER,
        capabilities=PREPARE,
        suggestion_id=chosen.id,
        idempotency_key="yes",
    )
    with pytest.raises(BankMatchingError) as blocked:
        service.confirm_suggestion(
            space_id=SPACE,
            actor_id=OWNER,
            capabilities=PREPARE,
            suggestion_id=other.id,
            idempotency_key="also",
        )
    assert blocked.value.code == "line_already_confirmed"
    service.decline_suggestion(
        space_id=SPACE,
        actor_id=OWNER,
        capabilities=PREPARE,
        suggestion_id=other.id,
        idempotency_key="no",
    )
    with pytest.raises(BankMatchingError) as declined:
        service.confirm_suggestion(
            space_id=SPACE,
            actor_id=OWNER,
            capabilities=PREPARE,
            suggestion_id=other.id,
            idempotency_key="undo",
        )
    assert declined.value.code == "pair_declined"


def test_a_reader_cannot_import_and_a_second_account_is_refused() -> None:
    service = _world()
    content = _popular([("01/10/2026", "A", "10.00", "")])
    with pytest.raises(BankMatchingError) as denied:
        service.import_statement(
            space_id=SPACE,
            actor_id=OWNER,
            owner_id=OWNER,
            capabilities=READ,
            content=content,
            account_id=ACCOUNT,
            reader_id=None,
            mapping=None,
            idempotency_key="read-only",
        )
    assert denied.value.code == "business_permission_denied"
    _import(service, content)
    with pytest.raises(BankMatchingError) as second:
        _import(service, content, "next", OTHER)
    assert second.value.code == "one_account"


def test_october_statement_ends_igualada_or_missing_its_receipt() -> None:
    """Synthetic 1–17 Oct. Deposits need a venta stub. The unmatched charge is the list."""

    charge_a, charge_b, unmatched, sale_a, sale_b = _NAMES
    targets = (
        _target("receipt", "1500.00", "2026-10-01", charge_a),
        _target("receipt", "800.00", "2026-10-03", charge_b),
        _target("venta", "5000.00", "2026-10-10", sale_a),
        _target("venta", "1200.00", "2026-10-15", sale_b),
    )
    service = _world(targets)
    content = _popular(
        [
            ("01/10/2026", charge_a, "1500.00", ""),
            ("03/10/2026", charge_b, "800.00", ""),
            ("07/10/2026", unmatched, "250.00", ""),
            ("10/10/2026", sale_a, "", "5000.00"),
            ("15/10/2026", sale_b, "", "1200.00"),
        ]
    )
    imported = _import(service, content, "oct")
    assert len(imported.lines) == 5
    assert imported.lines[2].amount == Decimal("-250.0000")
    for suggestion in imported.suggestions:
        service.confirm_suggestion(
            space_id=SPACE,
            actor_id=OWNER,
            capabilities=PREPARE,
            suggestion_id=suggestion.id,
            idempotency_key=f"yes-{suggestion.id}",
        )
    states = [service.line_state(line) for line in imported.lines]
    assert states == [
        "igualada",
        "igualada",
        "falta_comprobante",
        "igualada",
        "igualada",
    ]
    open_charges = service.unmatched_charges(
        space_id=SPACE,
        period_start=date(2026, 10, 1),
        period_end=date(2026, 10, 17),
    )
    assert [line.amount for line in open_charges] == [Decimal("-250.0000")]
    configure_bank_matching(service)
    try:
        assert unmatched_charge_count(SPACE, date(2026, 10, 1), date(2026, 10, 17)) == 1
    finally:
        configure_bank_matching(None)


def test_a_deposit_without_a_venta_is_missing_proof_but_not_an_unmatched_charge() -> None:
    service = _world()
    imported = _import(service, _popular([("10/10/2026", "Cobro", "", "5000.00")]))
    assert service.line_state(imported.lines[0]) == "falta_comprobante"
    assert (
        service.unmatched_charge_count(SPACE, date(2026, 10, 1), date(2026, 10, 17)) == 0
    )


def test_score_requires_amount_currency_and_the_date_window() -> None:
    line = BankLine(
        id=uuid4(),
        space_id=SPACE,
        bank_account_id=uuid4(),
        first_import_id=uuid4(),
        occurred_on=date(2026, 10, 1),
        description="Ferreteria Luna",
        normalized_description="ferreteria luna",
        amount=Decimal("-10.0000"),
        currency="DOP",
        raw_line={},
        line_hash="a" * 64,
        created_at=WHEN,
    )
    close = _target("receipt", "10.00", "2026-10-06", "Ferreteria Luna")
    far = _target("receipt", "10.00", "2026-10-07", "Ferreteria Luna")
    assert score_parts(line, close) == ScoreParts(
        Decimal("1.000"), Decimal("0.000"), Decimal("1.000")
    )
    assert score_parts(line, far) is None


def test_receipt_targets_come_from_accepted_expenses_only() -> None:
    class Event:
        id = "evt-1"
        state = "accepted"
        resolution = {
            "business": {
                "facts": {
                    "kind": {"state": "known", "value": "expense"},
                    "amount": {"state": "known", "value": "10.00"},
                    "currency": {"state": "known", "value": "DOP"},
                    "occurred_on": {"state": "known", "value": "2026-10-01"},
                    "counterparty": {"state": "known", "value": "Luna"},
                }
            }
        }

    found = receipt_target_from_event(Event())
    assert found is not None and found.kind == "receipt"
    Event.state = "draft"
    assert receipt_target_from_event(Event()) is None


def test_the_count_is_unavailable_until_the_service_starts() -> None:
    configure_bank_matching(None)
    with pytest.raises(BankMatchingError) as raised:
        unmatched_charge_count(SPACE, date(2026, 10, 1), date(2026, 10, 17))
    assert raised.value.code == "business_bank_matching_off"
