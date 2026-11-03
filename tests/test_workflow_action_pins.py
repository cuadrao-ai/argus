from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

ROOT = Path(__file__).resolve().parents[1]
PINNED_ACTION = re.compile(
    r"[\w.-]+/[\w.-]+(?:/[\w./-]+)?@[0-9a-fA-F]{40}"
)
VERSION_COMMENT = re.compile(r"[\s}\],]*#\s+v?\d[\w.+-]*\s*$")
SHA = "0123456789abcdef0123456789abcdef01234567"


def _mapping(node: Node) -> dict[str, Node]:
    assert isinstance(node, MappingNode)
    return {key.value: value for key, value in node.value}


def _action_nodes(source: str) -> Iterator[ScalarNode]:
    workflow = _mapping(yaml.compose(source))
    for job in _mapping(workflow["jobs"]).values():
        fields = _mapping(job)
        entries = [fields]
        if "steps" in fields:
            steps = fields["steps"]
            assert isinstance(steps, SequenceNode)
            entries.extend(_mapping(step) for step in steps.value)
        for entry in entries:
            if "uses" in entry:
                action = entry["uses"]
                assert isinstance(action, ScalarNode)
                yield action


def _pin_problems(source: str) -> list[str]:
    lines = source.splitlines()
    problems = []
    for action in _action_nodes(source):
        reference = action.value
        if reference.startswith("./"):
            continue
        location = f"line {action.start_mark.line + 1}: {reference}"
        if PINNED_ACTION.fullmatch(reference) is None:
            problems.append(f"{location} must use a full commit SHA")
        tail = lines[action.end_mark.line][action.end_mark.column:]
        if VERSION_COMMENT.fullmatch(tail) is None:
            problems.append(f"{location} must retain a trailing version comment")
    return problems


def _workflow_paths(directory: Path) -> list[Path]:
    return sorted(path for path in directory.iterdir() if path.suffix in {".yml", ".yaml"})


@pytest.mark.parametrize("path", _workflow_paths(ROOT / ".github" / "workflows"))
def test_workflow_actions_are_pinned(path: Path) -> None:
    assert _pin_problems(path.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("suffix", [".yml", ".yaml"])
def test_workflow_discovery_includes_both_extensions(tmp_path: Path, suffix: str) -> None:
    workflow = tmp_path / f"workflow{suffix}"
    workflow.write_text("jobs: {}\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    assert _workflow_paths(tmp_path) == [workflow]


@pytest.mark.parametrize(
    "reference",
    [
        "sample/action@v1",
        "sample/action@main",
        "sample/action@0123456",
        f"sample/action@{'g' * 40}",
        f"sample/action@{SHA}0",
        "sample/action",
        "docker://sample:1",
    ],
)
@pytest.mark.parametrize("reusable", [False, True])
def test_mutable_and_invalid_action_refs_fail(reference: str, reusable: bool) -> None:
    entry = f"uses: {reference} # v1\n"
    source = f"jobs:\n  check:\n    {entry}" if reusable else (
        f"jobs:\n  check:\n    steps:\n      - {entry}"
    )
    problems = _pin_problems(source)
    assert len(problems) == 1
    assert "must use a full commit SHA" in problems[0]


@pytest.mark.parametrize(
    "entry",
    [
        f"uses: sample/action@{SHA} # v1",
        f"uses: sample/action/subdirectory@{SHA} # v1.2.3",
        f"'uses': 'sample/action@{SHA}' # v1",
        f'"uses": "sample/action@{SHA}" # v1',
        f"{{uses: sample/action@{SHA}}} # v1",
        "uses: ./.github/actions/local",
    ],
)
def test_pinned_and_local_action_steps_pass(entry: str) -> None:
    assert _pin_problems(f"jobs:\n  check:\n    steps:\n      - {entry}\n") == []


@pytest.mark.parametrize(
    "entry",
    [
        f"uses: sample/repo/.github/workflows/build.yml@{SHA} # v1",
        "uses: ./.github/workflows/build.yml",
    ],
)
def test_pinned_and_local_reusable_workflows_pass(entry: str) -> None:
    assert _pin_problems(f"jobs:\n  check:\n    {entry}\n") == []


@pytest.mark.parametrize("comment", ["", " #", " # pinned", "\n      # v1"])
def test_missing_version_comment_fails(comment: str) -> None:
    source = f"jobs:\n  check:\n    steps:\n      - uses: sample/action@{SHA}{comment}\n"
    problems = _pin_problems(source)
    assert len(problems) == 1
    assert "must retain a trailing version comment" in problems[0]


def test_aliases_cannot_hide_unpinned_actions() -> None:
    source = "jobs:\n  check:\n    steps:\n      - &action {uses: sample/action@v1} # v1\n      - *action\n"
    assert len(_pin_problems(source)) == 2
    assert _pin_problems(source.replace("sample/action@v1", f"sample/action@{SHA}")) == []


def test_run_text_and_comments_are_not_action_uses() -> None:
    source = """jobs:
  check:
    steps:
      # uses: sample/action@v1
      - run: |
          uses: sample/action@v1
"""
    assert _pin_problems(source) == []
