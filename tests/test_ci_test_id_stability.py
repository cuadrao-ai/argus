"""Catch collection identities that change between fresh Python processes."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts/ci/check_test_ids.py"


class TestIdStabilityTests(unittest.TestCase):
    def run_check(
        self, source: str, *, duplicate: bool = False, addopts: str = ""
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
            sample = work / "test_sample.py"
            sample.write_text(source, encoding="utf-8")
            paths = [str(sample)] * (2 if duplicate else 1)
            return subprocess.run(
                [sys.executable, str(CHECK), *paths],
                cwd=ROOT,
                env={
                    **os.environ,
                    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                    "PYTEST_ADDOPTS": addopts,
                },
                capture_output=True,
                text=True,
                timeout=30,
            )

    def test_random_automatic_ids_are_rejected(self) -> None:
        result = self.run_check(
            "import pytest\nfrom uuid import uuid4\n"
            "@pytest.mark.parametrize('value', [str(uuid4())])\n"
            "def test_value(value):\n    raise AssertionError('must not execute')\n"
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Test IDs differ", result.stderr)
        self.assertIn("test_value[", result.stderr)

    def test_random_explicit_ids_are_rejected(self) -> None:
        result = self.run_check(
            "import pytest\nfrom uuid import uuid4\n"
            "@pytest.mark.parametrize('value', [1], ids=lambda value: str(uuid4()))\n"
            "def test_value(value):\n    pass\n"
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Test IDs differ", result.stderr)

    def test_time_based_automatic_ids_are_rejected(self) -> None:
        result = self.run_check(
            "import pytest\nfrom time import time_ns\n"
            "@pytest.mark.parametrize('value', [time_ns()])\n"
            "def test_value(value):\n    raise AssertionError('must not execute')\n"
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Test IDs differ", result.stderr)

    def test_explicit_ids_allow_random_values_without_executing_tests(self) -> None:
        result = self.run_check(
            "import pytest\nfrom uuid import uuid4\n"
            "@pytest.mark.parametrize('value', [str(uuid4())], ids=['random-value'])\n"
            "def test_value(value):\n    raise AssertionError('must not execute')\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Stable test IDs: 1", result.stdout)

    def test_collection_failure_is_rejected(self) -> None:
        result = self.run_check("raise RuntimeError('synthetic collection failure')\n")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Collection 1 failed", result.stderr)

    def test_empty_collection_is_rejected(self) -> None:
        result = self.run_check("")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Collection 1 failed", result.stderr)

    def test_duplicate_ids_are_rejected(self) -> None:
        result = self.run_check("def test_value():\n    pass\n", duplicate=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("duplicate test IDs", result.stderr)

    def test_inherited_selection_cannot_hide_tests(self) -> None:
        result = self.run_check(
            "def test_value():\n    pass\n", addopts="-k nonexistent_case"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Stable test IDs: 1", result.stdout)

    def test_backend_collection_ids_are_stable(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CHECK)],
            cwd=ROOT,
            env={**os.environ, "PYTEST_ADDOPTS": ""},
            capture_output=True,
            text=True,
            timeout=660,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
