"""The dossier's Bandeja standing with no database: for one draft it carries
the group, reason and label the receipt list gives the row, and every gap the
rule finds. The rule stays in ``bandeja_group`` and the row a draft gives its
receipt in ``receipts.draft_row``; nothing here restates either."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.api.business_drafts import draft_overlay
from argus.domain.business.actions import listos
from argus.domain.business.actions.dossier import bandeja_standing
from argus.domain.business.bandeja_group import (
    RULE,
    DraftStanding,
    group_of,
    listo_gaps,
    listo_reason,
)
from argus.domain.business.contracts.dossier import ReviewFlag
from argus.domain.business.contracts.facts import (
    BusinessResolution,
    ReadPurchase,
    Unknown,
)
from argus.domain.business.receipts import draft_row
from argus.domain.ingestion.receipt_review import duplicate_warning

from tests.business.test_bandeja_group import (
    FACTS,
    LISTO,
    OPEN_VIEW,
    known,
    with_facts,
    with_fiscal,
)

#: One draft per reason of the rule, each with that reason as its first gap.
GAPS: dict[str, DraftStanding] = {
    "not_read": replace(LISTO, read="none"),
    "check_details": replace(LISTO, read="unclear"),
    "several_purchases": replace(LISTO, read_attention="several_purchases"),
    "no_purchase_found": replace(LISTO, read_attention="no_purchase_found"),
    "duplicate": replace(LISTO, repeated=True),
    "credit_note": replace(LISTO, credit_note=True),
    "missing_merchant": with_facts(counterparty=Unknown()),
    "missing_date": with_facts(occurred_on=Unknown()),
    "missing_amount": with_facts(amount=Unknown()),
    "missing_currency": with_facts(currency=Unknown()),
    "sin_comprobante": with_facts(receipt_state=known("no_receipt"), fiscal=None),
    "missing_rnc": with_fiscal(rnc=Unknown()),
    "invalid_rnc": with_fiscal(rnc=known("12345")),
    "missing_ncf": with_fiscal(ncf=Unknown()),
    "invalid_ncf": replace(
        LISTO, flags=(ReviewFlag(code="ncf_malformed", field="ncf", confirm=True),)
    ),
    "ecf_check_failed": replace(LISTO, ecf_failed=True),
    "missing_itbis": with_fiscal(itbis=Unknown()),
    "review_flag": replace(
        LISTO, flags=(ReviewFlag(code="itbis_high", field="itbis", confirm=False),)
    ),
    "blocked": replace(LISTO, blockers=("business_questions_unresolved",)),
    "unverified_sender": replace(LISTO, sender="new"),
}


#: What a read can leave on a draft, by the attention an open draft then says.
LEFT_BY_READ: dict[str | None, BusinessResolution] = {
    None: BusinessResolution(facts=FACTS),
    "several_purchases": BusinessResolution(
        facts=FACTS,
        read_purchases=(
            ReadPurchase(index=1, amount="245.00"),
            ReadPurchase(index=2, amount="95.00"),
        ),
    ),
    "no_purchase_found": BusinessResolution(
        facts=FACTS.model_copy(update={"amount": Unknown()}), read_total="340.00"
    ),
}


def _event(state: str, left: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        state=state,
        resolution={"business": LEFT_BY_READ[left].model_dump(mode="json")},
    )


def _standing(  # noqa: ANN202
    state: str,
    draft: DraftStanding | None,
    *,
    left: str | None = None,
    duplicate: bool = False,
    deleted: bool = False,
    reading: bool = False,
):
    return bandeja_standing(
        {
            **draft_row(_event(state, left), duplicate=duplicate),
            "deleted": deleted,
            "read_pending": reading,
        },
        draft,
        accepting=state == "accepting",
    )


def _open(draft: DraftStanding, **more: object):  # noqa: ANN202
    return _standing("open", draft, **more)


def _listed(view: dict, draft: DraftStanding | None, **more: object) -> dict:
    row = group_of(view, draft, **more)
    return {name: row[name] for name in ("group", "reason", "label")}


def test_the_table_covers_every_reason_of_the_rule() -> None:
    assert set(GAPS) == {gap.reason for gap in RULE}


@pytest.mark.parametrize("reason", GAPS)
def test_an_open_draft_carries_the_reason_the_list_gives_it(reason: str) -> None:
    draft = GAPS[reason]

    group, gaps = _open(draft)

    assert group.model_dump() == _listed(OPEN_VIEW, draft)
    assert (group.group, group.reason, group.label) == (
        "attention",
        reason,
        "needs_attention",
    )
    assert gaps == listo_gaps(draft)
    assert gaps[0] == reason


def test_a_draft_with_several_gaps_names_them_all_in_the_rules_order() -> None:
    draft = replace(
        with_facts(
            counterparty=Unknown(),
            fiscal=LISTO.facts.fiscal.model_copy(
                update={"ncf": Unknown(), "itbis": Unknown()}
            ),
        ),
        sender="new",
    )

    group, gaps = _open(draft)

    assert group.reason == "missing_merchant"
    assert gaps == (
        "missing_merchant",
        "missing_ncf",
        "missing_itbis",
        "unverified_sender",
    )
    assert gaps == listo_gaps(draft)


@pytest.fixture
def senders(monkeypatch):  # noqa: ANN001, ANN201
    """A database where every read is clean and every draft came by email from
    a sender nobody verified; the drafts whose sender was read."""

    asked: list[str] = []

    def sender(connection: object, space_id: str, draft_id: str) -> str:
        asked.append(draft_id)
        return "new"

    clean_read = {"status": "review_ready", "shared": False}
    for name, answer in {
        "review_questions": lambda tx, ids: {},
        "_attachments": lambda tx, ids: {draft_id: [clean_read] for draft_id in ids},
        "_upload_years": lambda tx, ids: {},
        "repeated_comprobantes": lambda tx, events: {},
        "record_context": lambda tx: SimpleNamespace(accounts=()),
        "rnc_registry": lambda tx: None,
        "review_flags": lambda *args, **more: (),
        "workflow_blockers": lambda *args: ([], ()),
        "email_draft_standing": sender,
    }.items():
        monkeypatch.setattr(listos, name, answer)
    return asked


def _read_standing(draft: DraftStanding, **more: object) -> DraftStanding:
    event = SimpleNamespace(
        id=str(uuid4()),
        state="open",
        version=draft.version,
        resolution={
            "business": BusinessResolution(facts=draft.facts).model_dump(mode="json")
        },
    )
    tx = SimpleNamespace(
        connection=None,
        context=SimpleNamespace(actor=SimpleNamespace(space_id=uuid4())),
    )
    return listos.draft_standings(tx, [event], **more)[event.id]


#: The reasons a draft's facts alone give, each read before the sender.
FACT_GAPS = (
    "missing_merchant",
    "missing_date",
    "missing_amount",
    "missing_currency",
    "missing_rnc",
    "invalid_rnc",
    "missing_ncf",
    "missing_itbis",
)


@pytest.mark.parametrize("reason", FACT_GAPS)
def test_the_dossier_names_an_unverified_sender_beside_another_gap(
    senders: list[str], reason: str
) -> None:
    standing = _read_standing(GAPS[reason], every_gap=True)

    group, gaps = _open(standing)

    assert group.reason == reason
    assert gaps == (reason, "unverified_sender")


@pytest.mark.parametrize("reason", FACT_GAPS)
def test_the_list_does_not_read_the_sender_of_a_draft_another_gap_keeps_out(
    senders: list[str], reason: str
) -> None:
    standing = _read_standing(GAPS[reason])

    assert listo_reason(standing) == reason
    assert senders == []


def test_the_list_reads_the_sender_of_a_draft_nothing_else_keeps_out(
    senders: list[str],
) -> None:
    standing = _read_standing(LISTO)

    assert listo_reason(standing) == "unverified_sender"
    assert len(senders) == 1


def test_a_draft_with_no_gap_is_ready_and_names_none() -> None:
    group, gaps = _open(LISTO)

    assert group.model_dump() == _listed(OPEN_VIEW, LISTO)
    assert (group.group, group.reason, group.label) == ("listo", None, "ready")
    assert gaps == ()


def test_an_accepted_record_is_labeled_accepted_and_names_no_gap() -> None:
    group, gaps = _standing("accepted", None)

    assert group.model_dump() == _listed({**OPEN_VIEW, "status": "confirmed"}, None)
    assert (group.group, group.reason, group.label) == (None, None, "accepted")
    assert gaps == ()


def test_an_accepted_record_with_purchases_left_unrecorded_stays_accepted() -> None:
    group, gaps = _standing("accepted", None, left="several_purchases")

    assert (group.group, group.reason, group.label) == (None, None, "accepted")
    assert gaps == ()


def test_a_draft_being_approved_is_ready() -> None:
    group, gaps = _standing("accepting", None)

    assert group.model_dump() == _listed(OPEN_VIEW, None, accepting=True)
    assert (group.group, group.label) == ("listo", "ready")
    assert gaps == ()


def test_a_deleted_or_dismissed_draft_has_no_label() -> None:
    deleted, _ = _standing("dismissed", None, deleted=True)
    dismissed, _ = _standing("dismissed", None)

    assert (deleted.group, deleted.reason, deleted.label) == ("eliminados", None, None)
    assert (dismissed.group, dismissed.reason, dismissed.label) == (None, None, None)


def test_a_draft_whose_receipt_is_being_read_waits_and_names_no_gap() -> None:
    group, gaps = _open(GAPS["missing_ncf"], reading=True)

    assert group.model_dump() == _listed(
        {**OPEN_VIEW, "read_pending": True}, GAPS["missing_ncf"]
    )
    assert (group.group, group.reason, group.label) == ("reading", "reading", "reading")
    assert gaps == ()


def test_a_repeat_shows_first_and_stays_among_the_gaps() -> None:
    draft = replace(
        with_fiscal(ncf=Unknown()), read="unclear", blockers=("possible_duplicate",)
    )

    group, gaps = _open(draft, duplicate=True)

    assert group.model_dump() == _listed({**OPEN_VIEW, "attention": "duplicate"}, draft)
    assert group.reason == "duplicate"
    assert gaps == ("check_details", "duplicate", "missing_ncf")


STATES = ("open", "accepting", "accepted", "dismissed")


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("left", LEFT_BY_READ)
@pytest.mark.parametrize("duplicate", [False, True])
def test_the_receipt_list_says_of_a_draft_what_the_dossier_reads(
    state: str, left: str | None, duplicate: bool
) -> None:
    event = _event(state, left)
    linked = {
        "id": uuid4(),
        "state": state,
        "version": 2,
        "attention": "possible_duplicate" if duplicate else None,
        "activity_id": None,
        "resolution": event.resolution,
        "marks": {},
    }

    listed = draft_overlay({"id": str(uuid4()), "status": "queued"}, [linked])

    assert {
        name: listed[name] for name in ("status", "attention", "error_code")
    } == draft_row(event, duplicate=duplicate)


@pytest.mark.parametrize(
    ("state", "left", "duplicate", "row"),
    [
        ("open", None, False, ("review_ready", None, None)),
        ("accepting", None, True, ("review_ready", None, None)),
        ("accepted", None, True, ("confirmed", None, None)),
        ("dismissed", None, True, ("dismissed", None, None)),
        (
            "open",
            "several_purchases",
            False,
            ("needs_attention", "several_purchases", "several_purchases_found"),
        ),
        (
            "open",
            "no_purchase_found",
            False,
            ("needs_attention", "no_purchase_found", "no_purchase_found"),
        ),
        (
            "accepted",
            "several_purchases",
            False,
            ("confirmed", "several_purchases", "purchases_unrecorded"),
        ),
        (
            "open",
            "several_purchases",
            True,
            ("needs_attention", "duplicate", "possible_duplicate"),
        ),
    ],
)
def test_a_draft_gives_its_receipt_row_one_status_attention_and_code(
    state: str, left: str | None, duplicate: bool, row: tuple
) -> None:
    found = draft_row(_event(state, left), duplicate=duplicate)

    assert (found["status"], found["attention"], found["error_code"]) == row


@pytest.mark.parametrize(
    ("attention", "named", "pending", "warned"),
    [
        (None, (), (), False),
        ("source_changed", ("other",), ("other",), False),
        ("ambiguous_match", ("other",), (), True),
        ("possible_duplicate", (), (), True),
        ("possible_duplicate", ("other",), ("other",), True),
        ("possible_duplicate", ("other",), (), False),
    ],
)
def test_a_duplicate_warning_is_settled_only_once_no_named_repeat_is_open(
    attention: str | None, named: tuple, pending: tuple, warned: bool
) -> None:
    assert duplicate_warning(attention, named, lambda: pending) is warned


@pytest.mark.parametrize(
    ("attention", "named"),
    [(None, ()), ("source_removed", ("other",)), ("possible_duplicate", ())],
)
def test_the_open_repeats_are_read_only_when_they_decide(
    attention: str | None, named: tuple
) -> None:
    def pending() -> tuple:
        raise AssertionError("read the open repeats")

    duplicate_warning(attention, named, pending)

