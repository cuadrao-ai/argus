"""The settings catalog matches the names the code reads."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from scripts.ci.settings_agreement import Read, problems, scan

ROOT = Path(__file__).resolve().parents[1]


def _tree(tmp_path: Path, source: str, settings: list[dict[str, object]]) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(source)
    catalog = tmp_path / "scripts" / "ops"
    catalog.mkdir(parents=True)
    payload = {"version": 1, "settings": settings}
    (catalog / "settings_catalog.generated.json").write_text(json.dumps(payload) + "\n")
    return tmp_path


def test_a_setting_the_code_reads_and_the_list_lacks_fails(tmp_path: Path) -> None:
    root = _tree(tmp_path, 'import os\nos.getenv("CUADRAO_SAMPLE_FLAG", "false")\n', [])

    assert problems(root) == ["missing CUADRAO_SAMPLE_FLAG read by src/app.py"]


def test_a_listed_setting_nothing_reads_fails(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        "import os\n",
        [{"name": "CUADRAO_UNUSED", "default": None, "owner": "src/app.py"}],
    )

    assert problems(root) == ["orphan CUADRAO_UNUSED"]


def test_the_repository_settings_list_matches_the_code() -> None:
    assert problems(ROOT) == []


@pytest.mark.parametrize(
    ("source", "defaults"),
    [
        ('os.getenv("CUADRAO_SAMPLE")', {"CUADRAO_SAMPLE": None}),
        ('os.getenv("CUADRAO_SAMPLE", "20")', {"CUADRAO_SAMPLE": "20"}),
        ('os.getenv("CUADRAO_SAMPLE", default="20")', {"CUADRAO_SAMPLE": "20"}),
        ('os.environ.get("CUADRAO_SAMPLE", "20")', {"CUADRAO_SAMPLE": "20"}),
        ('os.environ["CUADRAO_SAMPLE"]', {"CUADRAO_SAMPLE": None}),
        (
            'from os import getenv; getenv("CUADRAO_SAMPLE", "20")',
            {"CUADRAO_SAMPLE": "20"},
        ),
        ('from os import environ; environ["CUADRAO_SAMPLE"]', {"CUADRAO_SAMPLE": None}),
        ('NAME = "CUADRAO_SAMPLE"; os.getenv(NAME, "20")', {"CUADRAO_SAMPLE": "20"}),
        ('NAME = "CUADRAO_SAMPLE"; str(NAME)', {}),
        ('CODE_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"; str(CODE_ALPHABET)', {}),
        ('NAMES = ["CUADRAO_SAMPLE"]; str(NAMES)', {}),
        ('NAMES = {"CUADRAO_SAMPLE": "ARGUS_UNUSED"}; str(NAMES)', {}),
        ('os.environ["CUADRAO_SAMPLE"] = "written"', {}),
        ('del os.environ["CUADRAO_SAMPLE"]', {}),
        ('other.environ["CUADRAO_SAMPLE"]', {}),
        ('os.getenv("CUADRAO_SAMPLE") or "20"', {"CUADRAO_SAMPLE": "20"}),
        ('(os.getenv("CUADRAO_SAMPLE") or "20").strip()', {"CUADRAO_SAMPLE": "20"}),
        (
            'os.getenv("CUADRAO_SAMPLE", "").strip().lower() or "sandbox"',
            {"CUADRAO_SAMPLE": "sandbox"},
        ),
        (
            'DEFAULT = 20; os.getenv("CUADRAO_SAMPLE") or DEFAULT',
            {"CUADRAO_SAMPLE": "20"},
        ),
        (
            'os.getenv("CUADRAO_SAMPLE") or os.getenv("ARGUS_SAMPLE") or "20"',
            {"CUADRAO_SAMPLE": "20", "ARGUS_SAMPLE": "20"},
        ),
        ('os.getenv("CUADRAO_SAMPLE", "10") or "20"', {"CUADRAO_SAMPLE": "10"}),
        ('os.getenv("CUADRAO_SAMPLE") and "not-a-default"', {"CUADRAO_SAMPLE": None}),
        (
            'source = os.environ; source.get("CUADRAO_SAMPLE", "20")',
            {"CUADRAO_SAMPLE": "20"},
        ),
        (
            """\
        def read(env=None):
            source = os.environ if env is None else env
            return source.get("CUADRAO_SAMPLE", "20")
        """,
            {"CUADRAO_SAMPLE": "20"},
        ),
        (
            """\
        def read(name, default="20"):
            return os.getenv(name) or default
        value = read("CUADRAO_SAMPLE")
        """,
            {"CUADRAO_SAMPLE": "20"},
        ),
        (
            """\
        def read(name, default="20"):
            return os.getenv(name) or default
        value = read("CUADRAO_SAMPLE", default="30")
        """,
            {"CUADRAO_SAMPLE": "30"},
        ),
        (
            """\
        def read():
            names = ("CUADRAO_SAMPLE", "ARGUS_SAMPLE")
            return [os.getenv(name, "20") for name in names]
        """,
            {"CUADRAO_SAMPLE": "20", "ARGUS_SAMPLE": "20"},
        ),
        (
            """\
        def read():
            for name in ("CUADRAO_SAMPLE", "ARGUS_SAMPLE"):
                value = os.getenv(name, "20")
        """,
            {"CUADRAO_SAMPLE": "20", "ARGUS_SAMPLE": "20"},
        ),
        (
            """\
        class Settings(BaseSettings):
            model_config = SettingsConfigDict(env_prefix="CUADRAO_")
            sample: str = "20"
        """,
            {"CUADRAO_SAMPLE": "20"},
        ),
        (
            """\
        class Settings(BaseSettings):
            sample: str = Field(default="20", validation_alias="CUADRAO_SAMPLE")
        """,
            {"CUADRAO_SAMPLE": "20"},
        ),
        (
            """\
        class Settings(BaseSettings):
            sample: str = Field(default="20", validation_alias=AliasChoices("CUADRAO_SAMPLE", "ARGUS_SAMPLE"))
        """,
            {"CUADRAO_SAMPLE": "20", "ARGUS_SAMPLE": "20"},
        ),
        (
            """\
        class Settings(BaseSettings):
            sample: str = Field(default="20", validation_alias=setting_aliases("SAMPLE"))
        """,
            {"CUADRAO_SAMPLE": "20", "ARGUS_SAMPLE": "20"},
        ),
        (
            """\
        class Response(BaseModel):
            sample: str = Field(default="20", validation_alias="CUADRAO_SAMPLE")
        """,
            {},
        ),
        ('names = setting_names("SAMPLE")', {}),
        (
            'value = setting_value("SAMPLE", "20")',
            {"CUADRAO_SAMPLE": "20", "ARGUS_SAMPLE": "20"},
        ),
    ],
)
def test_python_read_shapes(
    tmp_path: Path, source: str, defaults: dict[str, str | None]
) -> None:
    root = _tree(tmp_path, "import os\n" + dedent(source), [])
    reads, unresolved = scan(root)
    assert unresolved == []
    assert reads == {
        name: (Read(default, "src/app.py"),) for name, default in defaults.items()
    }


@pytest.mark.parametrize("package", ["web", "marketing"])
@pytest.mark.parametrize(
    "relative",
    [
        "next.config.ts",
        "proxy.ts",
        "instrumentation.ts",
        "scripts/run.mjs",
        "src/start.cjs",
        "src/start.mts",
        "src/start.cts",
        "components/item.tsx",
        "app/page.js",
    ],
)
def test_frontend_package_executable_files(
    tmp_path: Path, package: str, relative: str
) -> None:
    path = tmp_path / package / relative
    path.parent.mkdir(parents=True)
    path.write_text('const value = process.env.CUADRAO_SAMPLE ?? "20";\n')
    assert scan(tmp_path) == (
        {"CUADRAO_SAMPLE": (Read("20", f"{package}/{relative}"),)},
        [],
    )


@pytest.mark.parametrize(
    "relative",
    [
        "__tests__/sample.ts",
        "sample.test.ts",
        "sample.spec.tsx",
        "node_modules/sample.ts",
        ".next/sample.js",
        "next-env.d.ts",
        "e2e/sample.ts",
    ],
)
def test_frontend_non_runtime_files_are_excluded(tmp_path: Path, relative: str) -> None:
    path = tmp_path / "web" / relative
    path.parent.mkdir(parents=True)
    path.write_text("const value = process.env.CUADRAO_SAMPLE;\n")
    assert scan(tmp_path) == ({}, [])


@pytest.mark.parametrize(
    ("source", "defaults"),
    [
        ("const value = process.env.CUADRAO_SAMPLE;", {"CUADRAO_SAMPLE": None}),
        (
            'const value = process.env["CUADRAO_SAMPLE"] ?? "20";',
            {"CUADRAO_SAMPLE": "20"},
        ),
        (
            'const value = import.meta.env.CUADRAO_SAMPLE || "20";',
            {"CUADRAO_SAMPLE": "20"},
        ),
        ('const value = process.env.CUADRAO_SAMPLE ??\n "20";', {"CUADRAO_SAMPLE": "20"}),
        (
            'const value = process.env.CUADRAO_SAMPLE ?? "https://example.invalid";',
            {"CUADRAO_SAMPLE": "https://example.invalid"},
        ),
        ("const value = process.env.CUADRAO_SAMPLE ?? 20;", {"CUADRAO_SAMPLE": "20"}),
        (
            'const value = process.env.CUADRAO_SAMPLE === "yes"; const other = nothing ?? "20";',
            {"CUADRAO_SAMPLE": None},
        ),
        (
            "// process.env.CUADRAO_UNUSED\nconst value = process.env.CUADRAO_SAMPLE;",
            {"CUADRAO_SAMPLE": None},
        ),
        ('const example = "process.env.CUADRAO_UNUSED";', {}),
        ('const env = {CUADRAO_UNUSED: "value"}; env.CUADRAO_UNUSED;', {}),
        ('process.env.CUADRAO_UNUSED = "written";', {}),
        (
            "const env = process.env; const value = env.CUADRAO_SAMPLE;",
            {"CUADRAO_SAMPLE": None},
        ),
        (
            'function read(env: NodeJS.ProcessEnv = process.env) { return env.CUADRAO_SAMPLE ?? "20"; }',
            {"CUADRAO_SAMPLE": "20"},
        ),
    ],
)
def test_frontend_read_shapes(
    tmp_path: Path, source: str, defaults: dict[str, str | None]
) -> None:
    path = tmp_path / "web/lib/config.ts"
    path.parent.mkdir(parents=True)
    path.write_text(source)
    assert scan(tmp_path) == (
        {
            name: (Read(default, "web/lib/config.ts"),)
            for name, default in defaults.items()
        },
        [],
    )


@pytest.mark.parametrize("second_default", ["20", "30"])
def test_catalog_preserves_every_reader(tmp_path: Path, second_default: str) -> None:
    root = _tree(tmp_path, 'import os\nos.getenv("CUADRAO_SAMPLE", "20")\n', [])
    (root / "src" / "other.py").write_text(
        f'import os\nos.getenv("CUADRAO_SAMPLE", "{second_default}")\n'
    )
    from scripts.ci.settings_agreement import write_catalog

    write_catalog(root)
    rows = json.loads((root / "scripts/ops/settings_catalog.generated.json").read_text())[
        "settings"
    ]
    assert rows == [
        {
            "name": "CUADRAO_SAMPLE",
            "reads": [
                {"default": "20", "owner": "src/app.py"},
                {"default": second_default, "owner": "src/other.py"},
            ],
        }
    ]
    assert problems(root) == []
    (root / "src" / "other.py").write_text(
        'import os\nos.getenv("CUADRAO_SAMPLE", "40")\n'
    )
    assert problems(root)


@pytest.mark.parametrize(
    "rows",
    [
        [{"name": "CUADRAO_SAMPLE", "default": "20", "owner": "src/app.py"}] * 2,
        [
            {
                "name": "CUADRAO_SAMPLE",
                "default": "20",
                "owner": "src/app.py",
                "reads": [{"default": "20", "owner": "src/app.py"}],
            }
        ],
        [
            {
                "name": "CUADRAO_SAMPLE",
                "reads": [{"default": "20", "owner": "src/app.py"}] * 2,
            }
        ],
        [{"name": "CUADRAO_SAMPLE", "reads": []}],
    ],
)
def test_catalog_rejects_ambiguous_rows(
    tmp_path: Path, rows: list[dict[str, object]]
) -> None:
    root = _tree(tmp_path, 'import os\nos.getenv("CUADRAO_SAMPLE", "20")\n', rows)
    assert problems(root)


@pytest.mark.parametrize("specifier", ["./config", "@/lib/config"])
def test_frontend_environment_parameter_has_a_process_caller(
    tmp_path: Path, specifier: str
) -> None:
    root = tmp_path / "web/lib"
    root.mkdir(parents=True)
    (root / "runtime.ts").write_text(
        f'import {{ config }} from "{specifier}"; config(process.env);'
    )
    (root / "config.ts").write_text(
        'export function config(env: Record<string, string>) { return env.CUADRAO_SAMPLE ?? "20"; }'
    )
    assert scan(tmp_path) == ({"CUADRAO_SAMPLE": (Read("20", "web/lib/config.ts"),)}, [])


def test_frontend_unrelated_environment_parameter_is_not_a_reader(tmp_path: Path) -> None:
    path = tmp_path / "web/lib/config.ts"
    path.parent.mkdir(parents=True)
    path.write_text(
        "export function config(env: NodeJS.ProcessEnv) { return env.CUADRAO_UNUSED; }"
    )
    assert scan(tmp_path) == ({}, [])


def test_python_imported_collection_reaches_a_read(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        """\
import os
from config import NAMES

def configured(name):
    return os.getenv(name, "20")

values = [configured(name) for name in (*NAMES[tier],)]
""",
        [],
    )
    (root / "src/config.py").write_text(
        'NAMES = {"sample": ("CUADRAO_SAMPLE", "ARGUS_SAMPLE")}\nUNUSED = ["CUADRAO_UNUSED"]\n'
    )
    assert scan(root) == (
        {
            name: (Read("20", "src/app.py"),)
            for name in ("CUADRAO_SAMPLE", "ARGUS_SAMPLE")
        },
        [],
    )


def test_python_environment_snapshot_filter(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        """\
import os
NAMES = {"CUADRAO_SAMPLE"}
source = dict(os.environ)
for name, value in source.items():
    if name not in NAMES:
        continue
    str(value)
""",
        [],
    )
    assert scan(root) == ({"CUADRAO_SAMPLE": (Read(None, "src/app.py"),)}, [])


def test_python_environment_alias_does_not_escape_its_function(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        """\
import os

def real():
    source = os.environ
    return source.get("CUADRAO_SAMPLE")

def unrelated():
    source = {"CUADRAO_UNUSED": "not-a-setting"}
    return source.get("CUADRAO_UNUSED")
""",
        [],
    )
    assert scan(root) == ({"CUADRAO_SAMPLE": (Read(None, "src/app.py"),)}, [])


def test_frontend_environment_alias_does_not_escape_its_function(tmp_path: Path) -> None:
    path = tmp_path / "web/lib/config.ts"
    path.parent.mkdir(parents=True)
    path.write_text("""\
function real() { const env = process.env; return env.CUADRAO_SAMPLE; }
function unrelated() { const env = { CUADRAO_UNUSED: "value" }; return env.CUADRAO_UNUSED; }
""")
    assert scan(tmp_path) == ({"CUADRAO_SAMPLE": (Read(None, "web/lib/config.ts"),)}, [])


@pytest.mark.parametrize(
    "expression",
    [
        'value(process.env.CUADRAO_SAMPLE) ?? "https://example.invalid"',
        '(process.env.CUADRAO_SAMPLE ?? "").trim() || "https://example.invalid"',
        'process.env.CUADRAO_SAMPLE?.trim() || "https://example.invalid"',
    ],
)
def test_frontend_transformed_read_fallback(tmp_path: Path, expression: str) -> None:
    path = tmp_path / "web/lib/config.ts"
    path.parent.mkdir(parents=True)
    path.write_text(f"const value = {expression};")
    assert scan(tmp_path) == (
        {"CUADRAO_SAMPLE": (Read("https://example.invalid", "web/lib/config.ts"),)},
        [],
    )


@pytest.mark.parametrize(
    "source",
    [
        'source = os.environ\ndef unrelated(source):\n    return source.get("CUADRAO_UNUSED")\n',
        'def unrelated(os):\n    return os.getenv("CUADRAO_UNUSED")\n',
        'source = os.environ\ndef unrelated():\n    source = {}\n    return source.get("CUADRAO_UNUSED")\n',
    ],
)
def test_python_shadow_bindings_are_not_environment_reads(
    tmp_path: Path, source: str
) -> None:
    root = _tree(tmp_path, "import os\n" + source, [])
    assert scan(root) == ({}, [])


@pytest.mark.parametrize(
    "source",
    [
        "const env = process.env; function unrelated(env: Record<string, string>) { return env.CUADRAO_UNUSED; }",
        "function unrelated(process: { env: Record<string, string> }) { return process.env.CUADRAO_UNUSED; }",
        "const env = process.env; function unrelated() { const env = {}; return env.CUADRAO_UNUSED; }",
    ],
)
def test_frontend_shadow_bindings_are_not_environment_reads(
    tmp_path: Path, source: str
) -> None:
    path = tmp_path / "web/lib/config.ts"
    path.parent.mkdir(parents=True)
    path.write_text(source)
    assert scan(tmp_path) == ({}, [])


def test_python_cli_default_names_an_environment_read(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        """\
import os
import argparse

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url-env", default="ARGUS_APPLY_DATABASE_URL")
    args = parser.parse_args(argv)
    return os.environ.get(args.database_url_env, "")
""",
        [],
    )
    assert scan(root) == ({"ARGUS_APPLY_DATABASE_URL": (Read("", "src/app.py"),)}, [])


def test_python_unknown_environment_name_is_reported(tmp_path: Path) -> None:
    root = _tree(tmp_path, "import os\nos.getenv(selected_name())\n", [])
    reads, unresolved = scan(root)
    assert reads == {}
    assert unresolved == ["src/app.py:2 dynamic environment name selected_name()"]


def test_python_alias_reader_expands_names_at_its_call(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        """\
import os

def setting_value(name, default=None):
    for candidate in setting_names(name):
        value = os.environ.get(candidate)
        if value is not None:
            return value
    return default

value = setting_value("SAMPLE", "20")
""",
        [],
    )
    assert scan(root) == (
        {
            name: (Read("20", "src/app.py"),)
            for name in ("CUADRAO_SAMPLE", "ARGUS_SAMPLE")
        },
        [],
    )
