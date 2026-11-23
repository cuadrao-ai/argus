"""On real local Postgres: an approval's own revision starts from the
declaration its review showed, and the undo of a failed approval puts back
the declaration stored before it."""

from uuid import uuid4

import pytest
from argus.domain.business.contracts.actions import ApproveExpense
from argus.domain.business.contracts.dgii import PurchaseReview

from tests import test_business_approval_evidence_postgres as evidence
from tests import test_business_approval_fiscal_postgres as fiscal
from tests import test_business_first_fiscal_save_postgres as first
from tests import test_business_fiscal_links_postgres as links
from tests.business_accept_support import seen_gaps

users = fiscal.users
shared_actions = fiscal.shared_actions
actions = fiscal.actions
pytestmark = fiscal.pytestmark
REMEMBERED = {"category": "09", "payment_method": "01"}


def _approve(service, context, draft, shown):  # noqa: ANN001, ANN202
    """The accept the open dossier sends: its version, suggestions and gaps."""

    return service.approve(
        context,
        draft,
        ApproveExpense(
            version=shown.version,
            action="record_expense",
            suggestions=shown.declaration_suggestions,
            accept_gaps=seen_gaps(service, context, draft),
        ),
        str(uuid4()),
    )


@pytest.mark.parametrize(
    ("remembered", "changed"),
    [({}, set()), (REMEMBERED, set(REMEMBERED))],
    ids=["nothing suggested", "two suggestions taken"],
)
def test_an_approvals_revision_holds_only_what_the_approval_changed(  # noqa: ANN001
    actions, remembered, changed
):
    service, context = actions
    if remembered:
        links._remembered(service, context, **remembered)
    draft, shown = links._fresh(service, context)

    outcome = _approve(service, context, draft, shown)

    assert outcome.outcome == "applied", outcome
    approval = first._last_revision(service, context, draft)
    assert approval.before_dgii == shown.dgii
    assert first._changed(approval) == changed


@pytest.mark.parametrize(
    "saved", [None, {"payment_method": "04"}], ids=["none saved", "one saved"]
)
def test_a_failed_approval_puts_back_the_stored_declaration(actions, monkeypatch, saved):  # noqa: ANN001
    service, context = actions
    links._remembered(service, context, **REMEMBERED)
    draft, shown = links._fresh(service, context)
    if saved:
        links._review(service, context, draft, purchase=PurchaseReview(**saved))
        shown = service.dossier(context, draft)
    stored = fiscal.revisions(service, draft)[-1]["dgii"]
    assert (stored is None) == (saved is None)
    evidence.refuse_once(service, monkeypatch)

    failed = _approve(service, context, draft, shown)

    assert (failed.outcome, failed.code) == ("invalid_input", "activity_invalid")
    reopened = service.dossier(context, draft)
    filled, undone = reopened.history[-2:]
    # The approval's revision starts from a declaration either way, so the
    # undo cannot read what was stored from it.
    assert filled.before_dgii is not None
    assert filled.after_dgii.category == "09"
    assert (undone.version, fiscal.revisions(service, draft)[-1]["dgii"]) == (reopened.version, stored)
    assert reopened.dgii == shown.dgii
    assert reopened.declaration_suggestions == shown.declaration_suggestions
