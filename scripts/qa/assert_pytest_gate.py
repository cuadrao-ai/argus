"""Fail a required pytest gate unless every collected test ran and passed."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path
from xml.etree import ElementTree

# Outcome tag -> (suite count attribute, printed label). Order decides which
# count a testcase holding several outcomes lands in; it is counted once.
_OUTCOMES = {
    "failure": ("failures", "failed"),
    "error": ("errors", "error"),
    "skipped": ("skipped", "skipped"),
}
_SUITE_TAGS = ("testsuite", "testsuites")


def _labels(case: ElementTree.Element) -> list[str]:
    labels = []
    for tag, (_, label) in _OUTCOMES.items():
        outcome = case.find(tag)
        if outcome is None:
            continue
        xfail = tag == "skipped" and outcome.attrib.get("type") == "pytest.xfail"
        labels.append("xfail" if xfail else label)
    return labels


def _count(cases: Iterable[ElementTree.Element]) -> dict[str, int]:
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for case in cases:
        counts["tests"] += 1
        for tag, (attribute, _) in _OUTCOMES.items():
            if case.find(tag) is not None:
                counts[attribute] += 1
                break
    return counts


def _problems(root: ElementTree.Element) -> list[str]:
    problems = [
        f"  {', '.join(labels)}:"
        f" {case.attrib.get('classname', '')}::{case.attrib.get('name', '')}"
        for case in root.iter("testcase")
        if (labels := _labels(case))
    ]
    # The testcase elements own every count; a suite attribute that says
    # otherwise fails the gate.
    for suite in root.iter():
        if suite.tag not in _SUITE_TAGS:
            continue
        for attribute, found in _count(suite.iter("testcase")).items():
            claimed = suite.attrib.get(attribute)
            if claimed is not None and int(claimed) != found:
                problems.append(
                    f'  mismatch: suite "{suite.attrib.get("name", "")}" says'
                    f" {attribute}={claimed}, testcase elements show {found}"
                )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("junit_xml", type=Path)
    args = parser.parse_args()
    root = ElementTree.parse(args.junit_xml).getroot()
    counts = _count(root.iter("testcase"))
    if counts["tests"] == 0:
        raise SystemExit("required pytest gate collected zero tests")
    not_passed = counts["failures"] + counts["errors"] + counts["skipped"]
    summary = (
        f"{counts['tests']} tests, {counts['tests'] - not_passed} passed,"
        f" {counts['failures']} failed, {counts['errors']} errors,"
        f" {counts['skipped']} skipped"
    )
    problems = _problems(root)
    if problems:
        raise SystemExit(
            "\n".join([f"required pytest gate failed: {summary}", *problems])
        )
    print(f"required pytest gate passed: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
