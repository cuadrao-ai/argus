import json

import pytest
from argus.domain.ingestion.whatsapp.ai_consent import (
    ConsentError,
    require_link_disclosure,
)

from tests.ingestion.whatsapp_link_support import ENGLISH_NOTICE, NOTICE
from tests.test_i18n_coverage import LOCALES_DIR


@pytest.mark.parametrize(("language", "notice"), [("en", ENGLISH_NOTICE), ("es-419", NOTICE)])
def test_link_accepts_the_exact_notice(language: str, notice: str) -> None:
    catalog = LOCALES_DIR / language / "common.json"
    displayed = json.loads(catalog.read_text())["settings"]["whatsapp"]["consent_notice"]
    assert displayed == notice
    require_link_disclosure(language, displayed)


@pytest.mark.parametrize(
    ("language", "text"), [("es-419", ""), ("es-419", NOTICE + " "), ("en", NOTICE)]
)
def test_link_refuses_a_missing_changed_or_wrong_language_notice(
    language: str, text: str
) -> None:
    with pytest.raises(ConsentError, match="whatsapp_consent_disclosure_stale") as error:
        require_link_disclosure(language, text)
    assert error.value.status == 409


def test_read_status_uses_the_approved_text_from_the_stored_link_receipt() -> None:
    from uuid import uuid4

    from argus.domain.ingestion.whatsapp.ai_consent import AIConsentStore, digest

    route = {"gateway": "fixture"}
    store = AIConsentStore(None, lambda: route)
    link = (uuid4(), b"s" * 32, "1234")
    row = {
        "id": uuid4(),
        "scope_version": 2,
        "disclosure": NOTICE,
        "route_hash": digest(route),
        "consented_at": None,
        "revoked_at": None,
    }
    assert store._view(link, row, route)["disclosure"] == NOTICE
    assert store._view(link, row, route)["enabled"]
    assert not store._view(link, {**row, "disclosure": NOTICE + " "}, route)["enabled"]
