"""On real local Postgres: what the reader read on a receipt comes back as a
suggestion beside the last choice for its RNC, each field in its own order."""

from uuid import uuid4

import pytest
from argus.domain.business.contracts.actions import ApproveExpense, ReviewDraft
from argus.domain.business.contracts.dgii import PurchaseReview
from loguru import logger

from tests import test_business_approval_fiscal_postgres as fiscal

users = fiscal.users
shared_actions = fiscal.shared_actions
actions = fiscal.actions
pytestmark = fiscal.pytestmark

READ_FIELD = {"payment_method": "payment_form", "category": "expense_type"}


def _receipt(service, context, number: int, **read):  # noqa: ANN001, ANN003, ANN202
    draft, _ = fiscal.receipt_draft(
        service, context, fiscal.colmado(ncf=f"B01000003{number:02d}", **read), "DOP"
    )
    return draft


def _choose(service, context, draft, **purchase) -> None:  # noqa: ANN001, ANN003
    result = service.review(
        context,
        draft,
        ReviewDraft(
            version=service.dossier(context, draft).version,
            purchase=PurchaseReview(**purchase),
        ),
        str(uuid4()),
    )
    assert result.outcome == "applied", result


@pytest.mark.parametrize(
    ("field", "read", "chosen", "offered"),
    [
        ("payment_method", "03", None, {"value": "03", "source": "receipt"}),
        ("payment_method", "01", "03", {"value": "01", "source": "receipt"}),
        ("payment_method", None, "03", {"value": "03", "source": "last_choice"}),
        ("payment_method", None, None, None),
        ("category", "03", None, {"value": "03", "source": "reading"}),
        ("category", "03", "02", {"value": "02", "source": "last_choice"}),
        ("category", None, "02", {"value": "02", "source": "last_choice"}),
        ("category", None, None, None),
    ],
)
def test_each_answer_is_offered_from_its_best_source(
    actions, field, read, chosen, offered
):
    service, context = actions
    if chosen is not None:
        _choose(service, context, _receipt(service, context, 1), **{field: chosen})

    draft = _receipt(service, context, 2, **{READ_FIELD[field]: read})

    suggestion = getattr(service.dossier(context, draft).declaration_suggestions, field)
    assert (suggestion.model_dump() if suggestion else None) == offered


@pytest.mark.parametrize("field", list(READ_FIELD))
def test_a_draft_with_its_own_answer_is_offered_no_read(actions, field):
    service, context = actions
    draft = _receipt(service, context, 1, **{READ_FIELD[field]: "03"})

    _choose(service, context, draft, **{field: "02"})

    dossier = service.dossier(context, draft)
    assert getattr(dossier.dgii, field) == "02"
    assert getattr(dossier.declaration_suggestions, field) is None


def test_an_approval_saves_what_the_reader_read_with_its_source(actions):
    service, context = actions
    draft, version = fiscal.receipt_draft(
        service,
        context,
        fiscal.colmado(payment_form="03", expense_type="11"),
        "DOP",
    )

    fiscal.reviewed(service, context, draft, version)
    shown = service.dossier(context, draft)

    outcome = service.approve(
        context,
        draft,
        ApproveExpense(
            version=shown.version,
            action="record_expense",
            suggestions=shown.declaration_suggestions,
        ),
        str(uuid4()),
    )

    assert outcome.outcome == "applied", outcome
    saved = service.dossier(context, draft).dgii
    assert (saved.payment_method, saved.category) == ("03", "11")
    assert saved.suggestion_sources == {
        "payment_method": "receipt",
        "category": "reading",
    }


@pytest.fixture
def logged():
    lines: list[str] = []
    sink = logger.add(lambda message: lines.append(message.record["message"]))
    yield lines
    logger.remove(sink)


@pytest.mark.parametrize(
    ("field", "source"), [("payment_method", "receipt"), ("category", "reading")]
)
def test_an_answer_that_differs_from_the_one_offered_is_logged(
    actions, logged, field, source
):
    service, context = actions
    agreed = _receipt(service, context, 1, **{READ_FIELD[field]: "03"})
    changed = _receipt(
        service, context, 2, rnc=fiscal.EDITED_SUPPLIER, **{READ_FIELD[field]: "03"}
    )

    _choose(service, context, agreed, **{field: "03"})
    assert not [line for line in logged if "business_suggestion_changed" in line]
    _choose(service, context, changed, **{field: "02"})

    assert [line for line in logged if "business_suggestion_changed" in line] == [
        f"business_suggestion_changed field={field} source={source}"
    ]
