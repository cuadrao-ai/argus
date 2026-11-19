from __future__ import annotations

from unittest.mock import Mock

import pytest
from argus.llm.openrouter_key_policy import (
    MODEL_CREDENTIAL_ENV_NAMES,
    RETIRED_MODEL_CREDENTIAL_ENV_NAMES,
)

DEV, STG, PROD = MODEL_CREDENTIAL_ENV_NAMES


@pytest.fixture
def reached(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    from workflows import document_worker

    for name in (*MODEL_CREDENTIAL_ENV_NAMES, *RETIRED_MODEL_CREDENTIAL_ENV_NAMES):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(document_worker, "configure_logging", Mock())
    calls: list[str] = []

    async def stub_serve() -> None:
        calls.append("serve")

    monkeypatch.setattr(document_worker, "serve", stub_serve)
    return calls


def test_staging_document_worker_serves_with_only_the_staging_key(
    monkeypatch: pytest.MonkeyPatch, reached: list[str]
) -> None:
    from workflows import document_worker

    monkeypatch.setenv(STG, "synthetic-staging")

    document_worker.main()

    assert reached == ["serve"]


@pytest.mark.parametrize(
    ("present", "named"),
    [
        ({RETIRED_MODEL_CREDENTIAL_ENV_NAMES[1]: "synthetic-old"}, STG),
        ({STG: "synthetic-staging", PROD: "synthetic-production"}, PROD),
        ({STG: "synthetic-staging", DEV: "synthetic-local"}, DEV),
    ],
)
def test_staging_document_worker_refuses_to_start_with_another_environment_key(
    monkeypatch: pytest.MonkeyPatch,
    reached: list[str],
    present: dict[str, str],
    named: str,
) -> None:
    from workflows import document_worker

    for name, value in present.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match=named):
        document_worker.main()

    assert reached == []
