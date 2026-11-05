import pytest
from argus.domain.ingestion.email_intake.config import EmailIntakeSettings


@pytest.mark.parametrize(
    "other_key",
    [
        "RESEND_API_KEY",
        "RESEND_MARKETING_API_KEY",
        "MARKETING_RESEND_API_KEY",
        "RESEND_ONBOARDING_API_KEY",
        "ONBOARDING_RESEND_API_KEY",
    ],
)
def test_email_intake_ignores_other_lane_credentials(monkeypatch, other_key):
    monkeypatch.delenv("RESEND_BUSINESS_API_KEY", raising=False)
    monkeypatch.setenv(other_key, "synthetic-other-lane-key")
    assert EmailIntakeSettings().api_key.get_secret_value() == ""


def test_email_intake_reads_only_business_key_and_hides_it(monkeypatch):
    monkeypatch.setenv("RESEND_BUSINESS_API_KEY", "synthetic-business-key")
    monkeypatch.setenv("RESEND_API_KEY", "synthetic-generic-key")
    monkeypatch.setenv("ARGUS_RESEND_WEBHOOK_SECRET", "whsec_c3ludGhldGljLXNlY3JldA==")
    settings = EmailIntakeSettings()
    assert settings.api_key.get_secret_value() == "synthetic-business-key"
    assert "synthetic-business-key" not in repr(settings)
    assert "c3ludGhldGlj" not in repr(settings)


def test_flags_default_off(monkeypatch):
    for key in (
        "ARGUS_BUSINESS_EMAIL_CAPTURE_ENABLED",
        "ARGUS_BUSINESS_EMAIL_INTAKE_ENABLED",
        "ARGUS_BUSINESS_EMAIL_DOMAIN",
    ):
        monkeypatch.delenv(key, raising=False)
    settings = EmailIntakeSettings()
    assert (
        settings.capture_enabled,
        settings.receiving_enabled,
        settings.receiving_domain,
    ) == (
        False,
        False,
        "",
    )


def test_daily_budget_defaults_and_explicit_cuadrao_limits(monkeypatch):
    monkeypatch.delenv("CUADRAO_BUSINESS_EMAIL_DAILY_MESSAGE_LIMIT", raising=False)
    monkeypatch.delenv("CUADRAO_BUSINESS_EMAIL_DAILY_BYTE_LIMIT", raising=False)
    assert EmailIntakeSettings().daily_budget.messages == 100
    assert EmailIntakeSettings().daily_budget.bytes == 104857600
    monkeypatch.setenv("CUADRAO_BUSINESS_EMAIL_DAILY_MESSAGE_LIMIT", "7")
    monkeypatch.setenv("CUADRAO_BUSINESS_EMAIL_DAILY_BYTE_LIMIT", "20971520")
    assert EmailIntakeSettings().daily_budget.messages == 7
    assert EmailIntakeSettings().daily_budget.bytes == 20971520


@pytest.mark.parametrize(
    "name,value", [("MESSAGE", "0"), ("BYTE", "10485759"), ("MESSAGE", "invalid")]
)
def test_daily_budget_settings_reject_unusable_limits(monkeypatch, name, value):
    from pydantic import ValidationError

    monkeypatch.setenv(f"CUADRAO_BUSINESS_EMAIL_DAILY_{name}_LIMIT", value)
    with pytest.raises(ValidationError):
        EmailIntakeSettings()
