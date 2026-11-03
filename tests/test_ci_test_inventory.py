"""Exercise the evidence recorder against real, isolated test sessions."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InventoryTests(unittest.TestCase):
    def run_session(self, source: str, *args: str) -> tuple[int, dict]:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
            (work / "test_sample.py").write_text(source, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-p",
                    "scripts.ci.pytest_inventory",
                    "--ci-inventory=evidence.json",
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
            self.assertTrue((work / "evidence.json").exists(), result.stdout + result.stderr)
            return result.returncode, json.loads((work / "evidence.json").read_text())

    def test_preserves_parameter_ids_and_all_execution_phases(self) -> None:
        code, evidence = self.run_session(
            "import pytest\n"
            "@pytest.mark.parametrize('value', [1, 2], ids=['first', 'space and ::'])\n"
            "def test_value(value):\n    assert value > 0\n"
        )
        self.assertEqual(code, 0)
        self.assertEqual(evidence["exitstatus"], 0)
        self.assertEqual(
            evidence["nodeids"],
            ["test_sample.py::test_value[first]", "test_sample.py::test_value[space and ::]"],
        )
        self.assertEqual(evidence["collection_errors"], 0)
        self.assertEqual(evidence["deselected"], [])
        self.assertEqual(len(evidence["reports"]), 6)
        for nodeid in evidence["nodeids"]:
            reports = [r for r in evidence["reports"] if r["nodeid"] == nodeid]
            self.assertEqual([r["phase"] for r in reports], ["setup", "call", "teardown"])
            self.assertTrue(all(r["outcome"] == "passed" for r in reports))
            self.assertTrue(all(r["duration_seconds"] >= 0 for r in reports))
        self.assertGreater(evidence["elapsed_seconds"], 0)

    def test_failed_and_skipped_tests_remain_in_inventory(self) -> None:
        code, evidence = self.run_session(
            "import pytest\n"
            "def test_fail():\n    assert False\n"
            "@pytest.mark.skip(reason='synthetic skip')\n"
            "def test_skip():\n    pass\n"
        )
        self.assertEqual(code, 1)
        self.assertEqual(evidence["exitstatus"], 1)
        self.assertEqual(len(evidence["nodeids"]), 2)
        self.assertEqual(sum(r["outcome"] == "failed" for r in evidence["reports"]), 1)
        self.assertEqual(sum(r["outcome"] == "skipped" for r in evidence["reports"]), 1)

    def test_collection_error_is_not_success(self) -> None:
        code, evidence = self.run_session("raise RuntimeError('synthetic collection error')\n")
        self.assertEqual(code, 2)
        self.assertEqual(evidence["exitstatus"], 2)
        self.assertEqual(evidence["collection_errors"], 1)
        self.assertEqual(evidence["reports"], [])

    def test_deselection_is_explicit(self) -> None:
        code, evidence = self.run_session(
            "def test_one():\n    pass\ndef test_two():\n    pass\n", "-k", "one"
        )
        self.assertEqual(code, 0)
        self.assertEqual(evidence["nodeids"], ["test_sample.py::test_one"])
        self.assertEqual(evidence["deselected"], ["test_sample.py::test_two"])

    def test_duplicate_identities_are_not_hidden_by_a_set(self) -> None:
        code, evidence = self.run_session(
            "def test_one():\n    pass\n", "test_sample.py", "test_sample.py"
        )
        self.assertEqual(code, 0)
        self.assertEqual(evidence["nodeids"], ["test_sample.py::test_one"] * 2)
        self.assertEqual(len(evidence["reports"]), 6)

    def test_collect_only_is_distinct_from_execution(self) -> None:
        code, evidence = self.run_session("def test_one():\n    pass\n", "--collect-only")
        self.assertEqual(code, 0)
        self.assertEqual(evidence["nodeids"], ["test_sample.py::test_one"])
        self.assertEqual(evidence["reports"], [])

    def test_no_tests_is_not_success(self) -> None:
        code, evidence = self.run_session("")
        self.assertEqual(code, 5)
        self.assertEqual(evidence["exitstatus"], 5)
        self.assertEqual(evidence["nodeids"], [])


if __name__ == "__main__":
    unittest.main()
