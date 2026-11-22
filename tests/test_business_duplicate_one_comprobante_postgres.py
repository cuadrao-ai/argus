"""A repeat is two different problems. One supplier RNC and NCF is one
comprobante: approval refuses a second one, so the review offers only keeping
one and the copy is never Listo. Two receipts that look alike (merchant, date
and total) but carry different NCFs are a question: "different purchases" is
an answer, and then both approve and both reach the 606."""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from argus.api.business_drafts import receipt_summaries
from argus.api.business_receipt_activity import counts
from argus.domain.business.activity.queries import read_activity
from argus.domain.business.contracts.actions import (
    ApproveExpense,
    ApproveIncome,
    ResolveDuplicate,
    ReviewDraft,
)
from argus.domain.business.contracts.activity import ActivityFilters
from argus.domain.business.contracts.dgii import FiscalReview, SalesDeclaration
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.business.dgii_codes import TOOL_LABELS
from argus.domain.business.dgii_columns import COLUMNS
from argus.domain.business.dgii_export import fiscal_manifest
from argus.domain.business.fiscal_profile import set_profile
from argus.domain.business.reporting_file import RecordsExport, build_file
from argus.domain.business.reporting_query import ReportRequest
from argus.domain.business.reporting_store import read_export_source
from argus.domain.business.transactions import transaction
from faker import Faker
from psycopg.types.json import Jsonb

from tests import test_business_actions_postgres as shared
from tests import test_business_dgii_postgres as dgii
from tests import test_business_duplicate_resolution_postgres as resolution
from tests import test_business_receipt_views_postgres as views
from tests.business.receipt_stub import receipt_month
from tests.business_accept_support import seen_gaps
from tests.dgii.test_official_606_format import detail
from tests.dgii.test_packet import Packet
from tests.test_business_declaration_after_approval_postgres import (
    FILER,
    SUPPLIER,
    account_funding,
    blank_declaration,
)

users = shared.users
shared_actions = shared.actions
actions = dgii.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]


def _ncfs(count: int) -> list[str]:
    fake = Faker()
    return [f"B01{fake.unique.random_int(1, 99999999):08}" for _ in range(count)]


def _pair(actions):
    """Two prepared receipts with one merchant, date and total: the second
    carries the repeated-read warning that names the first."""

    service, context, _ = actions
    set_profile(service.authority, context, dgii.filer_change(FILER), str(uuid4()))
    first, second = _prepared(actions)
    account = dgii.cash_account(service, context)
    return first, second, account


def _prepared(actions, merchants=("Synthetic shop", "Synthetic shop")):
    """Two prepared receipts of one date and total from these merchants, each
    read finished clean. With one merchant the second warns of the first."""

    service, _, _ = actions
    drafts = []
    for merchant in merchants:
        receipt = resolution.receipts._receipt(
            actions, f"Synthetic {uuid4()}".encode(), merchant=merchant
        )
        resolution.preparation.bind(receipt)
        drafts.append(resolution.preparation.finish(receipt).draft_id)
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_source_connections set lease_until=null,"
            "lease_holder=null where lease_until is not null"
        )
        db.execute(
            "update public.financial_document_extractions d set"
            " draft=jsonb_set(d.draft, '{status}', '\"review_ready\"')"
            " from public.business_draft_sources l join public.business_sources s"
            " on s.id=l.source_id and s.space_id=l.space_id"
            " where s.connection_id=d.connection_id and l.draft_id=any(%s)",
            ([str(draft_id) for draft_id in drafts],),
        )
    return drafts


def _comprobante(
    service, context, draft_id, account, ncf: str, *, sale=False, rnc=SUPPLIER
) -> None:
    """Complete the purchase or sale with its fiscal number and declaration."""

    declaration = (
        {
            **{name: None for name in SalesDeclaration.model_fields},
            "form": "607",
            "id_type": "1",
            "income_type": "1",
            "billed_amount": "212.29",
            "cash": "250.50",
        }
        if sale
        else blank_declaration(category="02")
    )
    reviewed = service.review(
        context,
        draft_id,
        ReviewDraft(
            version=service.dossier(context, draft_id).version,
            document_type="venta" if sale else "recibo",
            facts=BusinessFactPatch.model_validate(
                {
                    name: {"state": "known", "value": value}
                    for name, value in {
                        "kind": "income" if sale else "expense",
                        "funding": account_funding(account),
                        "business_share": {"kind": "all"},
                        "receipt_state": "fiscal_receipt",
                    }.items()
                }
            ),
            dgii=FiscalReview.model_validate(
                {
                    "fiscal": {"rnc": rnc, "ncf": ncf, "itbis": "38.21"},
                    "declaration": declaration,
                }
            ),
        ),
        str(uuid4()),
    )
    assert reviewed.outcome == "applied", reviewed


def _decide(service, context, draft_id, other_id, decision: str, key=None):
    return service.resolve_duplicate(
        context,
        draft_id,
        ResolveDuplicate(
            version=service.dossier(context, draft_id).version,
            other_draft_id=other_id,
            other_version=service.dossier(context, other_id).version,
            decision=decision,
        ),
        key or str(uuid4()),
    )


def _approve(service, context, draft_id):
    dossier = service.dossier(context, draft_id)
    if dossier.facts.kind.value == "income":
        return service.approve_income(
            context,
            draft_id,
            ApproveIncome(
                version=dossier.version,
                action="record_income",
                accept_gaps=seen_gaps(service, context, draft_id),
            ),
            str(uuid4()),
        )
    return service.approve(
        context,
        draft_id,
        ApproveExpense(
            version=dossier.version,
            action="record_expense",
            accept_gaps=seen_gaps(service, context, draft_id),
        ),
        str(uuid4()),
    )


def _standings(service, context, *draft_ids):
    """The Bandeja rule's standing of each draft, by id."""

    from argus.domain.business.actions.listos import draft_standings

    with transaction(service.authority, context) as tx:
        events = [tx.imports.event(str(draft_id)) for draft_id in draft_ids]
        found = draft_standings(tx, events)
    return {draft_id: found[str(draft_id)] for draft_id in draft_ids}


def _listo(service, context, *draft_ids):
    from argus.domain.business.bandeja_group import listo_reason

    return {
        draft_id: listo_reason(standing)
        for draft_id, standing in _standings(service, context, *draft_ids).items()
    }


def _settled_before(service, context, draft_id, other_id) -> None:
    """A different-purchases answer stored the way the decision writes it,
    as a draft may hold it from before the server refused one for a shared
    comprobante."""

    from argus.domain.business.actions.duplicate_resolution import (
        attachment_signature,
    )
    from argus.domain.business.duplicates import evidence_signature

    with transaction(service.authority, context) as tx:
        event = tx.imports.event(str(draft_id))
        other = tx.imports.event(str(other_id))
        entry = {
            str(other_id): {
                "self": evidence_signature(tx.imports, event),
                "other": evidence_signature(tx.imports, other),
                "source_self": attachment_signature(tx, str(draft_id)),
                "source_other": attachment_signature(tx, str(other_id)),
            }
        }
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_import_events set resolution ="
            " jsonb_set(resolution, '{different_purchases}', %s),"
            " possible_duplicates='{}', attention=null, attention_detail=null"
            " where id=%s",
            (Jsonb(entry), str(draft_id)),
        )


@pytest.mark.parametrize("sale", [False, True], ids=["purchase", "sale"])
def test_a_true_copy_is_dropped_and_the_original_kept(actions, sale):
    service, context, _ = actions
    first, second, account = _pair(actions)
    [ncf] = _ncfs(1)
    for draft_id in (first, second):
        _comprobante(service, context, draft_id, account, ncf, sale=sale)
    web = views._web(service, context)
    before = counts(web, receipt_summaries(web, "all"))
    original = service.dossier(context, first)
    decided = _decide(service, context, second, first, "same_purchase")
    assert decided.outcome == "applied", decided
    copy = service.dossier(context, second)
    assert copy.review_state == "dismissed"
    assert copy.deleted is not None and copy.deleted.reason == "duplicate"
    kept = service.dossier(context, first)
    assert (kept.review_state, kept.version) == ("open", original.version)
    assert kept.duplicate_candidates == ()
    after = counts(web, receipt_summaries(web, "all"))
    assert after["bandeja_eliminados_count"] == before["bandeja_eliminados_count"] + 1
    assert after["pending_review_count"] == before["pending_review_count"] - 1
    assert _approve(service, context, first).outcome == "applied"
    feed = read_activity(service.authority, context, limit=25, filters=ActivityFilters())
    [entry] = [item for item in feed.items if item.action == "resolve_duplicate"]
    assert entry.decision == "same_purchase"
    # The row names the person the Eliminados marker records.
    assert copy.deleted.actor.actor_id == context.actor.actor_id
    assert entry.actor is not None
    assert (entry.actor.kind, entry.actor.display_name) == (
        "member",
        copy.deleted.actor.display_name,
    )
    assert entry.object is not None and entry.object.id == second


def test_a_shared_rnc_and_ncf_is_one_comprobante_whatever_was_stored(actions):
    service, context, _ = actions
    first, second, account = _pair(actions)
    [ncf] = _ncfs(1)
    for draft_id in (first, second):
        _comprobante(service, context, draft_id, account, ncf)
    [candidate] = service.dossier(context, second).duplicate_candidates
    assert (candidate.draft_id, candidate.basis) == (first, "fiscal_number")
    assert candidate.decisions == ("same_purchase",)
    before = service.dossier(context, second).version
    refused = _decide(service, context, second, first, "different_purchase")
    assert (refused.outcome, refused.code) == (
        "invalid_input",
        "duplicate_same_comprobante",
    ), refused
    assert service.dossier(context, second).version == before
    _settled_before(service, context, second, first)
    for draft_id in (first, second):
        [stays] = service.dossier(context, draft_id).duplicate_candidates
        assert (stays.basis, stays.decisions) == ("fiscal_number", ("same_purchase",))
    standings = _standings(service, context, first, second)
    assert {draft_id: s.repeated for draft_id, s in standings.items()} == {
        first: True,
        second: True,
    }
    assert set(_listo(service, context, first, second).values()) == {"duplicate"}
    assert _approve(service, context, first).outcome == "applied"
    copy = _approve(service, context, second)
    assert (copy.outcome, copy.code) == ("invalid_input", "duplicate_comprobante")
    assert _listo(service, context, second) == {second: "duplicate"}


def test_a_look_alike_with_another_ncf_is_two_purchases_when_the_person_says_so(
    actions,
):
    service, context, _ = actions
    first, second, account = _pair(actions)
    for draft_id, ncf in zip((first, second), _ncfs(2), strict=True):
        _comprobante(service, context, draft_id, account, ncf)
    [candidate] = service.dossier(context, second).duplicate_candidates
    assert (candidate.basis, candidate.decisions) == (
        "read_facts",
        ("different_purchase", "same_purchase"),
    )
    assert _listo(service, context, second) == {second: "duplicate"}
    decided = _decide(service, context, second, first, "different_purchase")
    assert decided.outcome == "applied", decided
    assert _listo(service, context, first, second) == {first: None, second: None}
    for draft_id in (first, second):
        assert service.dossier(context, draft_id).duplicate_candidates == ()
        assert _approve(service, context, draft_id).outcome == "applied"


@pytest.mark.parametrize("sale", [False, True], ids=["purchase", "sale"])
@pytest.mark.parametrize(
    ("same_rnc", "same_ncf"), [(True, True), (True, False), (False, True)]
)
def test_readiness_and_approval_read_one_comprobante_identity(
    actions, sale, same_rnc, same_ncf
):
    """Approval refuses exactly the pairs readiness and review hold back."""

    service, context, _ = actions
    first, second, account = _pair(actions)
    one, other = _ncfs(2)
    _comprobante(service, context, first, account, one, sale=sale)
    _comprobante(
        service,
        context,
        second,
        account,
        one if same_ncf else other,
        sale=sale,
        rnc=SUPPLIER if same_rnc else "199990048",
    )
    same = same_ncf and (sale or same_rnc)
    if not same:
        assert (
            _decide(service, context, second, first, "different_purchase").outcome
            == "applied"
        )
    else:
        _settled_before(service, context, second, first)
    assert _approve(service, context, first).outcome == "applied"
    held = _standings(service, context, second)[second].repeated
    offered = {
        (c.draft_id, c.basis)
        for c in service.dossier(context, second).duplicate_candidates
    }
    approval = _approve(service, context, second)
    refused = approval.outcome == "invalid_input" and approval.code == (
        "fiscal_duplicate_document" if sale else "duplicate_comprobante"
    )
    assert refused == held == ((first, "fiscal_number") in offered)
    assert refused is same
    if same:
        assert _listo(service, context, second) == {second: "duplicate"}
        [candidate] = service.dossier(context, second).duplicate_candidates
        assert candidate.decisions == ("same_purchase",)
        decision = _decide(service, context, second, first, "different_purchase")
        assert (decision.outcome, decision.code) == (
            "invalid_input",
            "duplicate_same_comprobante",
        )


# The 606 fields the DGII tool reads as text; every other filled one is an amount.
_TEXT = frozenset({"rnc", "id_type", "ncf", "modified_ncf", "income_withholding_type"})


def _official(file_row: list[str]) -> list[str]:
    """One row of the exported 606 file as the 23 fields of the DGII tool: the
    file splits each date into AAAAMM and DD and names each code by its label."""

    codes = {
        field: {label: code for code, label in labels.items()}
        for field, labels in TOOL_LABELS.items()
    }
    cells = iter(file_row)
    fields = []
    for name, _ in COLUMNS["606"]:
        value = next(cells)
        if name in ("occurred_on", "paid_on"):
            value += next(cells)
        elif name in codes and value:
            value = codes[name][value]
        elif value and name not in _TEXT:
            value = f"{Decimal(value):.2f}"
        fields.append(value)
    assert next(cells, None) is None
    return fields


def test_two_purchases_reach_the_606_and_one_comprobante_reaches_it_once(actions):
    service, context, _ = actions
    first, second, account = _pair(actions)
    one, two = _ncfs(2)
    _comprobante(service, context, first, account, one)
    _comprobante(service, context, second, account, two)
    assert _decide(service, context, second, first, "different_purchase").outcome == (
        "applied"
    )
    approved = {}
    for draft_id in (first, second):
        outcome = _approve(service, context, draft_id)
        assert outcome.outcome == "applied", outcome
        approved[draft_id] = str(outcome.activity_id)
    # Read apart, so only the comprobante ties them.
    original, copy = _prepared(actions, ("Tienda uno", "Tienda dos"))
    [shared_ncf] = _ncfs(1)
    for draft_id in (copy, original):
        _comprobante(service, context, draft_id, account, shared_ncf)
    kept = _approve(service, context, original)
    assert kept.outcome == "applied", kept
    approved[original] = str(kept.activity_id)
    refused = _approve(service, context, copy)
    assert (refused.outcome, refused.code) == ("invalid_input", "duplicate_comprobante")

    start, end = receipt_month()
    source = read_export_source(service.authority, context)
    request = ReportRequest(
        filters={
            "record_families": ["purchase"],
            "period": {
                "kind": "custom",
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
            },
        }
    )
    exported = build_file(source, RecordsExport(report=request, mode="dgii", format="csv"))
    _, *lines = csv.reader(io.StringIO(exported.content.decode("utf-8-sig")))
    rows = [_official(line) for line in lines]
    assert sorted(row[3] for row in rows) == sorted((one, two, shared_ncf))
    # The DGII format check, one record at a time, on each exported row.
    by_ncf = {row[3]: row for row in rows}
    for activity_id in approved.values():
        record = source.approved[activity_id]
        checked = detail(
            Packet(
                *fiscal_manifest(
                    (record,),
                    rnc=FILER,
                    business_name=dgii.PRACTICE_NAME,
                    start=start,
                    end=end,
                    captured_on=end + timedelta(days=1),
                )
            )
        )
        assert by_ncf[checked[3]] == checked
    assert [row[0] for row in rows] == [SUPPLIER] * 3
    assert UUID(approved[first]) != UUID(approved[second])
