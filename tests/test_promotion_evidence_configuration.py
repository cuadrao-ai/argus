"""Free configuration regressions using committed release contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.promotion_evidence_configuration import (
    assert_release_configuration_matches,
    release_configuration_at_commit,
)
from tests.promotion_evidence_repository import (
    commit_files,
    commit_measured_repository,
    live_eval_scorecard,
    write_evidence,
)
from tests.release_promotion_evidence_support import (
    assert_main_promotion_live_eval_evidence,
)

PROFILE = ".github/private-alpha-release-profile.json"
ROOT = Path(__file__).resolve().parents[1]


def _profile() -> dict:
    return json.loads((ROOT / PROFILE).read_text())


def _configuration(profile: dict) -> dict[str, str]:
    return {
        key: value
        for key, value in profile["services"]["api"]["env"].items()
        if key.endswith("_MODEL") or value in {"true", "false"}
    }


def _measured(tmp_path: Path) -> tuple[str, dict, dict]:
    commit_measured_repository(tmp_path)
    profile = _profile()
    sha = commit_files(tmp_path, {PROFILE: json.dumps(profile)})
    scorecard = live_eval_scorecard(tmp_path, measured_sha=sha)
    scorecard["schema_version"] = 3
    scorecard["provenance"]["release_configuration"] = _configuration(profile)
    return sha, profile, scorecard


def _gate(tmp_path: Path, measured: str, candidate: str, scorecard: dict) -> None:
    relative = write_evidence(tmp_path, "candidate.json", scorecard)
    manifest = tmp_path / "new-main-production-promotion.md"
    manifest.write_text(
        f"- Candidate SHA: `{candidate}`\n"
        f"- Live eval measured SHA: `{measured}`\n"
        f"- Live eval scorecard: `{relative}`\n"
    )
    assert_main_promotion_live_eval_evidence(manifest, repository_root=tmp_path)


def _historical_configuration(tmp_path: Path, environment: dict[str, str]) -> str:
    commit_measured_repository(tmp_path)
    return commit_files(
        tmp_path,
        {PROFILE: json.dumps({"services": {"api": {"env": environment}}})},
    )


@pytest.mark.parametrize("contract_prefix", ["ARGUS", "CUADRAO"])
@pytest.mark.parametrize("receipt_prefix", ["ARGUS", "CUADRAO"])
def test_approved_configuration_renames_keep_historical_evidence(
    tmp_path: Path, contract_prefix: str, receipt_prefix: str
) -> None:
    configuration = {"CHAT_MODEL": "test/model", "ACCOUNT_DELETION_ENABLED": "false"}
    contract = {f"{contract_prefix}_{key}": value for key, value in configuration.items()}
    receipt = {f"{receipt_prefix}_{key}": value for key, value in configuration.items()}
    sha = _historical_configuration(tmp_path, contract)
    assert_release_configuration_matches(
        receipt, shipped_sha=sha, repository_root=tmp_path, evidence="historical"
    )
    assert release_configuration_at_commit(sha, repository_root=tmp_path) == contract
    assert receipt == {
        f"{receipt_prefix}_{key}": value for key, value in configuration.items()
    }


@pytest.mark.parametrize(
    ("suffix", "expected", "actual"),
    [
        ("CHAT_MODEL", "test/model", "wrong/model"),
        ("CHAT_MODEL", "test/model", " test/model "),
        ("ACCOUNT_DELETION_ENABLED", "false", "true"),
        ("ACCOUNT_DELETION_ENABLED", "false", "0"),
        ("ACCOUNT_DELETION_ENABLED", "false", None),
    ],
)
def test_approved_configuration_rename_preserves_exact_values(
    tmp_path: Path, suffix: str, expected: str, actual: str | None
) -> None:
    sha = _historical_configuration(tmp_path, {f"ARGUS_{suffix}": expected})
    with pytest.raises(AssertionError, match=suffix):
        assert_release_configuration_matches(
            {f"CUADRAO_{suffix}": actual},
            shipped_sha=sha,
            repository_root=tmp_path,
            evidence="historical",
        )


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_approved_configuration_rename_requires_exact_key_set(
    tmp_path: Path, change: str
) -> None:
    sha = _historical_configuration(tmp_path, {"ARGUS_CHAT_MODEL": "test/model"})
    receipt = {"CUADRAO_CHAT_MODEL": "test/model"}
    if change == "missing":
        receipt.clear()
    else:
        receipt["CUADRAO_ACCOUNT_DELETION_ENABLED"] = "false"
    with pytest.raises(AssertionError, match="release_configuration"):
        assert_release_configuration_matches(
            receipt, shipped_sha=sha, repository_root=tmp_path, evidence="historical"
        )


@pytest.mark.parametrize("side", ["contract", "receipt"])
@pytest.mark.parametrize("second_value", ["test/model", "wrong/model"])
def test_approved_configuration_rename_rejects_dual_keys(
    tmp_path: Path, side: str, second_value: str
) -> None:
    contract = {"ARGUS_CHAT_MODEL": "test/model"}
    receipt = {"CUADRAO_CHAT_MODEL": "test/model"}
    if side == "contract":
        contract["CUADRAO_CHAT_MODEL"] = second_value
    else:
        receipt["ARGUS_CHAT_MODEL"] = second_value
    sha = _historical_configuration(tmp_path, contract)
    with pytest.raises(AssertionError, match="duplicate.*CUADRAO_CHAT_MODEL"):
        assert_release_configuration_matches(
            receipt, shipped_sha=sha, repository_root=tmp_path, evidence="historical"
        )


@pytest.mark.parametrize(
    ("contract_key", "receipt_key"),
    [
        ("ARGUS_APP_ORIGIN", "CUADRAO_APP_ORIGIN"),
        ("ARGUS_UNAPPROVED_ENABLED", "CUADRAO_UNAPPROVED_ENABLED"),
        ("OTHER_CHAT_MODEL", "CUADRAO_CHAT_MODEL"),
    ],
)
def test_unapproved_configuration_names_are_not_aliases(
    tmp_path: Path, contract_key: str, receipt_key: str
) -> None:
    sha = _historical_configuration(tmp_path, {contract_key: "true"})
    with pytest.raises(AssertionError, match="release_configuration"):
        assert_release_configuration_matches(
            {receipt_key: "true"},
            shipped_sha=sha,
            repository_root=tmp_path,
            evidence="historical",
        )


def test_approved_configuration_rename_uses_shipped_git_object(tmp_path: Path) -> None:
    sha = _historical_configuration(tmp_path, {"ARGUS_CHAT_MODEL": "test/model"})
    current_profile = {"services": {"api": {"env": {"CUADRAO_CHAT_MODEL": "wrong/model"}}}}
    commit_files(tmp_path, {PROFILE: json.dumps(current_profile)})
    assert_release_configuration_matches(
        {"CUADRAO_CHAT_MODEL": "test/model"},
        shipped_sha=sha,
        repository_root=tmp_path,
        evidence="historical",
    )
    with pytest.raises(AssertionError, match="CHAT_MODEL"):
        assert_release_configuration_matches(
            {"CUADRAO_CHAT_MODEL": "wrong/model"},
            shipped_sha=sha,
            repository_root=tmp_path,
            evidence="historical",
        )


@pytest.mark.parametrize("key", sorted(_configuration(_profile())))
@pytest.mark.parametrize("changed_in", ["contract", "eval-environment"])
def test_model_or_flag_mismatch_fails_promotion(
    tmp_path: Path, key: str, changed_in: str
) -> None:
    measured, profile, scorecard = _measured(tmp_path)
    old = profile["services"]["api"]["env"][key]
    new = "false" if old == "true" else "true" if old == "false" else old + "-changed"
    if changed_in == "contract":
        profile["services"]["api"]["env"][key] = new
        candidate = commit_files(tmp_path, {PROFILE: json.dumps(profile)})
        # A later checkout agrees with the evidence, but the candidate does not.
        profile["services"]["api"]["env"][key] = old
        commit_files(tmp_path, {PROFILE: json.dumps(profile)})
    else:
        candidate = measured
        scorecard["provenance"]["release_configuration"][key] = new
    with pytest.raises(AssertionError, match=key) as error:
        _gate(tmp_path, measured, candidate, scorecard)
    assert old in str(error.value) and new in str(error.value)


@pytest.mark.parametrize(
    ("service", "key"),
    [
        ("api", "CUADRAO_RUNTIME_EVENT_TIMEOUT_SECONDS"),
        ("api", "ARGUS_RESEARCH_GLOBAL_DAILY_CEILING"),
        ("web", "NEXT_PUBLIC_RESEARCH_RAIL_ENABLED"),
        ("workflow", "ENABLE_MARKET_DATA_CACHE"),
    ],
)
def test_other_settings_keep_evidence(tmp_path: Path, service: str, key: str) -> None:
    measured, profile, scorecard = _measured(tmp_path)
    profile["services"][service]["env"][key] = "changed"
    candidate = commit_files(tmp_path, {PROFILE: json.dumps(profile)})
    _gate(tmp_path, measured, candidate, scorecard)


def test_new_promotion_refuses_older_scorecard(tmp_path: Path) -> None:
    measured, _, scorecard = _measured(tmp_path)
    scorecard["provenance"].pop("release_configuration")
    with pytest.raises(AssertionError, match="release_configuration"):
        _gate(tmp_path, measured, measured, scorecard)


@pytest.mark.parametrize("key", sorted(_configuration(_profile())))
def test_writer_records_environment_and_refuses_a_mid_run_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    from tests.evals import measurement_eval_scorecard as writer

    expected = _configuration(_profile())
    for name, value in expected.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("ARGUS_MARKET_DATA_PROVIDER_MODE", "synthetic_unit_fixture")
    monkeypatch.setenv("ARGUS_ASSET_PROVIDER_MODE", "synthetic_unit_fixture")
    monkeypatch.setattr(writer, "_worktree_is_clean", lambda _root: True)
    provenance = writer.build_scorecard_provenance(evaluation_mode="mocked")
    assert provenance.release_configuration == expected
    old = expected[key]
    new = "false" if old == "true" else "true" if old == "false" else old + "-changed"
    monkeypatch.setenv(key, new)
    with pytest.raises(ValueError, match="release_configuration_mismatch"):
        writer.write_scorecard([], provenance=provenance, output_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_capture_uses_runtime_model_resolution_and_keeps_missing_flags_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.llm.openrouter import resolve_openrouter_model

    from tests.evals import measurement_eval_scorecard as writer
    from tests.promotion_evidence_configuration import measured_release_configuration

    monkeypatch.setenv("CUADRAO_CHAT_MODEL", "  provider/model  ")
    monkeypatch.setenv("CUADRAO_CHAT_FALLBACK_MODEL", "  ")
    monkeypatch.setenv("ARGUS_MEMORY_EMBEDDING_MODEL", "  ")
    monkeypatch.delenv("CUADRAO_ACCOUNT_DELETION_ENABLED", raising=False)
    observed = measured_release_configuration(
        writer._candidate_sha(ROOT), repository_root=ROOT
    )
    assert observed["CUADRAO_CHAT_MODEL"] == resolve_openrouter_model()
    assert observed["CUADRAO_CHAT_FALLBACK_MODEL"] == resolve_openrouter_model(
        fallback=True
    )
    assert "ARGUS_MEMORY_EMBEDDING_MODEL" not in observed
    assert "ARGUS_RESEARCH_RAIL_ENABLED" not in observed
    assert observed["CUADRAO_ACCOUNT_DELETION_ENABLED"] is None


@pytest.mark.parametrize("change", ["added", "removed", "missing-value", "flag-alias"])
def test_configuration_requires_all_current_keys(tmp_path: Path, change: str) -> None:
    measured, profile, scorecard = _measured(tmp_path)
    key = "CUADRAO_ACCOUNT_DELETION_ENABLED"
    candidate = measured
    if change == "added":
        key = "ARGUS_NEW_CAPABILITY_ENABLED"
        profile["services"]["api"]["env"][key] = "true"
    elif change == "removed":
        del profile["services"]["api"]["env"][key]
    else:
        scorecard["provenance"]["release_configuration"][key] = (
            None if change == "missing-value" else "1"
        )
    if change in {"added", "removed"}:
        candidate = commit_files(tmp_path, {PROFILE: json.dumps(profile)})
    with pytest.raises(AssertionError, match=key):
        _gate(tmp_path, measured, candidate, scorecard)


@pytest.mark.parametrize("side", ["baseline", "candidate"])
def test_targeted_ab_uses_shared_configuration_check(tmp_path: Path, side: str) -> None:
    from tests.release_promotion_evidence_support import (
        assert_prose_failure_measured_on_both_sides,
    )

    sha, _, scorecard = _measured(tmp_path)
    paths = {}
    for name in ("baseline", "candidate"):
        provenance = dict(scorecard["provenance"])
        if name == side:
            provenance["release_configuration"] = {
                **provenance["release_configuration"],
                "CUADRAO_CHAT_MODEL": "wrong/model",
            }
        paths[name] = write_evidence(
            tmp_path,
            f"{name}.json",
            {
                "case_id": "case-a",
                "side": name,
                "provenance": provenance,
                "measurement": {"attempts": 10, "defect_count": 0},
            },
        )
    with pytest.raises(AssertionError, match="CUADRAO_CHAT_MODEL"):
        assert_prose_failure_measured_on_both_sides(
            " ".join(f"`{path}`" for path in paths.values()),
            tmp_path / "new-promotion.md",
            case_id="case-a",
            deployed_sha=sha,
            candidate_sha=sha,
            repository_root=tmp_path,
        )


def test_baseline_configuration_change_does_not_hide_new_failures(tmp_path: Path) -> None:
    from tests.release_promotion_evidence_support import (
        assert_main_promotion_baseline_comparison,
    )

    measured, profile, baseline = _measured(tmp_path)
    profile["services"]["api"]["env"]["CUADRAO_CHAT_MODEL"] += "-changed"
    candidate = commit_files(tmp_path, {PROFILE: json.dumps(profile)})
    relative = write_evidence(tmp_path, "baseline.json", baseline)
    manifest = (
        f"- Candidate SHA: `{candidate}`\n- Rollback target: `{measured}`\n"
        f"- Baseline eval scorecard: `{relative}`\n"
    )
    with pytest.raises(AssertionError, match="case-a passes on the deployed build"):
        assert_main_promotion_baseline_comparison(
            manifest,
            tmp_path / "new-promotion.md",
            candidate_results=[{"id": "case-a", "status": "failed"}],
            repository_root=tmp_path,
        )
    baseline["provenance"]["release_configuration"]["CUADRAO_CHAT_MODEL"] = "wrong/model"
    write_evidence(tmp_path, "baseline.json", baseline)
    with pytest.raises(AssertionError, match="CUADRAO_CHAT_MODEL"):
        assert_main_promotion_baseline_comparison(
            manifest,
            tmp_path / "new-promotion.md",
            candidate_results=[],
            repository_root=tmp_path,
        )


@pytest.mark.parametrize("key", ["CUADRAO_CHAT_MODEL", "CUADRAO_ACCOUNT_DELETION_ENABLED"])
def test_scorecard_records_a_disagreeing_environment_without_substituting_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    from tests.evals import measurement_eval_scorecard as writer

    for name, value in _configuration(_profile()).items():
        monkeypatch.setenv(name, value)
    expected = _configuration(_profile())[key]
    different = "wrong/model" if key.endswith("_MODEL") else str(expected != "true").lower()
    monkeypatch.setenv(key, different)
    monkeypatch.setenv("ARGUS_MARKET_DATA_PROVIDER_MODE", "synthetic_unit_fixture")
    monkeypatch.setenv("ARGUS_ASSET_PROVIDER_MODE", "synthetic_unit_fixture")
    monkeypatch.setattr(writer, "_worktree_is_clean", lambda _root: True)
    provenance = writer.build_scorecard_provenance(evaluation_mode="mocked")
    path = writer.write_scorecard([], provenance=provenance, output_dir=tmp_path)
    recorded = json.loads(path.read_text())
    assert recorded["schema_version"] == 3
    assert recorded["provenance"]["release_configuration"][key] == different
