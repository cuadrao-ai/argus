"""Receipt fixtures that expect a purchase must name a paid status.

``ReceiptDetails.payment_status`` defaults to unknown. ``batch_from_result``
then withholds the transaction rows, so a fixture that omits the field yields
no candidate.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import ExtractionResult

ROOT = Path(__file__).resolve().parents[1]
MARKERS = {
    "merchant",
    "total",
    "items",
    "subtotal",
    "tax",
    "currency",
    "occurred_on",
    "ncf",
    "ecf",
    "rnc",
    "itbis",
}


@dataclass(frozen=True)
class ReceiptFixture:
    ref: str
    keys: frozenset[str]
    receipt: dict | None


def _unresolved(node: ast.AST, value: object) -> bool:
    return value is None and not isinstance(node, ast.Constant)


def _static(node: ast.AST, env: dict):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        return None
    if isinstance(node, (ast.List, ast.Tuple)):
        values = []
        for child in node.elts:
            item = _static(child, env)
            if _unresolved(child, item):
                return None
            values.append(item)
        return values
    if isinstance(node, ast.Dict) and all(key is not None for key in node.keys):
        found = {}
        for key, value in zip(node.keys, node.values, strict=False):
            name = _static(key, env)
            item = _static(value, env)
            if not isinstance(name, str) or _unresolved(value, item):
                return None
            found[name] = item
        return found
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
        and not node.args
        and all(keyword.arg is not None for keyword in node.keywords)
    ):
        found = {}
        for keyword in node.keywords:
            item = _static(keyword.value, env)
            if _unresolved(keyword.value, item):
                return None
            found[keyword.arg] = item
        return found
    return None


def _keys(node: ast.AST, env: dict) -> frozenset[str] | None:
    if isinstance(node, ast.Name) and isinstance(env.get(node.id), dict):
        return frozenset(env[node.id])
    if isinstance(node, ast.Dict):
        if any(key is None for key in node.keys):
            return None
        names = [_static(key, env) for key in node.keys]
        if not all(isinstance(name, str) for name in names):
            return None
        return frozenset(names)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
        and not node.args
    ):
        if any(keyword.arg is None for keyword in node.keywords):
            return None
        return frozenset(keyword.arg for keyword in node.keywords)
    return None


def _module_dicts(tree: ast.Module) -> dict:
    env: dict = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name):
            value = _static(node.value, env)
            if isinstance(value, dict):
                env[target.id] = value
    return env


def _expects_candidate(source: str, function: ast.AST) -> bool:
    segment = ast.get_source_segment(source, function) or ""
    if "len(batch.candidates) == 1" in segment or "for c in batch.candidates" in segment:
        return True
    return "ReceiptStub(" in segment and (
        "_landed_as(" in segment or '"prepared"' in segment
    )


def _called_names(function: ast.AST) -> set[str]:
    return {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def _receipt_nodes(function: ast.AST) -> list[tuple[int, ast.AST]]:
    found: list[tuple[int, ast.AST]] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id == "ReceiptStub" and len(node.args) >= 2:
            found.append((node.args[1].lineno, node.args[1]))
        for keyword in node.keywords:
            if keyword.arg == "details" and node.func.id == "ReceiptStub":
                found.append((keyword.value.lineno, keyword.value))
            if keyword.arg == "receipt":
                found.append((keyword.value.lineno, keyword.value))
        if (
            node.func.id == "model_validate"
            and node.args
            and isinstance(node.args[0], (ast.Dict, ast.Call))
        ):
            body = node.args[0]
            receipt = None
            if isinstance(body, ast.Dict):
                for key, value in zip(body.keys, body.values, strict=False):
                    if isinstance(key, ast.Constant) and key.value == "receipt":
                        receipt = value
            elif isinstance(body, ast.Call):
                for keyword in body.keywords:
                    if keyword.arg == "receipt":
                        receipt = keyword.value
            if receipt is not None:
                found.append((receipt.lineno, receipt))
    return found


def candidate_receipt_fixtures(root: Path = ROOT) -> list[ReceiptFixture]:
    fixtures: list[ReceiptFixture] = []
    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        env = _module_dicts(tree)
        functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        marked = {
            name for name, node in functions.items() if _expects_candidate(source, node)
        }
        for name in list(marked):
            marked.update(_called_names(functions[name]) & set(functions))
        rel = path.relative_to(root.parent)
        for name in sorted(marked):
            for line, node in _receipt_nodes(functions[name]):
                keys = _keys(node, env)
                if keys is None or not (keys & MARKERS):
                    continue
                value = _static(node, env)
                receipt = value if isinstance(value, dict) else None
                fixtures.append(ReceiptFixture(f"{rel}:{line}", keys, receipt))
    return fixtures


def _project(receipt: dict):
    total = receipt.get("total") or "1.00"
    occurred_on = receipt.get("occurred_on")
    result = ExtractionResult.model_validate(
        {
            "complete": True,
            "readable": True,
            "pages_read": [1],
            "observations": [
                {
                    "page": 1,
                    "row": 1,
                    "evidence": "transaction",
                    "status": "posted",
                    "amount": total,
                    "currency": receipt.get("currency") or "DOP",
                    "occurred_on": occurred_on,
                    "direction": "outflow",
                    "kind_hint": "expense",
                    "merchant": receipt.get("merchant"),
                }
            ],
            "receipt": receipt,
        }
    )
    return batch_from_result(
        result, "a" * 64, "fixture-guard", datetime.now(timezone.utc), 1
    )


class TestCandidateReceiptFixtures:
    def test_a_fixture_that_expects_a_candidate_names_paid_payment(self) -> None:
        failures = []
        seen = set()
        for fixture in candidate_receipt_fixtures():
            if fixture.ref in seen:
                continue
            seen.add(fixture.ref)
            if "payment_status" not in fixture.keys:
                if fixture.receipt is None:
                    failures.append(f"{fixture.ref} omits payment_status")
                    continue
                batch = _project(fixture.receipt)
                failures.append(
                    f"{fixture.ref} candidates={len(batch.candidates)} "
                    f"payment_status={batch.receipt.payment_status!r}"
                )
                continue
            if fixture.receipt is None:
                continue
            batch = _project(fixture.receipt)
            if (
                fixture.receipt.get("payment_status") != "paid"
                or len(batch.candidates) != 1
                or batch.issues
            ):
                failures.append(
                    f"{fixture.ref} candidates={len(batch.candidates)} "
                    f"payment_status={batch.receipt.payment_status!r} "
                    f"issues={[issue.code for issue in batch.issues]}"
                )
        assert failures == []
