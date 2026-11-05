"""Provisional local lifecycle scaffolding, not a product API or permission model."""

import hashlib
import json
import os
import re
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .extract import FIELDS, load_input


def field_issues(fields: dict) -> list[str]:
    issues = []
    try:
        value = fields.get("date", "")
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError("Date must be ISO")
    except (TypeError, ValueError):
        issues.append("date")
    try:
        raw = fields.get("amount", "")
        if not isinstance(raw, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", raw):
            raise ValueError("Amount must be explicit decimal text")
        amount = Decimal(raw)
        if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
            raise ValueError(
                "Amount must be positive finite money with at most two decimals"
            )
    except (InvalidOperation, ValueError):
        issues.append("amount")
    if fields.get("currency") not in ("DOP", "USD"):
        issues.append("currency")
    if fields.get("kind") not in ("expense", "refund", "income", "transfer"):
        issues.append("kind")
    for key in ("account", "description", "source_id"):
        if not isinstance(fields.get(key), str) or not fields[key].strip():
            issues.append(key)
    if fields.get("destination") not in ("personal", "household"):
        issues.append("destination")
    return issues


def _signature(fields: dict) -> tuple:
    return tuple(
        fields.get(key)
        for key in ("date", "description", "amount", "currency", "kind", "account")
    )


class Harness:
    """Single-process local JSON persistence with explicit simulated decisions."""

    def __init__(self, state_path: Path):
        self.state_path = Path(state_path)
        self.state = (
            json.loads(self.state_path.read_text())
            if self.state_path.exists()
            else {
                "format": "synthetic-test-scaffolding-v1",
                "proposals": {},
                "records": {},
                "imports": [],
            }
        )
        if self.state.get("format") != "synthetic-test-scaffolding-v1":
            raise ValueError("Not a harness state file")
        self.proposals = self.state["proposals"]
        self.records = self.state["records"]
        self._committed = deepcopy(self.state)

    def _save(self):
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n")
            os.replace(temporary, self.state_path)
        except (OSError, TypeError, ValueError):
            self.state = deepcopy(self._committed)
            self.proposals = self.state["proposals"]
            self.records = self.state["records"]
            raise
        self._committed = deepcopy(self.state)

    def _issues(self, proposal: dict) -> list[str]:
        issues = field_issues(proposal["fields"])
        if not proposal.get("overlap_reviewed"):
            for other in self.proposals.values():
                if other["id"] == proposal["id"] or other["status"] == "rejected":
                    continue
                if other["source_ref"]["digest"] == proposal["source_ref"]["digest"]:
                    if other["source_ref"]["row"] == proposal["source_ref"]["row"]:
                        issues.append("possible_overlap")
                        break
                    continue
                other_fields = (
                    self.records[other["id"]]["fields"]
                    if other["status"] == "confirmed"
                    else other["fields"]
                )
                same_reference = all(
                    other_fields.get(key) == proposal["fields"].get(key)
                    for key in ("source_id", "account", "currency")
                )
                if same_reference or _signature(other_fields) == _signature(
                    proposal["fields"]
                ):
                    issues.append("possible_overlap")
                    break
        return issues

    def ingest(self, path: Path, stub_path: Path | None = None) -> dict:
        result = load_input(path, stub_path)
        ids = []
        for item in result["proposals"]:
            ref = item["source_ref"]
            identity = f"{ref['digest']}:{ref['row']}"
            if "stub_digest" in ref:
                identity += f":stub:{ref['stub_digest']}"
            proposal_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
            ids.append(proposal_id)
            if proposal_id not in self.proposals:
                self.proposals[proposal_id] = {
                    "id": proposal_id,
                    **item,
                    "mode": result["mode"],
                    "status": "proposed",
                    "issues": [],
                }
        self.state["imports"].append(
            {"file": Path(path).name, "mode": result["mode"], "errors": result["errors"]}
        )
        self.review()
        self._save()
        return {"mode": result["mode"], "ids": ids, "errors": result["errors"]}

    def review(self) -> list[dict]:
        for proposal in self.proposals.values():
            proposal["issues"] = (
                self._issues(proposal) if proposal["status"] == "proposed" else []
            )
        return list(self.proposals.values())

    def resolve(self, proposal_id: str, **fields):
        proposal = self.proposals[proposal_id]
        if proposal["status"] != "proposed":
            raise ValueError("Only proposed entries can be resolved")
        if set(fields) - set(FIELDS) - {"overlap_reviewed"}:
            raise ValueError("Unknown resolution field")
        if "overlap_reviewed" in fields:
            if fields["overlap_reviewed"] is not True:
                raise ValueError("Overlap acknowledgment must be explicit true")
            proposal["overlap_reviewed"] = fields.pop("overlap_reviewed")
        proposal.setdefault("resolutions", []).append(
            {"before": dict(proposal["fields"]), "changes": fields}
        )
        proposal["fields"].update(fields)
        self.review()
        self._save()

    def confirm(self, proposal_ids: list[str]) -> dict:
        for proposal_id in proposal_ids:
            if proposal_id not in self.proposals:
                raise KeyError(proposal_id)
        outcome = {"confirmed": [], "skipped": {}}
        for proposal_id in proposal_ids:
            proposal = self.proposals[proposal_id]
            if proposal["status"] == "confirmed":
                continue
            issues = self._issues(proposal)
            if proposal["status"] != "proposed" or issues:
                outcome["skipped"][proposal_id] = issues or [proposal["status"]]
                continue
            self.records[proposal_id] = {
                "id": proposal_id,
                "proposal_id": proposal_id,
                "fields": dict(proposal["fields"]),
                "source_ref": dict(proposal["source_ref"]),
                "revisions": [],
            }
            proposal["status"] = "confirmed"
            outcome["confirmed"].append(proposal_id)
        self.review()
        self._save()
        return outcome

    def reject(self, proposal_id: str):
        proposal = self.proposals[proposal_id]
        if proposal["status"] != "proposed":
            raise ValueError("Only proposed entries can be rejected")
        proposal["status"] = "rejected"
        self.review()
        self._save()

    def correct(self, record_id: str, reason: str, **fields):
        if not reason.strip() or set(fields) - set(FIELDS):
            raise ValueError("Correction requires a reason and known fields")
        record = self.records[record_id]
        after = {**record["fields"], **fields}
        if field_issues(after):
            raise ValueError(f"Unresolved correction: {field_issues(after)}")
        record["revisions"].append(
            {"before": dict(record["fields"]), "after": after, "reason": reason}
        )
        record["fields"] = after
        self._save()

    def totals(self) -> dict:
        totals = {}
        for record in self.records.values():
            fields = record["fields"]
            group = totals.setdefault(fields["currency"], {}).setdefault(
                fields["destination"],
                {
                    "expense": Decimal("0"),
                    "income": Decimal("0"),
                    "transfer": Decimal("0"),
                },
            )
            kind = "expense" if fields["kind"] == "refund" else fields["kind"]
            group[kind] += Decimal(fields["amount"]) * (
                -1 if fields["kind"] == "refund" else 1
            )
        return {
            currency: {
                destination: {kind: f"{amount:.2f}" for kind, amount in group.items()}
                for destination, group in destinations.items()
            }
            for currency, destinations in totals.items()
        }
