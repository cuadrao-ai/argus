from __future__ import annotations

from unittest.mock import Mock

import pytest


def test_document_worker_main_skips_hosted_openrouter_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.llm import openrouter_key_policy

    from workflows import document_worker

    validate = Mock()
    run = Mock()
    monkeypatch.setattr(
        openrouter_key_policy,
        "validate_hosted_openrouter_configuration",
        validate,
    )
    monkeypatch.setattr(document_worker.asyncio, "run", run)

    document_worker.main()

    validate.assert_not_called()
    run.assert_called_once()


def test_hosted_resolve_registered_still_required_for_extraction_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.delenv("CUADRAO_PROD_OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("CUADRAO_OPENROUTER_API_KEY_STG", raising=False)

    from argus.llm.openrouter_key_policy import resolve_openrouter_api_key

    with pytest.raises(RuntimeError, match="CUADRAO_OPENROUTER_API_KEY_STG"):
        resolve_openrouter_api_key("registered")
