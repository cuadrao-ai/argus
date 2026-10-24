"""The sole projector for every fiscal evidence source."""

from collections.abc import Sequence

from .contracts import FiscalState, Observation

_RANK = [
    "unreported",
    "REGISTERED",
    "TO_SEND",
    "WAITING_RESPONSE",
    "TO_NOTIFY",
    "FINISHED",
]


def project(
    observations: Sequence[Observation],
    *,
    contacted: bool,
    identified: bool,
    attempts: int = 0,
) -> FiscalState:
    processing, legal, xml, pdf = "unreported", "unreported", "unreported", "unreported"
    review = False
    unknown = False
    codes: list[str] = []
    for event in observations:
        if _RANK.index(event.processing) > _RANK.index(processing):
            processing = event.processing
        if event.legal != "unreported":
            if legal == "unreported":
                legal = event.legal
            elif legal != event.legal:
                review = True
        if event.xml != "unreported":
            xml = event.xml
        if event.pdf != "unreported":
            pdf = event.pdf
        if event.code and event.code not in codes:
            codes.append(event.code)
        review |= event.source == "conflict"
        unknown |= event.source == "unknown"
    submission = (
        "identified"
        if identified
        else (
            "unknown" if unknown or review else ("contacted" if contacted else "prepared")
        )
    )
    reconciliation = "not_needed"
    if contacted and (not identified or processing != "FINISHED"):
        reconciliation = "identity_missing" if not identified else "pending"
        if attempts >= 20:
            reconciliation = "exhausted"
    if review:
        reconciliation = "conflict"
    return FiscalState(
        submission=submission,
        processing=processing,
        legal=legal,
        xml=xml,
        pdf=pdf,
        reconciliation=reconciliation,
        diagnostics=tuple(codes[-16:]),
        needs_review=review
        or (contacted and not identified)
        or reconciliation == "exhausted",
    )
