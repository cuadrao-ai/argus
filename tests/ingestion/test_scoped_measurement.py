import ast
import hashlib
import json
import subprocess
from decimal import Decimal
from pathlib import Path

import httpx
from argus.domain.ingestion.documents.models import ExtractionBatch

from scripts.documents.scoped_measurement import (
    CONTEXT_TOKENS,
    DEFAULT_MANIFEST,
    REPO,
    load_fixtures,
    main,
    reservation_from_endpoints,
    score_checks,
)


def _batch(cost: str) -> ExtractionBatch:
    return ExtractionBatch(
        candidates=(),
        metadata={"route_receipts": [{"usage_cost_usd": cost}]},
    )


def _layout(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "root"
    evidence = root / "docs" / "reports" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "baseline.json").write_text(json.dumps({"cases": []}), encoding="utf-8")
    return root, evidence


def _entry(root: Path, fixture_id: str, body: bytes) -> dict:
    path = root / "fixtures" / f"{fixture_id}.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return {
        "id": fixture_id,
        "path": str(path.relative_to(root)),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def _manifest(root: Path, entries: list[dict], model: str = "fixture-model") -> Path:
    path = root / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "model": model,
                "retries": 0,
                "baseline_scorecard": "docs/reports/evidence/baseline.json",
                "fixtures": entries,
            }
        ),
        encoding="utf-8",
    )
    return path


def _run(
    monkeypatch, root, evidence, manifest_path, name, extract, endpoints, key="test-key"
):
    if key is None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    else:
        monkeypatch.setenv("OPENROUTER_API_KEY", key)
    monkeypatch.delenv("APP_ENV", raising=False)
    output = evidence / name
    code = main(
        [
            "--manifest",
            str(manifest_path),
            "--output",
            str(output),
            "--evidence-root",
            str(evidence),
        ],
        fixture_root=root,
        extract=extract,
        fetch_endpoints=endpoints,
    )
    return code, output


def _rate(numerator: str) -> str:
    return format(Decimal(numerator) / Decimal(CONTEXT_TOKENS), "f")


def test_reservation_prices_the_full_window_at_the_higher_rate():
    higher = reservation_from_endpoints(
        [
            {
                "pricing": {
                    "prompt": "0.000000001",
                    "image": "0.000000003",
                    "input_cache_read": "0.000000002",
                    "completion": "0.000000001",
                    "internal_reasoning": "0.000000004",
                }
            }
        ]
    )
    assert higher.usd == Decimal("0.003193728")

    approved = reservation_from_endpoints(
        [
            {
                "pricing": {
                    "prompt": "0.000000825",
                    "image": "0.000000825",
                    "completion": "0.000004125",
                    "internal_reasoning": "0.000004125",
                }
            },
            {"pricing": {"prompt": "0.000000001", "completion": "0.000000001"}},
        ]
    )
    assert approved.usd == Decimal("0.9145752")
    assert approved.usd * 3 == Decimal("2.7437256")


def test_cap_refusal_keeps_spent_plus_reservation_inside_five_dollars(
    tmp_path, monkeypatch, capsys
):
    root, evidence = _layout(tmp_path)
    first, second = (
        _entry(root, "one", b"one"),
        _entry(root, "two", b"two"),
    )
    received = []

    def extract(fixture, model):
        received.append((fixture.id, model))
        return _batch("3")

    def expensive(_model):
        return [{"pricing": {"prompt": "1", "completion": "0"}}]

    code, output = _run(
        monkeypatch,
        root,
        evidence,
        _manifest(root, [first]),
        "over.json",
        extract,
        expensive,
    )
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == "spend_cap\n"
    assert captured.out == ""
    assert not output.exists()
    assert received == []

    def exact_three(_model):
        return [{"pricing": {"prompt": _rate("3"), "completion": "0"}}]

    code, output = _run(
        monkeypatch,
        root,
        evidence,
        _manifest(root, [first, second]),
        "partial.json",
        extract,
        exact_three,
    )
    scorecard = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert code == 1
    assert received == [("one", "fixture-model")]
    assert [case["fixture"] for case in scorecard["cases"]] == ["one"]
    assert scorecard["cases"][0]["usage"] == {"cost": "3"}
    assert scorecard["known_actual_cost_usd"] == "3"
    assert scorecard["stop_reason"] == "spend_cap"
    assert printed["known_actual_cost_usd"] == "3"

    def exact_five(_model):
        return [{"pricing": {"prompt": _rate("5"), "completion": "0"}}]

    def cheap_extract(fixture, model):
        received.append((fixture.id, model))
        return _batch("0.01")

    code, output = _run(
        monkeypatch,
        root,
        evidence,
        _manifest(root, [first]),
        "edge.json",
        cheap_extract,
        exact_five,
    )
    scorecard = json.loads(output.read_text(encoding="utf-8"))
    assert code == 1
    assert scorecard["cases"][0]["usage"] == {"cost": "0.01"}
    assert scorecard["stop_reason"] is None


def test_fourth_request_is_refused_and_a_second_run_does_not_repeat_it(
    tmp_path, monkeypatch, capsys
):
    root, evidence = _layout(tmp_path)
    entries = [_entry(root, name, name.encode()) for name in ("a", "b", "c", "d")]
    received = []
    priced = []

    def extract(fixture, model):
        received.append(fixture.id)
        return _batch("0.01")

    def endpoints(model):
        priced.append(model)
        return [{"pricing": {"prompt": _rate("0.02"), "completion": "0"}}]

    code, output = _run(
        monkeypatch,
        root,
        evidence,
        _manifest(root, entries),
        "scorecard.json",
        extract,
        endpoints,
    )
    scorecard = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert code == 1
    assert received == ["a", "b", "c"]
    assert [case["fixture"] for case in scorecard["cases"]] == ["a", "b", "c"]
    assert [case["usage"]["cost"] for case in scorecard["cases"]] == [
        "0.01",
        "0.01",
        "0.01",
    ]
    assert scorecard["known_actual_cost_usd"] == "0.03"
    assert scorecard["stop_reason"] == "call_limit"
    assert scorecard["scope"] == "document_extraction"
    assert scorecard["model"] == "fixture-model"
    assert scorecard["profile"] == {
        "max_tokens": 12000,
        "timeout_seconds": 90,
        "max_retries": 0,
    }
    assert scorecard["privacy"] == {
        "require_parameters": True,
        "data_collection": "deny",
        "zdr": True,
        "allow_fallbacks": False,
    }
    assert set(scorecard["surface"]) == {
        "src/argus/domain/ingestion/documents/extractor.py",
        "src/argus/domain/ingestion/documents/models.py",
    }
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
    ).strip()
    assert scorecard["candidate_sha"] == head
    assert printed["totals"] == {"failed": 3, "passed": 0, "unavailable": 0}
    assert printed["known_actual_cost_usd"] == "0.03"

    saved = output.read_bytes()
    code, _ = _run(
        monkeypatch,
        root,
        evidence,
        _manifest(root, entries),
        "scorecard.json",
        extract,
        endpoints,
    )
    assert code == 1
    assert capsys.readouterr().err == "output_exists\n"
    assert received == ["a", "b", "c"]
    assert priced == ["fixture-model"]
    assert output.read_bytes() == saved


def test_provider_failure_is_not_retried(tmp_path, monkeypatch, capsys):
    root, evidence = _layout(tmp_path)
    entries = [_entry(root, "one", b"one"), _entry(root, "two", b"two")]
    received = []

    def extract(fixture, _model):
        received.append(fixture.id)
        if len(received) == 1:
            raise RuntimeError("down")
        return _batch("0.01")

    def endpoints(_model):
        return [{"pricing": {"prompt": "0.0000000001", "completion": "0.0000000001"}}]

    code, output = _run(
        monkeypatch,
        root,
        evidence,
        _manifest(root, entries),
        "failed.json",
        extract,
        endpoints,
    )
    scorecard = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert code == 1
    assert received == ["one"]
    assert scorecard["cases"] == [
        {
            "fixture": "one",
            "fixture_sha256": entries[0]["sha256"],
            "status": "unavailable",
            "checks": {},
            "usage": None,
            "actual_cost_usd": None,
        }
    ]
    assert scorecard["known_actual_cost_usd"] == "0"
    assert scorecard["stop_reason"] == "provider_failed"
    assert printed["totals"] == {"failed": 0, "passed": 0, "unavailable": 1}


def test_provider_http_error_records_status_message_and_code(
    tmp_path, monkeypatch, capsys
):
    root, evidence = _layout(tmp_path)
    entry = _entry(root, "one", b"one")
    received = []

    def extract(fixture, _model):
        received.append(fixture.id)
        request = httpx.Request(
            "POST",
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": "Bearer super-secret-key"},
        )
        response = httpx.Response(
            402,
            json={
                "error": {
                    "message": "Insufficient credits",
                    "code": 402,
                }
            },
            request=request,
        )
        raise httpx.HTTPStatusError("payment", request=request, response=response)

    def endpoints(_model):
        return [{"pricing": {"prompt": "0.0000000001", "completion": "0.0000000001"}}]

    code, output = _run(
        monkeypatch,
        root,
        evidence,
        _manifest(root, [entry]),
        "http.json",
        extract,
        endpoints,
        key="super-secret-key",
    )
    scorecard = json.loads(output.read_text(encoding="utf-8"))
    text = output.read_text(encoding="utf-8")
    assert code == 1
    assert received == ["one"]
    assert scorecard["stop_reason"] == "provider_failed"
    assert scorecard["cases"][0]["provider_error"] == {
        "http_status": 402,
        "message": "Insufficient credits",
        "code": 402,
    }
    assert "super-secret-key" not in text
    assert "Authorization" not in text
    assert capsys.readouterr().err == ""


def test_missing_key_fails_closed_before_a_request(tmp_path, monkeypatch, capsys):
    root, evidence = _layout(tmp_path)
    entry = _entry(root, "one", b"one")
    manifest_path = _manifest(root, [entry])
    priced = []

    def endpoints(model):
        priced.append(model)
        return [{"pricing": {"prompt": "1", "completion": "0"}}]

    def extract(_fixture, _model):
        raise AssertionError("request")

    monkeypatch.setenv("ARGUS_PROD_OPENROUTER_API_KEY", "other-key")
    code, output = _run(
        monkeypatch,
        root,
        evidence,
        manifest_path,
        "missing.json",
        extract,
        endpoints,
        key=None,
    )
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == "missing_api_key\n"
    assert "other-key" not in captured.err
    assert not output.exists()
    assert priced == []

    code, output = _run(
        monkeypatch,
        root,
        evidence,
        manifest_path,
        "priced.json",
        extract,
        endpoints,
        key="present-key",
    )
    assert code == 1
    assert capsys.readouterr().err == "spend_cap\n"
    assert priced == ["fixture-model"]
    assert not output.exists()


def test_fixture_hash_mismatch_stops_before_a_request(tmp_path, monkeypatch, capsys):
    root, evidence = _layout(tmp_path)
    entry = _entry(root, "one", b"beta")
    entry["sha256"] = hashlib.sha256(b"alpha").hexdigest()
    (root / entry["path"]).write_bytes(b"not-the-hashed-bytes")
    manifest_path = _manifest(root, [entry])
    priced = []

    def endpoints(model):
        priced.append(model)
        return [{"pricing": {"prompt": "1", "completion": "0"}}]

    def extract(_fixture, _model):
        raise AssertionError("request")

    code, output = _run(
        monkeypatch,
        root,
        evidence,
        manifest_path,
        "hash.json",
        extract,
        endpoints,
        key="present-key",
    )
    assert code == 1
    assert capsys.readouterr().err == "fixture_checksum_mismatch\n"
    assert priced == []
    assert not output.exists()

    (root / entry["path"]).write_bytes(b"alpha")
    code, output = _run(
        monkeypatch,
        root,
        evidence,
        manifest_path,
        "hash.json",
        extract,
        endpoints,
        key=None,
    )
    assert code == 1
    assert capsys.readouterr().err == "missing_api_key\n"
    assert priced == []


def test_committed_manifest_matches_fixture_bytes_and_baseline_check_names():
    _manifest_body, fixtures = load_fixtures(DEFAULT_MANIFEST, REPO)
    assert [item.id for item in fixtures] == [
        "receipt-dop",
        "unreadable",
        "order-confirmation-estimated-tax",
    ]
    baseline = json.loads(
        (
            REPO
            / "docs/reports/evidence/cuadrao-receipt-extraction-20261011/live-measurement.json"
        ).read_text(encoding="utf-8")
    )
    empty = ExtractionBatch(candidates=())
    by_id = {item.id: item for item in fixtures}
    compared = 0
    for case in baseline["cases"]:
        checks = score_checks(by_id[case["fixture"]], empty, 0)
        assert set(checks) == set(case["checks"])
        compared += 1
    assert compared == 2


def test_runner_does_not_import_the_six_fixture_budget():
    tree = ast.parse((REPO / "scripts/documents/scoped_measurement.py").read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    assert "argus.llm.openrouter_tasks" in modules
    assert "argus.domain.ingestion.documents.models" in modules
    assert "scripts.documents.budget" not in modules
