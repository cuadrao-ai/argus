from __future__ import annotations

from unittest.mock import Mock

import pytest


def test_hosted_document_worker_main_reaches_serve_without_guest_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from workflows import document_worker

    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("CUADRAO_PROD_OPENROUTER_API_KEY", "synthetic-registered")
    monkeypatch.delenv("CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(document_worker, "configure_logging", Mock())

    reached: list[str] = []

    async def stub_serve() -> None:
        reached.append("serve")

    monkeypatch.setattr(document_worker, "serve", stub_serve)

    document_worker.main()

    assert reached == ["serve"]


def test_hosted_resolve_registered_still_required_for_extraction_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.delenv("CUADRAO_PROD_OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("CUADRAO_OPENROUTER_API_KEY_STG", raising=False)

    from argus.llm.openrouter_key_policy import resolve_openrouter_api_key

    with pytest.raises(RuntimeError, match="CUADRAO_OPENROUTER_API_KEY_STG"):
        resolve_openrouter_api_key("registered")
