import pytest
from argus.domain.ingestion.whatsapp.ai_consent import (
    ConsentError,
    require_link_disclosure,
)

from tests.ingestion.whatsapp_link_support import NOTICE


@pytest.mark.parametrize(
    ("language", "text"), [("es-419", ""), ("es-419", NOTICE + " "), ("en", NOTICE)]
)
def test_link_refuses_a_missing_changed_or_wrong_language_notice(
    language: str, text: str
) -> None:
    with pytest.raises(ConsentError, match="whatsapp_consent_disclosure_stale") as error:
        require_link_disclosure(language, text)
    assert error.value.status == 409
