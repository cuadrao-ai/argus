"""Validate required pull request metadata; bot-authored requests are exempt."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HEADING = "## Merge Danger"
REQUIRED_FIELDS = ("Door", "Blast radius", "Rollback")
DOORS = frozenset({"one-way", "two-way"})
ISSUE_REFERENCE = re.compile(r"\b(?:closes|fixes|refs)\s+#[1-9][0-9]*\b", re.IGNORECASE)
PILOT_FLOWS = ("upload", "email", "WhatsApp", "review", "month close", "606/607")
PILOT_FLOW = re.compile(r"(?:[-*]\s+)?Pilot flow:[ \t]*(?P<value>.*)")
NO_PILOT_FLOW = re.compile(r"none \((?P<reason>.+)\)")
TEMPLATE_REASON_HINT = "reason"
FIELD_LINE = re.compile(
    r"^(?:[-*]\s+)?(?P<name>Door|Blast radius|Rollback|Eval tier):\s*(?P<value>.*)$"
)
PLACEHOLDER = re.compile(r"^<.+>$", re.DOTALL)


def merge_danger_section(body: str) -> str | None:
    lines = body.replace("\r\n", "\n").split("\n")
    start = None
    for index, line in enumerate(lines):
        if line.strip() == HEADING:
            start = index + 1
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


def field_values(section: str) -> dict[str, str]:
    found: dict[str, list[str]] = {}
    current: str | None = None
    for line in section.split("\n"):
        match = FIELD_LINE.match(line)
        if match is not None:
            current = match.group("name")
            found[current] = [match.group("value")]
            continue
        if current is not None:
            found[current].append(line)
    return {name: "\n".join(parts).strip() for name, parts in found.items()}


def body_problems(body: str) -> list[str]:
    section = merge_danger_section(body)
    if section is None:
        return ["missing Merge Danger block"]
    values = field_values(section)
    problems: list[str] = []
    for name in REQUIRED_FIELDS:
        value = values.get(name, "")
        if value == "":
            problems.append(f"{name} is empty")
            continue
        if PLACEHOLDER.match(value):
            problems.append(f"{name} is an untouched placeholder")
            continue
        if name == "Door" and value not in DOORS:
            problems.append("Door must be one-way or two-way")
    lines = [line.strip() for line in body.splitlines()]
    if not any(ISSUE_REFERENCE.search(line) for line in lines):
        problems.append(
            "missing issue reference: write Closes, Fixes or Refs and the issue number, as in Closes #12"
        )
    if not any(valid_pilot_flow(line) for line in lines):
        problems.append(
            "missing or invalid Pilot flow line; use one or more of "
            f"{', '.join(PILOT_FLOWS)} (comma-separated), or none (<written reason>)"
        )
    return problems


def valid_pilot_flow(line: str) -> bool:
    match = PILOT_FLOW.fullmatch(line)
    if match is None:
        return False
    value = match.group("value").strip()
    no_flow = NO_PILOT_FLOW.fullmatch(value)
    if no_flow is not None:
        reason = no_flow.group("reason").strip()
        return (
            bool(reason)
            and not PLACEHOLDER.fullmatch(reason)
            and reason.lower() != TEMPLATE_REASON_HINT
        )
    return all(flow.strip() in PILOT_FLOWS for flow in value.split(","))


def pull_request(payload: object) -> dict | None:
    if not isinstance(payload, dict):
        return None
    candidate = payload.get("pull_request")
    if not isinstance(candidate, dict):
        return None
    return candidate


def author_login(request: dict) -> str:
    user = request.get("user")
    if not isinstance(user, dict):
        return ""
    login = user.get("login")
    return login if isinstance(login, str) else ""


def is_bot_author(request: dict) -> bool:
    user = request.get("user")
    return author_login(request).endswith("[bot]") or (
        isinstance(user, dict) and user.get("type") == "Bot"
    )


def request_body(request: dict) -> str:
    body = request.get("body")
    return body if isinstance(body, str) else ""


def main() -> int:
    raw_path = os.environ.get("GITHUB_EVENT_PATH", "").strip()
    if not raw_path:
        print("GITHUB_EVENT_PATH is required.", file=sys.stderr)
        return 1
    try:
        payload = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot read the pull request event: {exc}", file=sys.stderr)
        return 1
    request = pull_request(payload)
    if request is None:
        print("The event has no pull request.", file=sys.stderr)
        return 1
    login = author_login(request)
    if is_bot_author(request):
        print(f"exempt author {login}")
        return 0
    problems = body_problems(request_body(request))
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
