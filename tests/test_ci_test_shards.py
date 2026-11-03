"""Prove exact shard coverage and fail closed on incomplete execution evidence."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from scripts.ci.test_shards import partition, read_timings, verify

ROOT = Path(__file__).resolve().parents[1]
NODES = [
    "tests/test_a.py::test_one[x::y]",
    "tests/test_a.py::test_two",
    "tests/test_b.py::test_one",
]


def evidence(index: int, selected: list[str], full: list[str] | None = None) -> dict:
    return {
        "schema_version": 2,
        "shard_index": index,
        "shard_count": 2,
        "full_nodeids": NODES if full is None else full,
        "nodeids": selected,
        "exitstatus": 0,
        "collection_errors": 0,
        "deselected": [],
        "reports": [
            {
                "nodeid": nodeid,
                "phase": phase,
                "outcome": "passed",
                "duration_seconds": 0.01,
            }
            for nodeid in selected
            for phase in ("setup", "call", "teardown")
        ],
    }


def complete() -> list[dict]:
    return [evidence(0, NODES[:2]), evidence(1, NODES[2:])]


class PartitionTests(unittest.TestCase):
    def test_balances_measured_costs_and_keeps_files_together(self) -> None:
        nodes = [f"tests/test_{name}.py::test_{i}" for name in "abcd" for i in range(2)]
        timings = {
            f"tests/test_{name}.py": seconds
            for name, seconds in zip("abcd", [8, 7, 6, 5], strict=True)
        }
        shards = partition(nodes, 2, timings)
        self.assertEqual(shards, [nodes[:2] + nodes[6:], nodes[2:6]])
        self.assertEqual(Counter(n for shard in shards for n in shard), Counter(nodes))

    def test_ties_are_deterministic_and_preserve_collection_order(self) -> None:
        nodes = [
            "tests/test_b.py::test_two",
            "tests/test_a.py::test_one",
            "tests/test_b.py::test_one",
        ]
        self.assertEqual(partition(nodes, 2, {}), [[nodes[0], nodes[2]], [nodes[1]]])
        self.assertEqual(
            partition(list(reversed(nodes)), 2, {}), [[nodes[2], nodes[0]], [nodes[1]]]
        )

    def test_unknown_files_use_measured_per_node_cost(self) -> None:
        nodes = [
            "tests/test_a.py::test_one",
            "tests/test_b.py::test_one",
            "tests/test_b.py::test_two",
            "tests/test_c.py::test_one",
        ]
        self.assertEqual(
            partition(nodes, 2, {"tests/test_a.py": 3}),
            [nodes[1:3], [nodes[0], nodes[3]]],
        )

    def test_rejects_duplicate_ids_invalid_count_and_empty_shards(self) -> None:
        for nodes, count in [
            (NODES + NODES[:1], 2),
            (NODES, 0),
            (NODES, -1),
            (NODES, True),
            (NODES, 3),
            ([], 1),
        ]:
            with self.subTest(nodes=nodes, count=count), self.assertRaises(ValueError):
                partition(nodes, count, {})

    def test_rejects_bad_timing_data(self) -> None:
        for value in [-1, float("inf"), float("nan"), True, "4", None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                partition(NODES, 2, {"tests/test_a.py": value})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "timings.json"
            for text in ["[]", '{"not-a-file": 1}', '{"tests/test_a.py::test_one": 1}']:
                path.write_text(text)
                with self.subTest(text=text), self.assertRaises(ValueError):
                    read_timings(path)

    def test_zero_timings_still_populate_every_shard(self) -> None:
        self.assertTrue(
            all(partition(NODES, 2, {"tests/test_a.py": 0, "tests/test_b.py": 0}))
        )


class VerificationTests(unittest.TestCase):
    def test_complete_union_has_reusable_exact_ids_and_counts(self) -> None:
        result = verify(list(reversed(complete())), require_passed=True)
        self.assertEqual(result["nodeids"], NODES)
        self.assertEqual(result["test_count"], 3)
        self.assertEqual(result["selected_counts"], {"0": 2, "1": 1})
        self.assertTrue(result["union_exact"])
        self.assertEqual(result["duplicates"], 0)
        self.assertEqual(len(result["nodeids_sha256"]), 64)

    def test_full_collection_order_may_differ_between_runners(self) -> None:
        data = complete()
        data[1]["full_nodeids"] = list(reversed(NODES))
        self.assertEqual(verify(data)["test_count"], 3)
        self.assertEqual(
            verify(data)["nodeids_sha256"], verify(complete())["nodeids_sha256"]
        )

    def test_missing_repeated_or_mismatched_shard_is_rejected(self) -> None:
        for data in [[], complete()[:1], [complete()[0], complete()[0]]]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                verify(data)
        for key, value in [
            ("shard_index", 2),
            ("shard_index", True),
            ("shard_count", 3),
            ("full_nodeids", NODES[:-1]),
        ]:
            data = complete()
            data[1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify(data)

    def test_omissions_and_overlapping_assignments_are_rejected(self) -> None:
        for data in [
            [evidence(0, NODES[:1]), evidence(1, NODES[2:])],
            [evidence(0, NODES[:2]), evidence(1, NODES[1:])],
        ]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                verify(data)

    def test_duplicate_full_or_selected_ids_are_rejected(self) -> None:
        for key in ["nodeids", "full_nodeids"]:
            data = complete()
            data[0][key] = data[0][key] + data[0][key][:1]
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify(data)

    def test_failed_partial_or_deselected_runs_are_rejected(self) -> None:
        for key, value in [
            ("exitstatus", None),
            ("exitstatus", 1),
            ("exitstatus", False),
            ("collection_errors", 1),
            ("collection_errors", None),
            ("deselected", ["removed"]),
            ("reports", []),
        ]:
            data = complete()
            data[0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                verify(data)

    def test_missing_duplicate_or_foreign_execution_reports_are_rejected(self) -> None:
        data = complete()
        variants = [
            data[0]["reports"][:-1],
            data[0]["reports"] + data[0]["reports"][:1],
            data[0]["reports"] + evidence(0, ["foreign"])["reports"],
        ]
        for reports in variants:
            data = complete()
            data[0]["reports"] = reports
            with self.subTest(reports=reports), self.assertRaises(ValueError):
                verify(data)

    def test_backend_skip_is_allowed_but_required_pass_gate_rejects_it(self) -> None:
        for phase in ["setup", "call", "teardown"]:
            data = complete()
            reports = data[1]["reports"]
            next(r for r in reports if r["phase"] == phase)["outcome"] = "skipped"
            if phase == "setup":
                data[1]["reports"] = [r for r in reports if r["phase"] != "call"]
            verify(data)
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                verify(data, require_passed=True)

    def test_failed_outcomes_and_invalid_durations_are_rejected(self) -> None:
        for key, value in [
            ("outcome", "failed"),
            ("duration_seconds", -1),
            ("duration_seconds", float("nan")),
            ("duration_seconds", True),
        ]:
            data = complete()
            data[0]["reports"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                verify(data)

    def test_baseline_comparison_requires_explicit_added_file(self) -> None:
        baseline = evidence(0, NODES[:2])
        with self.assertRaisesRegex(ValueError, "unexpected added tests"):
            verify(complete(), baseline=baseline)
        result = verify(
            complete(), baseline=baseline, allow_added_files=("tests/test_b.py",)
        )
        self.assertEqual(result["added_nodeids"], NODES[2:])
        self.assertEqual(result["removed_nodeids"], [])
        self.assertTrue(result["baseline_compared"])

    def test_baseline_comparison_rejects_new_skips_without_rejecting_existing_skips(
        self,
    ) -> None:
        baseline = evidence(0, NODES)
        data = complete()
        data[1]["reports"][1]["outcome"] = "skipped"
        with self.assertRaisesRegex(ValueError, "previously executed tests now skipped"):
            verify(data, baseline=baseline)
        baseline["reports"][-2]["outcome"] = "skipped"
        proof = verify(data, baseline=baseline)
        self.assertEqual(proof["skipped_nodeids"], NODES[2:])

    def test_baseline_removal_fails_even_with_added_file_allowlist(self) -> None:
        baseline = evidence(0, NODES + ["tests/test_removed.py::test_one"])
        with self.assertRaisesRegex(ValueError, "baseline tests removed"):
            verify(
                complete(),
                baseline=baseline,
                allow_added_files=("tests/test_removed.py",),
            )


class ShardSessionTests(unittest.TestCase):
    def run_session(self, work: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "scripts.ci.pytest_inventory",
                "-q",
                *args,
            ],
            cwd=work,
            env={
                **os.environ,
                "PYTHONPATH": str(ROOT),
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PYTEST_ADDOPTS": "",
            },
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_real_sessions_preserve_parameterized_union_and_file_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "pytest.ini").write_text("[pytest]\n")
            (work / "test_a.py").write_text(
                "import pytest\n"
                "@pytest.fixture(scope='module')\n"
                "def counter():\n    return []\n"
                "@pytest.mark.parametrize('value', [1, 2], ids=['x::y', 'two words'])\n"
                "def test_count(counter, value):\n    counter.append(value)\n    assert len(counter) == value\n"
            )
            (work / "test_b.py").write_text("def test_one():\n    pass\n")
            (work / "timings.json").write_text('{"test_a.py": 10, "test_b.py": 1}')
            baseline_run = self.run_session(work, "--ci-inventory=baseline.json")
            self.assertEqual(
                baseline_run.returncode, 0, baseline_run.stdout + baseline_run.stderr
            )
            baseline = json.loads((work / "baseline.json").read_text())
            shards = []
            for index in range(2):
                result = self.run_session(
                    work,
                    f"--ci-inventory=shard-{index}.json",
                    "--ci-shard-count=2",
                    f"--ci-shard-index={index}",
                    "--ci-timings=timings.json",
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                shards.append(json.loads((work / f"shard-{index}.json").read_text()))
            self.assertEqual(verify(shards, baseline=baseline)["test_count"], 3)
            self.assertEqual(shards[0]["nodeids"], baseline["nodeids"][:2])
            self.assertTrue(all(shard["deselected"] == [] for shard in shards))
            cli = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/ci/test_shards.py"),
                    "shard-0.json",
                    "shard-1.json",
                    "--baseline",
                    "baseline.json",
                    "--require-passed",
                    "--output",
                    "proof.json",
                ],
                cwd=work,
                capture_output=True,
                text=True,
            )
            self.assertEqual(cli.returncode, 0, cli.stdout + cli.stderr)
            self.assertEqual(
                json.loads((work / "proof.json").read_text())["nodeids"],
                baseline["nodeids"],
            )

    def test_real_sessions_reject_preselection_duplicates_and_empty_shards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "pytest.ini").write_text("[pytest]\n")
            for name in "ab":
                (work / f"test_{name}.py").write_text("def test_one():\n    pass\n")
            for args, expected in [
                (["-k", "test_a"], "unexpected deselection"),
                (["test_a.py", "test_a.py", "test_b.py"], "duplicate node IDs"),
                (["--ci-shard-count=3"], "exceeds collected test files"),
                (["--ci-shard-index=2"], "invalid CI shard"),
            ]:
                result = self.run_session(
                    work, "--ci-inventory=shard.json", "--ci-shard-count=2", *args
                )
                with self.subTest(args=args):
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(expected, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
