"""On real local Postgres: an approval saves the 606 suggestion the person
saw, with its source; a bulk approval saves the server's own; a saved answer
is never replaced; and a person's change drops the source."""

from uuid import uuid4

import pytest
from argus.domain.business.contracts.actions import ApproveExpense, ReviewDraft
from argus.domain.business.contracts.dgii import (
    DeclarationSuggestions,
    PurchaseReview,
)
from pydantic import ValidationError

from tests import test_business_approval_fiscal_postgres as fiscal
from tests.business_accept_support import seen_gaps

users = fiscal.users
shared_actions = fiscal.shared_actions
actions = fiscal.actions
pytestmark = fiscal.pytestmark
LAST = "last_choice"


def _receipt(service, context, number: int) -> tuple:  # noqa: ANN001
    """An unreviewed receipt of the one supplier, under its own comprobante."""

    read = fiscal.colmado(ncf=f"B01000003{number:02d}", total=f"{1180 + number}.00")
    return fiscal.receipt_draft(service, context, read, "DOP")


def _choose(service, context, draft, **purchase) -> int:  # noqa: ANN001, ANN003
    version = service.dossier(context, draft).version
    result = service.review(
        context,
        draft,
        ReviewDraft(version=version, purchase=PurchaseReview(**purchase)),
        str(uuid4()),
    )
    assert result.outcome == "applied", result
    return result.version


def _remembered(service, context, **purchase) -> None:  # noqa: ANN001, ANN003
    """A person answered for this supplier on an earlier receipt."""

    earlier, _ = _receipt(service, context, 1)
    _choose(service, context, earlier, **purchase)


def _ready(service, context, number: int) -> tuple:  # noqa: ANN001
    """A fresh receipt reviewed to approvable, and its dossier."""

    draft, version = _receipt(service, context, number)
    fiscal.reviewed(service, context, draft, version)
    return draft, service.dossier(context, draft)


def _approve(service, context, draft, version, suggestions=None):  # noqa: ANN001
    return service.approve(
        context,
        draft,
        ApproveExpense(
            version=version,
            action="record_expense",
            suggestions=suggestions,
            accept_gaps=seen_gaps(service, context, draft),
        ),
        str(uuid4()),
    )


def _saved(service, context, draft) -> tuple:  # noqa: ANN001
    declared = service.dossier(context, draft).dgii
    return declared.category, declared.payment_method, declared.suggestion_sources


def test_single_approval_saves_the_shown_values_with_their_source(actions):  # noqa: ANN001
    service, context = actions
    _remembered(service, context, category="02", payment_method="03")
    draft, shown = _ready(service, context, 2)
    assert shown.declaration_suggestions.model_dump() == {
        "category": {"value": "02", "source": LAST},
        "payment_method": {"value": "03", "source": LAST},
    }

    outcome = _approve(
        service, context, draft, shown.version, shown.declaration_suggestions
    )

    assert outcome.outcome == "applied", outcome
    assert _saved(service, context, draft) == (
        "02",
        "03",
        {"category": LAST, "payment_method": LAST},
    )
    approval = fiscal.revisions(service, draft)[-1]
    assert approval["dgii"]["suggestion_sources"] == {
        "category": LAST,
        "payment_method": LAST,
    }
    with service.authority.pool.connection() as db:
        actor = db.execute(
            "select actor->>'actor_id' from public.business_draft_revisions"
            " where draft_id=%s and version=%s",
            (draft, approval["version"]),
        ).fetchone()[0]
    assert actor == str(context.actor.actor_id)
    recorded = service.dossier(context, draft)
    assert recorded.declaration_suggestions == DeclarationSuggestions()


def test_the_reading_source_is_kept_like_any_other(actions):  # noqa: ANN001
    service, context = actions
    draft, shown = _ready(service, context, 2)
    assert shown.declaration_suggestions == DeclarationSuggestions()

    outcome = _approve(
        service,
        context,
        draft,
        shown.version,
        DeclarationSuggestions.model_validate(
            {"category": {"value": "05", "source": "reading"}}
        ),
    )

    assert outcome.outcome == "applied", outcome
    assert _saved(service, context, draft) == ("05", None, {"category": "reading"})


def test_an_approval_without_suggestions_saves_none(actions):  # noqa: ANN001
    service, context = actions
    _remembered(service, context, category="02", payment_method="03")
    draft, shown = _ready(service, context, 2)

    assert _approve(service, context, draft, shown.version).outcome == "applied"

    assert _saved(service, context, draft) == (None, None, {})
    recorded = service.dossier(context, draft)
    assert recorded.declaration_suggestions == DeclarationSuggestions()


def test_a_stale_version_is_refused_and_saves_nothing(actions):  # noqa: ANN001
    service, context = actions
    _remembered(service, context, category="02")
    draft, shown = _ready(service, context, 2)
    _choose(service, context, draft, category="04")

    outcome = _approve(
        service, context, draft, shown.version, shown.declaration_suggestions
    )

    assert (outcome.outcome, outcome.code) == ("stale_version", "stale_version")
    assert _saved(service, context, draft) == ("04", None, {})
    assert service.dossier(context, draft).review_state == "open"


def test_a_suggestion_for_an_answer_the_draft_has_is_refused(actions):  # noqa: ANN001
    service, context = actions
    _remembered(service, context, payment_method="03")
    draft, _ = _ready(service, context, 2)
    version = _choose(service, context, draft, payment_method="01")

    outcome = _approve(
        service,
        context,
        draft,
        version,
        DeclarationSuggestions.model_validate(
            {"payment_method": {"value": "03", "source": LAST}}
        ),
    )

    assert (outcome.outcome, outcome.code) == ("invalid_input", "suggestion_stale")
    assert _saved(service, context, draft) == (None, "01", {})
    assert service.dossier(context, draft).review_state == "open"


@pytest.mark.parametrize(
    "shown",
    [
        {"category": {"value": "12", "source": LAST}},
        {"payment_method": {"value": "08", "source": LAST}},
        {"category": {"value": "02", "source": "guess"}},
    ],
)
def test_an_invalid_code_or_source_is_no_request(shown):  # noqa: ANN001
    with pytest.raises(ValidationError):
        ApproveExpense.model_validate(
            {"version": 1, "action": "record_expense", "suggestions": shown}
        )


def test_a_person_changing_a_saved_answer_drops_only_its_source(actions):  # noqa: ANN001
    service, context = actions
    _remembered(service, context, category="02", payment_method="03")
    draft, shown = _ready(service, context, 2)
    _approve(service, context, draft, shown.version, shown.declaration_suggestions)

    _choose(service, context, draft, paid_on="2026-09-10")
    assert _saved(service, context, draft)[2] == {
        "category": LAST,
        "payment_method": LAST,
    }
    _choose(service, context, draft, payment_method="04")
    assert _saved(service, context, draft) == ("02", "04", {"category": LAST})
    _choose(service, context, draft, category="02")
    assert _saved(service, context, draft) == ("02", "04", {"category": LAST})
    _choose(service, context, draft, category="05")
    assert _saved(service, context, draft) == ("05", "04", {})


def test_an_unconfirmed_tipo_de_gasto_reads_blank_and_takes_the_suggestion(actions):  # noqa: ANN001
    service, context = actions
    draft, _ = _ready(service, context, 2)
    _choose(service, context, draft, category="09", category_suggested=True)
    legacy = service.dossier(context, draft)
    assert legacy.declaration_suggestions.category is None

    _remembered(service, context, category="02")
    shown = service.dossier(context, draft)
    assert shown.declaration_suggestions.category.value == "02"
    outcome = _approve(
        service, context, draft, shown.version, shown.declaration_suggestions
    )

    assert outcome.outcome == "applied", outcome
    declared = service.dossier(context, draft).dgii
    assert (declared.category, declared.category_suggested) == ("02", False)
    assert declared.suggestion_sources == {"category": LAST}


def test_the_606_line_carries_the_saved_codes(actions):  # noqa: ANN001
    service, context = actions
    _remembered(service, context, category="02", payment_method="03")
    draft, shown = _ready(service, context, 2)
    outcome = _approve(
        service, context, draft, shown.version, shown.declaration_suggestions
    )
    assert outcome.outcome == "applied", outcome

    lines, issues = fiscal.lines_606(service, context)

    assert issues == []
    [line] = lines
    cells = line.split("|")
    assert cells[:4] == [fiscal.SUPPLIER, "1", "02", "B0100000302"]
    assert "1002.00" in cells
    assert cells[-1] == "03"


def test_an_answer_left_blank_stays_out_of_the_606(actions):  # noqa: ANN001
    service, context = actions
    _remembered(service, context, category="02")
    draft, shown = _ready(service, context, 2)
    outcome = _approve(
        service, context, draft, shown.version, shown.declaration_suggestions
    )
    assert outcome.outcome == "applied", outcome

    lines, issues = fiscal.lines_606(service, context)

    assert lines == []
    required = {
        issue["field"]
        for issue in issues
        if issue["code"] == "fiscal_fact_required"
        and issue["activity_id"] == str(outcome.activity_id)
    }
    assert required == {"payment_method"}
