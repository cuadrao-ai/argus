from datetime import datetime, timezone

import pytest
from argus.domain.business.reporting_query import ReportRequest, run_query

from tests.business.test_business_reporting_query import IDENTITY, record


@pytest.mark.parametrize("enabled,expected", [(False, 2), (True, 1)])
def test_fiscal_overview_switch_preserves_period_only_legacy_count(enabled, expected):
    rows = [
        record("matching", stage="needs_fiscal_data", counterparty="Taller"),
        record("outside-search", stage="needs_fiscal_data", counterparty="Colmado"),
        record("ready", stage="ready_for_export", counterparty="Taller"),
    ]
    answer = run_query(
        IDENTITY,
        rows,
        ReportRequest(filters={"q": "Taller"}),
        datetime(2026, 10, 31, tzinfo=timezone.utc),
        registros_summary_v2_enabled=enabled,
    )
    assert answer.overview.needs_fiscal_data == expected
    assert answer.matching_count == 2


@pytest.mark.parametrize("enabled", [False, True])
def test_complete_answers_match_pinned_integration_and_approved_branch(enabled):
    import json
    from pathlib import Path

    from argus.domain.business.reporting_query import ReportRecord

    fixture = json.loads(
        (Path(__file__).parent / "fixtures/registros_summary_switch.json").read_text()
    )
    rows = [ReportRecord.model_validate(row) for row in fixture["records"]]
    observed_at = datetime.fromisoformat(fixture["observed_at"])
    for case in fixture["cases"]:
        actual = run_query(
            IDENTITY, rows, ReportRequest.model_validate(case["request"]), observed_at,
            registros_summary_v2_enabled=enabled,
        )
        assert actual.model_dump(mode="json") == case["on" if enabled else "off"]


@pytest.mark.parametrize("value,expected", [(None, False), ("", False), ("false", False), ("bad", False), ("true", True), ("1", True)])
def test_registros_summary_setting_is_server_owned_and_default_off(monkeypatch, value, expected):
    from argus.domain.business.config import registros_summary_v2_enabled

    monkeypatch.delenv("CUADRAO_REGISTROS_SUMMARY_V2_ENABLED", raising=False)
    monkeypatch.setenv("NEXT_PUBLIC_CUADRAO_REGISTROS_SUMMARY_V2_ENABLED", "true")
    if value is not None:
        monkeypatch.setenv("CUADRAO_REGISTROS_SUMMARY_V2_ENABLED", value)
    assert registros_summary_v2_enabled() is expected


def test_registros_summary_declarations_are_off_for_both_hosted_environments():
    import json
    from pathlib import Path

    import yaml

    root = Path(__file__).parents[2]
    name = "CUADRAO_REGISTROS_SUMMARY_V2_ENABLED"
    manifest = json.loads((root / "scripts/ops/staging_env_manifest.json").read_text())
    entry = next(item for item in manifest["services"]["api"]["entries"] if item["name"] == name)
    assert entry["value"] == entry["production"]["value"] == "false"
    assert f"{name}=false" in (root / ".env.example").read_text().splitlines()
    services = yaml.safe_load((root / "render.yaml").read_text())["services"]
    values = [item["value"] for service in services for item in service.get("envVars", []) if item["key"] == name]
    assert values == ["false", "false"]
