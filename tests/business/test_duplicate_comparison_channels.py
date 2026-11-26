"""A compared document's file says where it arrived by the same rule as the
dossier's attachment sources: WhatsApp from the intake store, email from the
email queue, else the stored ``web``."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from argus.domain.business.contracts.dossier import (
    AttachmentSource,
    BusinessDossier,
    ComparedDocument,
    ComparedFile,
    DuplicateCandidate,
    DuplicateComparison,
)
from argus.domain.business.record_origin import UploadIntake, with_source_channels

NOW = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)


def _document(name: str) -> ComparedDocument:
    return ComparedDocument(
        draft_id=uuid4(),
        file=ComparedFile(
            connection_id=uuid4(),
            filename=name,
            media_type="image/png",
            channel="web",
            received_at=NOW,
        ),
        received_at=NOW,
        state="open",
    )


@pytest.fixture
def dossier() -> BusinessDossier:
    document, other = _document("nueva.png"), _document("vieja.png")
    attachment = AttachmentSource(
        id=uuid4(),
        channel="web",
        received_at=NOW,
        connection_id=document.file.connection_id,
        filename="nueva.png",
        media_type="image/png",
    )
    candidate = DuplicateCandidate(
        draft_id=other.draft_id,
        version=1,
        basis="read_facts",
        comparison=DuplicateComparison(document=document, other=other),
    )
    return BusinessDossier.model_construct(
        sources=(attachment,), duplicate_candidates=(candidate,)
    )


def _channels(dossier: BusinessDossier) -> tuple[str, str]:
    [candidate] = dossier.duplicate_candidates
    return (
        candidate.comparison.document.file.channel,
        candidate.comparison.other.file.channel,
    )


def test_a_compared_file_that_arrived_by_whatsapp_says_so(dossier) -> None:  # noqa: ANN001
    other = str(dossier.duplicate_candidates[0].comparison.other.file.connection_id)
    seen = with_source_channels(dossier, UploadIntake(frozenset({other}), {}))
    assert _channels(seen) == ("web", "whatsapp")
    assert [s.channel for s in seen.sources] == ["web"]


def test_a_compared_file_that_arrived_by_email_says_so(dossier) -> None:  # noqa: ANN001
    document = str(dossier.duplicate_candidates[0].comparison.document.file.connection_id)
    other = str(dossier.duplicate_candidates[0].comparison.other.file.connection_id)
    emails = {
            document: (("d1",), False, NOW - timedelta(minutes=1)),
            # The email came after the file was saved, so it is a repeat of a web upload.
            other: (("d2",), False, NOW + timedelta(minutes=1)),
    }
    seen = with_source_channels(dossier, UploadIntake(frozenset(), emails))
    assert _channels(seen) == ("email", "web")
    assert [s.channel for s in seen.sources] == ["email"]
