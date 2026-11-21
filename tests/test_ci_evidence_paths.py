"""Evidence triggers cover source-derived inputs without a second path manifest."""

from pathlib import Path

import pytest

from scripts.ci.check_evidence_paths import dependencies, matches, problems, route_matches


def put(root: Path, path: str, text: str = "") -> None:
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text)


def fixture_tree(root: Path) -> Path:
    put(
        root,
        ".github/workflows/sample-evidence.yml",
        """
on:
  pull_request:
    paths:
      - .github/workflows/sample-evidence.yml
      - web/**
jobs:
  synthetic-evidence:
    steps:
      - working-directory: web
        run: bun scripts/sample-evidence.ts
""",
    )
    put(
        root,
        "web/scripts/sample-evidence.ts",
        """
import { fixture } from "../fixtures/data";
await page.goto(`${baseURL}/biz?view=inbox`);
const generated = `import Screen from "@/components/Recovery";`;
""",
    )
    put(root, "web/fixtures/data.ts", 'export { value } from "./nested";')
    put(root, "web/fixtures/nested.ts")
    put(root, "web/app/biz/page.tsx", 'import View from "@/components/View";')
    put(root, "web/components/View.tsx", 'import "./view.css";')
    put(root, "web/components/view.css")
    put(root, "web/components/Recovery.tsx")
    put(root, "web/app/layout.tsx", 'import "./globals.css";')
    put(root, "web/app/globals.css")
    put(root, "web/proxy.ts")
    put(root, "web/package.json", "{}")
    return root / ".github/workflows/sample-evidence.yml"


def test_evidence_workflow_paths_cover_source_inputs():
    assert problems() == []


def test_ci_evidence_follows_route_imports_fixtures_and_generated_pages(tmp_path):
    workflow = fixture_tree(tmp_path)
    found = dependencies(tmp_path, workflow)
    assert {
        "web/fixtures/nested.ts",
        "web/app/biz/page.tsx",
        "web/components/View.tsx",
        "web/components/view.css",
        "web/components/Recovery.tsx",
        "web/app/globals.css",
        "web/app/layout.tsx",
        "web/proxy.ts",
        "web/package.json",
    } <= found
    assert problems(tmp_path) == []
    put(tmp_path, "external/new.ts")
    put(tmp_path, "web/components/View.tsx", 'import value from "../../external/new";')
    assert problems(tmp_path) == [
        "sample-evidence.yml: paths do not cover external/new.ts"
    ]


def test_ci_evidence_catches_new_driven_page_and_unresolved_import(tmp_path):
    fixture_tree(tmp_path)
    put(tmp_path, "web/app/new/page.tsx", 'import value from "../../../external/new";')
    put(tmp_path, "external/new.ts")
    script = tmp_path / "web/scripts/sample-evidence.ts"
    script.write_text(script.read_text() + "\nawait page.goto(`${baseURL}/new`);")
    assert problems(tmp_path) == [
        "sample-evidence.yml: paths do not cover external/new.ts"
    ]
    put(tmp_path, "external/new.ts", 'import value from "./missing";')
    with pytest.raises(ValueError, match="unresolved local import"):
        problems(tmp_path)


def test_ci_evidence_includes_dynamic_locales_fonts_and_assets(tmp_path):
    workflow = fixture_tree(tmp_path)
    put(
        tmp_path,
        "web/app/layout.tsx",
        """
const font = {src: "./fonts/font.woff2"};
const image = "/brand/mark.svg";
const loadPath = "/locales/{{lng}}/{{ns}}.json";
const countLabel = "{{count}}";
""",
    )
    put(tmp_path, "web/app/unrelated.ts")
    assert "web/app/unrelated.ts" not in dependencies(tmp_path, workflow)
    for path in [
        "web/app/fonts/font.woff2",
        "web/public/brand/mark.svg",
        "web/public/locales/en/common.json",
        "web/public/locales/es-419/common.json",
    ]:
        put(tmp_path, path)
        assert path in dependencies(tmp_path, workflow)


@pytest.mark.parametrize(
    "path,pattern,expected",
    [
        ("web/lib/one.ts", "web/lib/*.ts", True),
        ("web/lib/nested/one.ts", "web/lib/*.ts", False),
        ("web/lib/nested/one.ts", "web/lib/**", True),
        ("web/lib/one.ts", "web/**/*.ts", True),
        ("web/one.ts", "web/**/*.ts", True),
        ("src/one.py", "web/**", False),
    ],
)
def test_ci_evidence_path_globs(path, pattern, expected):
    assert matches(path, pattern) is expected


def test_ci_evidence_rejects_unsupported_filter_syntax():
    with pytest.raises(ValueError, match="unsupported"):
        matches("web/app/page.tsx", "!web/**")


@pytest.mark.parametrize(
    "route,url",
    [
        (".", "/"),
        ("biz", "/biz"),
        ("[locale]/[[...slug]]", "/en/contact"),
        ("[locale]/[[...slug]]", "/en"),
        ("(group)/biz", "/biz"),
    ],
)
def test_ci_evidence_route_matching(route, url):
    assert route_matches(route, url)
    assert not route_matches("biz", "/business")
