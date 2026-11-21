"""Check evidence trigger coverage from workflow commands and local source imports.

No dependency manifest: the workflow owns its paths; scripts own imports and URL
literals. Follow relative/alias imports (including generated fixture source),
Next pages named by script URLs, their layouts, and package build inputs. This is
static coverage, not execution tracing: conditional imports count; computed URLs
and computed imports still need review. Mocked API URLs do not imply execution of
backend handlers. Run directly or through tests/test_ci_evidence_paths.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from loguru import logger

ROOT = Path(__file__).resolve().parents[2]
IMPORT = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*(?:\(\s*)?|\brequire\s*\(\s*)["']([^"']+)["']"""
)
LITERAL = re.compile(r"""["'`]([^"'`\n]+)["'`]""")
SOURCE = {".ts", ".tsx", ".js", ".mjs", ".cjs", ".css"}


def resolve_file(path: Path) -> Path | None:
    candidates = [path]
    candidates += [Path(str(path) + ext) for ext in (*sorted(SOURCE), ".json")]
    candidates += [path / ("index" + ext) for ext in sorted(SOURCE)]
    return next(
        (candidate.resolve() for candidate in candidates if candidate.is_file()), None
    )


def matches(path: str, pattern: str) -> bool:
    """The positive * and ** path globs used by these workflows.

    Reject other syntax rather than silently approximate Actions filtering.
    """
    if any(char in pattern for char in "![]+{}?"):
        raise ValueError(f"unsupported evidence path glob: {pattern}")
    regex = re.escape(pattern).replace(r"\*\*/", "(?:.*/)?")
    regex = regex.replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return re.fullmatch(regex, path) is not None


def route_matches(route: str, url: str) -> bool:
    parts = []
    for part in route.split("/"):
        if part.startswith("(") and part.endswith(")"):
            continue
        if part.startswith("[[..."):
            parts.append("(?:/.*)?")
        elif part.startswith("[..."):
            parts.append("/.+")
        elif part.startswith("["):
            parts.append("/[^/]+")
        elif part and part != ".":
            parts.append("/" + re.escape(part))
    return re.fullmatch("".join(parts) or "/", url) is not None


def script_urls(text: str) -> set[str]:
    urls = set()
    for literal in LITERAL.findall(text):
        if literal.startswith("${baseURL}"):
            literal = literal.removeprefix("${baseURL}")
        if literal.startswith("/") and not literal.startswith("//"):
            urls.add(re.split(r"[?#]|\$\{", literal)[0] or "/")
    return urls


def dependencies(root: Path, workflow: Path) -> set[str]:
    data = yaml.safe_load(workflow.read_text())
    pending: list[Path] = [workflow]
    for job in data["jobs"].values():
        for step in job["steps"]:
            app = step.get("working-directory")
            if app not in {"web", "marketing"}:
                continue
            package = root / app
            scripts = re.findall(
                r"(?:scripts|e2e)/[\w./-]+\.(?:ts|mjs)", step.get("run", "")
            )
            for script in scripts:
                source = package / script
                pending.append(source)
                urls = script_urls(source.read_text())
                for page in (package / "app").rglob("page.tsx"):
                    route = page.parent.relative_to(package / "app").as_posix()
                    if any(route_matches(route, url) for url in urls):
                        pending.append(page)
            # Framework/build inputs apply to each workflow that builds this app.
            pending += [
                p
                for p in package.glob("*")
                if p.is_file()
                and (
                    p.name in {"package.json", "bun.lock", "tsconfig.json"}
                    or p.name.startswith(("next.config.", "postcss.config.", "proxy."))
                )
            ]
            if "playwright test" in step.get("run", ""):
                pending.append(package / "playwright.config.ts")

    seen: set[Path] = set()
    while pending:
        path = pending.pop().resolve()
        if path in seen:
            continue
        if not path.is_file():
            raise ValueError(f"missing evidence input: {path.relative_to(root)}")
        seen.add(path)
        relative = path.relative_to(root)
        package = root / relative.parts[0]
        if "app" in relative.parts and path.name == "page.tsx":
            folder = path.parent
            while folder != package:
                pending += [p for p in folder.glob("layout.*") if p.suffix in SOURCE]
                folder = folder.parent
        # Generated fixture pages still use the package's root layout.
        if relative.parts[0] in {"web", "marketing"} and "scripts" in relative.parts:
            pending += list((package / "app").glob("layout.*"))
        if path.suffix not in SOURCE:
            continue
        text = path.read_text()
        for name in IMPORT.findall(text):
            if not name.startswith((".", "@/")):
                continue
            target = package / name[2:] if name.startswith("@/") else path.parent / name
            resolved = resolve_file(target)
            if resolved is None:
                raise ValueError(f"{relative}: unresolved local import {name}")
            pending.append(resolved)
        # Local fonts, public images and locale templates are not JS imports.
        for literal in LITERAL.findall(text):
            if not re.search(r"\.[A-Za-z0-9]+$", literal):
                continue
            target = (
                package / "public" / literal.lstrip("/")
                if literal.startswith("/")
                else path.parent / literal
            )
            if "{{" in literal:
                pattern = re.sub(r"\{\{\w+\}\}", "*", str(target))
                pending += list(Path("/").glob(pattern.lstrip("/")))
            elif "${" not in literal and len(literal.encode()) < 240 and target.is_file():
                pending.append(target)
    return {path.relative_to(root).as_posix() for path in seen}


def problems(root: Path = ROOT) -> list[str]:
    errors = []
    for workflow in sorted((root / ".github/workflows").glob("*-evidence.yml")):
        data = yaml.safe_load(workflow.read_text())
        events = data.get("on", data.get(True, {}))  # YAML 1.1 treats 'on' as true.
        patterns = events["pull_request"]["paths"]
        for path in sorted(dependencies(root, workflow)):
            if not any(matches(path, pattern) for pattern in patterns):
                errors.append(f"{workflow.name}: paths do not cover {path}")
    return errors


if __name__ == "__main__":
    failures = problems()
    for failure in failures:
        logger.error(failure)
    if not failures:
        logger.info("Evidence workflow paths cover their statically resolved inputs")
    raise SystemExit(bool(failures))
