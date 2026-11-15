"""Fail when a browser spec or Playwright config is not run by any CI workflow.

A spec is every ``*.spec.ts`` under ``web/e2e/`` and ``marketing/e2e/``. A config is
every ``playwright*.config.ts`` in those app folders and every ``*.config.ts`` under
their ``e2e/`` folders.

A workflow runs a spec when one of its ``run:`` steps runs ``playwright test``,
directly or through a ``package.json`` script, and that command selects the spec:

- The command's config is ``--config``/``-c``, else ``playwright.config.ts`` in the
  step's directory. The directory comes from ``working-directory:`` and any ``cd``
  earlier in the same step.
- The config selects the spec through ``testDir``, ``testMatch`` and ``testIgnore``.
  Each must be a string literal or a list of string literals. Anything else fails
  the check, because this script cannot read it.
- Positional arguments filter by file path, as in Playwright.

A config is run when such a command uses it. Shell scripts that a step calls are
not followed. There is no allowlist: run the spec in CI or delete it.
"""

from __future__ import annotations

import fnmatch
import json
import posixpath
import re
import shlex
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPS = ("web", "marketing")
SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")"}
VALUE_FLAGS = {
    "--project",
    "--grep",
    "-g",
    "--grep-invert",
    "--workers",
    "-j",
    "--reporter",
    "--retries",
    "--timeout",
    "--output",
    "--shard",
    "--max-failures",
    "--repeat-each",
    "--global-timeout",
    "--trace",
    "--tsconfig",
}
SELECTOR = re.compile(r"\b(testDir|testMatch|testIgnore)\s*:\s*")
STRING = re.compile(r"""\s*(["'])([^"'\n]*)\1\s*""")


class UnreadableConfig(Exception):
    pass


@dataclass(frozen=True)
class Run:
    config: str
    filters: tuple[str, ...]


@dataclass(frozen=True)
class Selection:
    test_dir: str
    match: tuple[str, ...]
    ignore: tuple[str, ...]


def step_chunks(text: str) -> list[list[str]]:
    chunks: list[list[str]] = [[]]
    block_indent: int | None = None
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip())
        if block_indent is not None and (not line.strip() or indent > block_indent):
            chunks[-1].append(line)
            continue
        block_indent = None
        if re.match(r"\s*- ", line):
            chunks.append([])
        chunks[-1].append(line)
        if re.match(r"\s*(?:- )?[\w-]+:\s*[|>][-+]?\s*$", line):
            block_indent = indent
    return chunks


def step_script(chunk: list[str]) -> tuple[str, str] | None:
    workdir = "."
    script = None
    for index, line in enumerate(chunk):
        found = re.match(r"\s*(?:- )?working-directory:\s*['\"]?([^'\"\s]+)", line)
        if found:
            workdir = found.group(1)
        found = re.match(r"(\s*)(?:- )?run:\s*(.*)$", line)
        if not found:
            continue
        value = found.group(2).strip()
        if value[:1] not in "|>":
            script = value.strip("'\"")
            continue
        key_indent = len(found.group(1))
        body = []
        for following in chunk[index + 1 :]:
            if following.strip() and len(following) - len(following.lstrip()) <= key_indent:
                break
            body.append(following.strip())
        script = (" " if value.startswith(">") else "\n").join(body)
    return (workdir, script) if script is not None else None


def commands(script: str) -> list[list[str]]:
    result: list[list[str]] = []
    for line in script.replace("\\\n", " ").splitlines():
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        try:
            tokens = list(lexer)
        except ValueError:
            tokens = line.split()
        current: list[str] = []
        for token in tokens + [";"]:
            if token in SEPARATORS:
                if current:
                    result.append(current)
                current = []
            else:
                current.append(token)
    return result


def playwright_args(tokens: list[str], cwd: Path) -> list[str] | None:
    for index in range(len(tokens) - 1):
        if tokens[index].endswith("playwright") and tokens[index + 1] == "test":
            return tokens[index + 2 :]
    while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
        tokens = tokens[1:]
    if len(tokens) < 3 or tokens[0] not in {"bun", "npm"} or tokens[1] != "run":
        return None
    manifest = cwd / "package.json"
    if not manifest.is_file():
        return None
    script = json.loads(manifest.read_text()).get("scripts", {}).get(tokens[2])
    extra = [token for token in tokens[3:] if token != "--"]
    for command in commands(script or ""):
        args = playwright_args(command, cwd)
        if args is not None:
            return args + extra
    return None


def workflow_runs(root: Path) -> list[Run]:
    runs = []
    for workflow in sorted((root / ".github/workflows").glob("*.y*ml")):
        for chunk in step_chunks(workflow.read_text()):
            step = step_script(chunk)
            if step is None:
                continue
            cwd = (root / step[0]).resolve()
            for tokens in commands(step[1]):
                if tokens[:1] == ["cd"] and len(tokens) == 2:
                    cwd = (cwd / tokens[1]).resolve()
                    continue
                args = playwright_args(tokens, cwd)
                if args is not None:
                    runs.append(run_from_args(root, cwd, args))
    return runs


def run_from_args(root: Path, cwd: Path, args: list[str]) -> Run:
    config = cwd / "playwright.config.ts"
    filters = []
    pending = None
    for arg in args:
        if pending == "config":
            config = cwd / arg
        if pending:
            pending = None
            continue
        if arg in {"--config", "-c"}:
            pending = "config"
        elif arg.startswith("--config="):
            config = cwd / arg.split("=", 1)[1]
        elif arg in VALUE_FLAGS:
            pending = "value"
        elif not arg.startswith("-"):
            filters.append(arg)
    return Run(relative(root, config.resolve()), tuple(filters))


def literals(text: str, start: int, field: str, config: str) -> tuple[str, ...]:
    found = STRING.match(text, start)
    if found:
        return (found.group(2),)
    if text[start : start + 1] == "[":
        end = text.find("]", start)
        items = [item for item in text[start + 1 : end].split(",") if item.strip()]
        values = [STRING.fullmatch(item) for item in items]
        if end != -1 and all(values):
            return tuple(value.group(2) for value in values)
    raise UnreadableConfig(f"{config}: {field} must be a string literal or a list of them")


def selection(root: Path, config: str) -> Selection:
    path = root / config
    text = path.read_text()
    if re.search(r"""from\s+["'][^"']*config["']""", text):
        raise UnreadableConfig(f"{config}: a config built from another config cannot be read")
    fields = {"testDir": (".",), "testMatch": ("*.spec.ts",), "testIgnore": ()}
    for found in SELECTOR.finditer(text):
        fields[found.group(1)] = literals(text, found.end(), found.group(1), config)
    test_dir = posixpath.normpath(posixpath.join(posixpath.dirname(config), fields["testDir"][0]))
    return Selection(test_dir, fields["testMatch"], fields["testIgnore"])


def glob_hit(path: str, pattern: str) -> bool:
    if "/" not in pattern:
        return fnmatch.fnmatch(posixpath.basename(path), pattern)
    return fnmatch.fnmatch(path, pattern) or (
        pattern.startswith("**/") and fnmatch.fnmatch(path, pattern[3:])
    )


def selects(root: Path, run: Run, chosen: Selection, spec: str) -> bool:
    if not spec.startswith(chosen.test_dir.rstrip("/") + "/"):
        return False
    inner = spec[len(chosen.test_dir.rstrip("/")) + 1 :]
    if not any(glob_hit(inner, pattern) for pattern in chosen.match):
        return False
    if any(glob_hit(inner, pattern) for pattern in chosen.ignore):
        return False
    absolute = (root / spec).as_posix()
    return not run.filters or any(re.search(item, absolute) for item in run.filters)


def specs(root: Path) -> list[str]:
    return sorted(
        relative(root, path) for app in APPS for path in (root / app / "e2e").rglob("*.spec.ts")
    )


def configs(root: Path) -> list[str]:
    found = set()
    for app in APPS:
        found.update((root / app).glob("playwright*.config.ts"))
        found.update((root / app / "e2e").rglob("*.config.ts"))
    return sorted(relative(root, path) for path in found)


def relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def problems(root: Path) -> list[str]:
    runs = workflow_runs(root)
    found = []
    chosen: dict[str, Selection] = {}
    for config in sorted({run.config for run in runs}):
        if not (root / config).is_file():
            found.append(f"{config}: a workflow runs this config, but it does not exist")
            continue
        try:
            chosen[config] = selection(root, config)
        except UnreadableConfig as error:
            found.append(str(error))
    for spec in specs(root):
        if not any(
            run.config in chosen and selects(root, run, chosen[run.config], spec) for run in runs
        ):
            found.append(f"{spec}: no workflow runs this spec. Run it in CI or delete it.")
    used = {run.config for run in runs}
    for config in configs(root):
        if config not in used:
            found.append(f"{config}: no workflow runs this config. Run it in CI or delete it.")
    return found


def main() -> int:
    started = time.perf_counter()
    found = problems(ROOT)
    for problem in found:
        print(problem)
    print(
        f"Browser specs: {len(specs(ROOT))} found, {len(found)} problems; "
        f"{time.perf_counter() - started:.3f}s"
    )
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
