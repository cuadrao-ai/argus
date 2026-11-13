"""Every browser spec and Playwright config must be run by a CI workflow."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_e2e_specs_run.py"
spec = importlib.util.spec_from_file_location("check_e2e_specs_run", SCRIPT)
guard = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = guard
spec.loader.exec_module(guard)

DEFAULT_CONFIG = 'export default defineConfig({ testDir: "./e2e" });\n'


def tree(root: Path, workflow: str, files: dict[str, str]) -> Path:
    files = {"web/playwright.config.ts": DEFAULT_CONFIG, **files}
    files[".github/workflows/ci.yml"] = workflow
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


def workflow(*steps: str) -> str:
    return "jobs:\n  web:\n    steps:\n" + "".join(steps)


def test_run_spec_and_config_glob_pass_and_orphan_fails(tmp_path):
    root = tree(
        tmp_path,
        workflow(
            "      - name: Browser checks\n"
            "        run: |\n"
            "          cd web\n"
            "          PORT=3101 bunx playwright test e2e/run.spec.ts\n"
            "          bunx playwright test --config e2e/glob.playwright.config.ts\n"
        ),
        {
            "web/e2e/run.spec.ts": "",
            "web/e2e/glob-a.spec.ts": "",
            "web/e2e/glob-b.spec.ts": "",
            "web/e2e/orphan.spec.ts": "",
            "web/e2e/glob.playwright.config.ts": (
                'export default { testDir: ".", testMatch: ["glob-*.spec.ts"] };\n'
            ),
        },
    )

    assert guard.problems(root) == [
        "web/e2e/orphan.spec.ts: no workflow runs this spec. Run it in CI or delete it."
    ]


@pytest.mark.parametrize(
    "step",
    [
        "      - run: cd web && bunx playwright test e2e/kept.spec.ts\n",
        "      - working-directory: web\n        run: bunx playwright test e2e/kept\n",
        "      - name: Folded\n        run: >-\n          cd web &&\n"
        "          bunx playwright test --workers 1\n          e2e/kept.spec.ts\n",
        "      - name: Package script\n        working-directory: web\n"
        "        run: bun run test:e2e -- e2e/kept.spec.ts\n",
    ],
    ids=["cd", "working-directory", "folded", "package-script"],
)
def test_command_shapes_select_the_named_spec_only(tmp_path, step):
    root = tree(
        tmp_path,
        workflow(step),
        {
            "web/package.json": json.dumps({"scripts": {"test:e2e": "playwright test"}}),
            "web/e2e/kept.spec.ts": "",
            "web/e2e/other.spec.ts": "",
        },
    )

    assert guard.problems(root) == [
        "web/e2e/other.spec.ts: no workflow runs this spec. Run it in CI or delete it."
    ]


def test_ignored_spec_is_not_run(tmp_path):
    root = tree(
        tmp_path,
        workflow("      - run: cd web && bunx playwright test\n"),
        {
            "web/playwright.config.ts": (
                'export default { testDir: "./e2e", testIgnore: "**/skip.spec.ts" };\n'
            ),
            "web/e2e/nested/kept.spec.ts": "",
            "web/e2e/skip.spec.ts": "",
        },
    )

    assert guard.problems(root) == [
        "web/e2e/skip.spec.ts: no workflow runs this spec. Run it in CI or delete it."
    ]


def test_unused_config_fails(tmp_path):
    root = tree(
        tmp_path,
        workflow("      - run: cd web && bunx playwright test\n"),
        {
            "web/e2e/kept.spec.ts": "",
            "web/e2e/old.playwright.config.ts": DEFAULT_CONFIG,
        },
    )

    assert guard.problems(root) == [
        "web/e2e/old.playwright.config.ts: no workflow runs this config. Run it in CI or delete it."
    ]


def test_config_it_cannot_read_fails_instead_of_guessing(tmp_path):
    root = tree(
        tmp_path,
        workflow(
            "      - run: cd web && bunx playwright test --config e2e/dynamic.playwright.config.ts\n"
        ),
        {
            "web/e2e/dynamic.playwright.config.ts": (
                'export default { testDir: ".", testMatch: on ? "a.spec.ts" : "b.spec.ts" };\n'
            ),
            "web/e2e/a.spec.ts": "",
        },
    )

    assert guard.problems(root) == [
        "web/e2e/dynamic.playwright.config.ts: testMatch must be a string literal or a list of them",
        "web/e2e/a.spec.ts: no workflow runs this spec. Run it in CI or delete it.",
        "web/playwright.config.ts: no workflow runs this config. Run it in CI or delete it.",
    ]
