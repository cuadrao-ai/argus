from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from argus.domain.business.actions.declaration_links import (
    saved_declaration_links,
    written_declaration,
)
from argus.domain.business.actions.facts import patched_facts, reviewed_amount_facts
from argus.domain.business.actions.fiscal import reviewed_fiscal_facts
from argus.domain.business.amount_inheritance import (
    INHERITANCE,
    NO_SOURCES,
    LinkedSources,
    inherit_amounts,
    inheritance_overrides,
    inheritance_state,
    written_from,
)
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.amounts import AmountsPreview, AmountsPreviewRequest
from argus.domain.business.contracts.dgii import (
    DgiiDeclaration,
    FiscalInput,
    FiscalReview,
    PurchaseReview,
)
from argus.domain.business.contracts.facts import (
    BusinessFactPatch,
    BusinessFacts,
    BusinessResolution,
    InheritedValue,
    MontosReview,
)
from argus.domain.business.document_type import direction
from argus.domain.business.purchase_review import apply_purchase, net_amount
from argus.domain.business.review_flags import review_flags

_Sources = Callable[[BusinessFacts, DgiiDeclaration | None], LinkedSources]


@dataclass(frozen=True)
class DraftSources:
    """What a save and the dossier read beyond the draft, so a preview reads
    the same: ``review`` is what a review and the dossier show a declaration
    from, ``stored`` what a saved one follows."""

    review: _Sources
    stored: _Sources


def _fixed(linked: LinkedSources) -> DraftSources:
    return DraftSources(review=lambda *_: linked, stored=lambda *_: linked)


def previewed_links(
    resolution: BusinessResolution,
    request: AmountsPreviewRequest,
    after: BusinessFacts,
    sources: DraftSources,
) -> dict[str, InheritedValue]:
    """The links the dossier shows once the request's draft is saved: the
    write and save a revision runs, read as the dossier reads it. It saves
    nothing."""

    before = resolution.facts
    previous = resolution.fiscal_overrides
    form = direction(resolution.document_type).form
    declared = request.declaration
    overrides = None
    if declared is not None or request.override_inherited or request.restore_inherited:
        if not {*request.override_inherited, *request.restore_inherited} <= INHERITANCE.keys():
            raise ActionError("invalid_input", "business_amount_inheritance_invalid")
        if declared is not None and declared.form != form:
            raise ActionError("invalid_input", "fiscal_direction_unsupported")
        raw = resolution.dgii if resolution.dgii is not None and resolution.dgii.form == form else None
        _, declared, overrides = written_declaration(
            before, raw, lambda _: request.declaration, previous, resolution.bill_mark,
            sources.review(before, raw),
            written=request.override_inherited,
            restore=request.restore_inherited,
            amount_derived=raw is None or resolution.amount_derived,
            unsaved=raw is None,
        )
    venta = resolution.document_type == "venta"
    saved, overrides = saved_declaration_links(
        before, after, declared if declared is not None else resolution.dgii,
        previous, resolution.bill_mark, overrides, sources.stored,
        written=declared is not None,
        venta=venta,
        amount_derived=resolution.amount_derived,
    )
    bill_mark = None if venta else resolution.bill_mark
    shown = sources.review(after, saved)
    return inheritance_state(after, written_from(after, saved, overrides, bill_mark, shown), overrides, shown)


def preview_amounts(resolution: BusinessResolution, request: AmountsPreviewRequest, linked: LinkedSources = NO_SOURCES, sources: DraftSources | None = None) -> AmountsPreview:
    source_ids = (uuid4(),)  # Preview provenance exists only for this calculation.
    before = resolution.facts
    declaration = written_from(before, resolution.dgii, resolution.fiscal_overrides, resolution.bill_mark, linked)
    overrides = inheritance_overrides(before, declaration, None, resolution.fiscal_overrides, amount_derived=resolution.amount_derived, linked=linked)
    after = before
    if request.amount is not None:
        after = patched_facts(after, BusinessFactPatch(amount=request.amount), source_ids, origin="member_set")
    if request.itbis is not None:
        fiscal = before.fiscal
        after = reviewed_fiscal_facts(after, FiscalReview(
            fiscal=FiscalInput(rnc=fiscal.rnc.value if fiscal else None, ncf=(fiscal.ecf.value or fiscal.ncf.value) if fiscal else None, itbis=request.itbis.value),
            declaration=declaration or apply_purchase(None, PurchaseReview()),
        ), source_ids, "member_set")
    if request.net_amount is not None or request.legal_tip is not None:
        after = reviewed_amount_facts(after, MontosReview(net_amount=request.net_amount, legal_tip=request.legal_tip), source_ids, origin="member_set")
    declaration = inherit_amounts(after, declaration, overrides, linked)
    return AmountsPreview(
        net_amount=net_amount(after, declaration),
        mismatch=next((flag for flag in review_flags(after, declaration=declaration) if flag.code == "amounts_mismatch"), None),
        inheritance=previewed_links(resolution, request, after, sources or _fixed(linked)),
    )
