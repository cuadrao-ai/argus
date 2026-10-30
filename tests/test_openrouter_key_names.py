from __future__ import annotations

import pytest
from argus.llm.openrouter_key_policy import resolve_openrouter_api_key

_SECRET = "sentinel-openrouter-secret-9f3c2a"
_OTHER_KEYS = (
    "OPENROUTER_API_KEY",
    "CUADRAO_OPENROUTER_API_KEY_DEV",
    "CUADRAO_OPENROUTER_API_KEY_STG",
    "CUADRAO_OPENROUTER_API_KEY_PROD",
    "ARGUS_PROD_OPENROUTER_API_KEY",
    "ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY",
)


@pytest.mark.parametrize(
    ("app_env", "tried_names"),
    [
        (
            "production",
            (
                "CUADRAO_OPENROUTER_API_KEY_PROD",
                "ARGUS_PROD_OPENROUTER_API_KEY",
            ),
        ),
        (
            "staging",
            (
                "CUADRAO_OPENROUTER_API_KEY_STG",
                "ARGUS_PROD_OPENROUTER_API_KEY",
            ),
        ),
        ("preview", ("ARGUS_PROD_OPENROUTER_API_KEY",)),
    ],
)
def test_hosted_missing_key_error_lists_every_tried_name(
    monkeypatch: pytest.MonkeyPatch,
    app_env: str,
    tried_names: tuple[str, ...],
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    for name in _OTHER_KEYS:
        if name in tried_names:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, _SECRET)

    with pytest.raises(RuntimeError) as exc_info:
        resolve_openrouter_api_key("registered")

    message = str(exc_info.value)
    assert message == f"{', '.join(tried_names)} is required in hosted environments."
    assert _SECRET not in message


def test_provider_free_env_names_the_per_environment_openrouter_keys() -> None:
    from tests.conftest import PROVIDER_CREDENTIAL_ENV_VARS

    missing = {
        "CUADRAO_OPENROUTER_API_KEY_DEV",
        "CUADRAO_OPENROUTER_API_KEY_STG",
        "CUADRAO_OPENROUTER_API_KEY_PROD",
    } - set(PROVIDER_CREDENTIAL_ENV_VARS)
    assert missing == set()
