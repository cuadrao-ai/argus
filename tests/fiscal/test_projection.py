from argus.domain.business.fiscal_sandbox.contracts import Observation
from argus.domain.business.fiscal_sandbox.projection import project


def test_acceptance_survives_late_processing_and_pdf_failure():
    state = project(
        [
            Observation(
                source="callback",
                processing="FINISHED",
                legal="ACCEPTED",
                pdf="available",
            ),
            Observation(source="response", processing="REGISTERED"),
            Observation(source="artifact", pdf="retrieval_failed"),
        ],
        contacted=True,
        identified=True,
    )
    assert state.processing == "FINISHED"
    assert state.legal == "ACCEPTED"
    assert state.pdf == "retrieval_failed"
    assert not state.needs_review


def test_first_terminal_is_sticky_and_contradiction_requires_review():
    state = project(
        [
            Observation(source="callback", legal="ACCEPTED"),
            Observation(source="poll", legal="REJECTED"),
        ],
        contacted=True,
        identified=True,
    )
    assert state.legal == "ACCEPTED"
    assert state.needs_review


def test_missing_identity_never_becomes_retryable():
    state = project(
        [Observation(source="unknown", code="contact_uncertain")],
        contacted=True,
        identified=False,
    )
    assert state.submission == "unknown"
    assert state.needs_review
