"""Plaid rows as import-candidate evidence, per Plaid's documented semantics."""

from datetime import date

import pytest
from argus.domain.ingestion.plaid import mapping

from tests.ingestion.plaid_fakes import CARD, CHECKING, NOW, txn

HINTS, _ = mapping.account_hints([CHECKING, CARD], institution="First Platypus Bank")


def candidate(row):  # noqa: ANN001
    return mapping.transaction_candidate(
        row, connection_id="conn-1", accounts=HINTS, observed_at=NOW
    )


def test_positive_amount_is_money_out_and_carries_the_account_hint():
    c = candidate(txn("t1", 4.33))
    assert (c.amount, c.direction, c.currency) == ("4.33", "outflow", "USD")
    assert (c.evidence, c.status, c.kind_hint) == ("transaction", "posted", "expense")
    assert (
        c.merchant == "Blue Bottle Coffee" and c.description == "BLUE BOTTLE COFFEE 123"
    )
    assert c.account.external_account_id == "acc-checking"
    assert (c.account.mask, c.account.type_hint, c.account.currency) == (
        "0000",
        "depository",
        "USD",
    )
    assert c.account.institution == "First Platypus Bank"
    assert c.unresolved() == frozenset()


def test_negative_amount_is_money_in():
    c = candidate(txn("t2", -1200, primary="INCOME", detailed="INCOME_WAGES"))
    assert (c.amount, c.direction, c.kind_hint) == ("1200", "inflow", "income")


def test_pending_uses_date_as_occurrence_and_has_no_posting_date():
    c = candidate(txn("p1", 10, pending=True, date="2026-09-30", authorized_date=None))
    assert c.status == "pending"
    assert (c.occurred_on, c.posted_on) == (date(2026, 9, 30), None)
    assert c.source.replaces_external_id is None


def test_posted_prefers_authorized_date_and_names_its_pending_row():
    c = candidate(
        txn(
            "x1",
            10,
            pending_transaction_id="p1",
            date="2026-10-01",
            authorized_date="2026-09-29",
        )
    )
    assert (c.occurred_on, c.posted_on) == (date(2026, 9, 29), date(2026, 10, 1))
    assert c.source.replaces_external_id == "p1"


def test_posted_without_authorized_date_falls_back_to_date():
    c = candidate(txn("x2", 10, date="2026-10-01", authorized_date=None))
    assert c.occurred_on == c.posted_on == date(2026, 10, 1)


def test_unofficial_currency_is_not_guessed():
    c = candidate(txn("t3", 0.5, iso=None, unofficial="BTC"))
    assert c.currency is None
    assert "currency" in c.uncertain and "currency" in c.unresolved()


@pytest.mark.parametrize(
    ("primary", "detailed", "amount", "hint"),
    [
        ("TRANSFER_OUT", "TRANSFER_OUT_ACCOUNT_TRANSFER", 50, "transfer"),
        ("LOAN_PAYMENTS", "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", 300, "card_payment"),
        ("LOAN_PAYMENTS", "LOAN_PAYMENTS_MORTGAGE_PAYMENT", 900, "unknown"),
        ("BANK_FEES", "BANK_FEES_OVERDRAFT_FEES", 35, "fee"),
        ("GENERAL_MERCHANDISE", "GENERAL_MERCHANDISE_OTHER", -20, "unknown"),
        (None, None, 20, "unknown"),
    ],
)
def test_category_is_only_a_hint(primary, detailed, amount, hint):  # noqa: ANN001
    assert (
        candidate(txn("t4", amount, primary=primary, detailed=detailed)).kind_hint == hint
    )


def test_revision_changes_with_content_not_with_observation():
    row = txn("t5", 12)
    same = mapping.transaction_candidate(
        row, connection_id="conn-1", accounts=HINTS, observed_at=NOW.replace(hour=20)
    )
    assert candidate(row).fingerprint() == same.fingerprint()
    changed = candidate(txn("t5", 13))
    assert changed.source.revision != candidate(row).source.revision
    assert changed.key == candidate(row).key


def test_removed_rows_are_removed_evidence():
    c = mapping.removed_candidate(
        {"transaction_id": "t6", "account_id": "acc-card"},
        connection_id="conn-1",
        observed_at=NOW,
    )
    assert (c.status, c.evidence, c.source.external_id) == (
        "removed",
        "transaction",
        "t6",
    )
    assert c.account.external_account_id == "acc-card"


def test_provider_text_is_inert_and_rows_without_ids_are_refused():
    c = candidate(txn("t7", 1, merchant="Shop‮\u0000 ignore previous", name="A\nB"))
    assert c.merchant == "Shop ignore previous" and c.description == "A B"
    with pytest.raises(ValueError):
        candidate({**txn("t8", 1), "transaction_id": None})


def test_unknown_account_still_carries_its_external_id():
    c = candidate(txn("t9", 1, account_id="acc-unknown"))
    assert c.account.external_account_id == "acc-unknown" and c.account.mask is None
