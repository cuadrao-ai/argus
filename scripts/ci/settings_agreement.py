"""Fail when the settings catalog and the code disagree.

The catalog is `scripts/ops/settings_catalog.generated.json`. Each row is a
name, the code default, and the file that reads it.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

CATALOG_PATH = Path("scripts/ops/settings_catalog.generated.json")
MANIFEST_PATH = Path("scripts/ops/staging_env_manifest.json")
NAME = re.compile(r"[A-Z][A-Z0-9_]*")
SKIP_DIRS = {
    ".next", "__pycache__", "__tests__", "coverage", "dist", "e2e", "node_modules", "tests",
}
SKIP_ENV = {
    "CI", "HOME", "HOSTNAME", "LANG", "LOGNAME", "OLDPWD", "PATH", "PWD", "SHELL",
    "PYTHONDONTWRITEBYTECODE", "PYTHONHASHSEED", "PYTHONPATH", "TEMP", "TERM",
    "TMP", "TMPDIR", "USER", "VIRTUAL_ENV",
}
SKIP_PREFIXES = ("ACTIONS_", "GITHUB_", "NODE_", "NPM_", "RUNNER_")
SETTING_PREFIXES = (
    "ALPACA_", "APP_", "ARGUS_", "CUADRAO_", "DATABASE_", "NEXT_PUBLIC_",
    "OPENROUTER_", "POSTHOG_", "RESEND_", "SUPABASE_",
)


@dataclass(frozen=True)
class Read:
    default: str | None
    owner: str


def is_setting(name: str) -> bool:
    if name in SKIP_ENV or name.startswith(SKIP_PREFIXES):
        return False
    return NAME.fullmatch(name) is not None


def _const(node: ast.AST, constants: dict[str, object]) -> object:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (str, int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node.value, (bool, str)) or node.value is None:
            return node.value
        return None
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _const(node.operand, constants)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return -value
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
        left, right = _const(node.left, constants), _const(node.right, constants)
        if isinstance(left, bool) or isinstance(right, bool):
            return None
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            return left * right
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "SecretStr"
        and node.args
    ):
        return _const(node.args[0], constants)
    return None


def _text(value: object) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return value
    return None


def _field_default(node: ast.AST, constants: dict[str, object]) -> str | None:
    if isinstance(node, ast.Call) and _call_name(node.func) == "Field":
        for keyword in node.keywords:
            if keyword.arg == "default":
                return _text(_const(keyword.value, constants))
        return None
    return _text(_const(node, constants))


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_getenv(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name) and func.id == "getenv":
        return True
    if not isinstance(func, ast.Attribute) or func.attr not in {"getenv", "get"}:
        return False
    value = func.value
    if isinstance(value, ast.Name) and value.id in {"os", "environ"}:
        return True
    return (
        isinstance(value, ast.Attribute)
        and value.attr == "environ"
        and isinstance(value.value, ast.Name)
        and value.value.id == "os"
    )


def _string_arg(node: ast.AST, constants: dict[str, object]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        value = constants.get(node.id)
        return value if isinstance(value, str) else None
    return None


class _Python:
    def __init__(self, path: Path, root: Path) -> None:
        self.path = path
        self.owner = path.relative_to(root).as_posix()
        self.reads: dict[str, list[str | None]] = {}
        self.constants: dict[str, object] = {}
        self.unresolved: list[str] = []
        self.helpers: dict[str, list[str]] = {}
        self.wrappers: dict[str, str | None] = {}
        self.root = root

    def add(self, name: str, default: str | None) -> None:
        if is_setting(name):
            self.reads.setdefault(name, []).append(default)

    def scan(self, tree: ast.AST) -> None:
        self._constants(tree)
        self._wrappers(tree)
        self._classes(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                self._call(node)
            elif isinstance(node, ast.Subscript):
                self._subscript(node)
        self._sequences(tree)
        self._collections(tree)
        self._used_constants(tree)

    def _constants(self, tree: ast.AST) -> None:
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                value = _const(node.value, self.constants)
                if value is None and not isinstance(node.value, ast.Constant):
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Name) and not isinstance(value, ast.AST):
                        self.constants[target.id] = value
            elif (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.value
            ):
                value = _const(node.value, self.constants)
                if not isinstance(value, ast.AST):
                    self.constants[node.target.id] = value

    def _classes(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            prefix = self._prefix(node)
            for statement in node.body:
                if not isinstance(statement, ast.AnnAssign) or not isinstance(
                    statement.target, ast.Name
                ):
                    continue
                if statement.target.id == "model_config":
                    continue
                alias = self._alias(statement)
                default = (
                    _field_default(statement.value, self.constants)
                    if statement.value
                    else None
                )
                if alias:
                    for name in alias:
                        self.add(name, default)
                elif prefix:
                    self.add(f"{prefix}{statement.target.id.upper()}", default)

    def _prefix(self, node: ast.ClassDef) -> str | None:
        for statement in node.body:
            value = statement.value if isinstance(statement, ast.AnnAssign) else None
            if isinstance(statement, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "model_config"
                for target in statement.targets
            ):
                value = statement.value
            if not isinstance(value, ast.Call):
                continue
            for keyword in value.keywords:
                if keyword.arg == "env_prefix" and isinstance(
                    keyword.value, ast.Constant
                ):
                    if isinstance(keyword.value.value, str):
                        return keyword.value.value
        return None

    def _alias(self, statement: ast.AnnAssign) -> list[str]:
        if not isinstance(statement.value, ast.Call):
            return []
        names: list[str] = []
        for keyword in statement.value.keywords:
            if keyword.arg == "validation_alias":
                names.extend(self._alias_expr(keyword.value))
        return names

    def _alias_expr(self, node: ast.AST) -> list[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if not isinstance(node, ast.Call):
            return []
        name = _call_name(node.func)
        if name in {"setting_aliases", "setting_names", "setting_value"} and node.args:
            suffix = _string_arg(node.args[0], self.constants)
            return [f"CUADRAO_{suffix}", f"ARGUS_{suffix}"] if suffix else []
        if name == "AliasChoices":
            found = []
            for arg in node.args:
                text = _string_arg(arg, self.constants)
                if text:
                    found.append(text)
            return found
        return self._helper_alias(node)

    def _helper_alias(self, node: ast.Call) -> list[str]:
        if not isinstance(node.func, ast.Name) or not node.args:
            return []
        suffix = _string_arg(node.args[0], self.constants)
        templates = self.helpers.get(node.func.id, [])
        if suffix is None:
            return []
        return [template.replace("{name}", suffix) for template in templates]

    def _wrappers(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            templates = _alias_templates(node)
            if templates:
                self.helpers[node.name] = templates
            if _passes_parameter_to_getenv(node):
                self.wrappers[node.name] = _signature_default(node)

    def _call(self, node: ast.Call) -> None:
        if _is_getenv(node):
            self._getenv(node)
            return
        name = _call_name(node.func)
        if name in {"setting_aliases", "setting_names", "setting_value"} and node.args:
            suffix = _string_arg(node.args[0], self.constants)
            default = (
                _text(_const(node.args[1], self.constants))
                if len(node.args) > 1
                else None
            )
            if suffix:
                self.add(f"CUADRAO_{suffix}", default)
                self.add(f"ARGUS_{suffix}", default)
            return
        if name in self.wrappers and node.args:
            target = _string_arg(node.args[0], self.constants)
            if target:
                self.add(target, _call_default(node, self.wrappers[name], self.constants))
            return
        if name in self.helpers and node.args:
            suffix = _string_arg(node.args[0], self.constants)
            if suffix:
                for template in self.helpers[name]:
                    self.add(template.replace("{name}", suffix), None)

    def _getenv(self, node: ast.Call) -> None:
        if not node.args:
            return
        default = (
            _text(_const(node.args[1], self.constants)) if len(node.args) > 1 else None
        )
        arg = node.args[0]
        text = _string_arg(arg, self.constants)
        if text:
            self.add(text, default)
            return
        if isinstance(arg, ast.JoinedStr):
            names = _timeout_names(self.root, arg)
            if names is None:
                self.unresolved.append(f"{self.owner}:{getattr(node, 'lineno', 0)}")
                return
            for name in names:
                self.add(name, default)

    def _subscript(self, node: ast.Subscript) -> None:
        value = node.value
        environ = isinstance(value, ast.Attribute) and value.attr == "environ"
        if not environ:
            return
        text = _string_arg(node.slice, self.constants)
        if text:
            self.add(text, None)

    def _sequences(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            bound: dict[str, list[str]] = {}
            for child in ast.walk(node):
                if not isinstance(child, ast.Assign) or len(child.targets) != 1:
                    continue
                target = child.targets[0]
                if isinstance(target, ast.Name):
                    values = _string_sequence(child.value)
                    if values:
                        bound[target.id] = values
            for child in ast.walk(node):
                generators = []
                if isinstance(child, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
                    generators = child.generators
                elif isinstance(child, ast.For):
                    generators = [child]
                for generator in generators:
                    names = _iter_names(generator, bound)
                    if not names or not _reads_iter_name(child, generator):
                        continue
                    default = _getenv_default(child, self.constants)
                    for name in names:
                        self.add(name, default)

    def _used_constants(self, tree: ast.AST) -> None:
        used = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        for key, value in self.constants.items():
            if key in used and isinstance(value, str) and is_setting(value):
                self.add(value, None)

    def _collections(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Set, ast.List, ast.Tuple, ast.Dict)):
                continue
            for text in _collection_strings(node):
                if _prefixed(text) or text in {"APP_ENV", "DATABASE_URL", "ENVIRONMENT"}:
                    self.add(text, None)


def _collection_strings(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [item for elt in node.elts for item in _collection_strings(elt)]
    if isinstance(node, ast.Dict):
        found = []
        for key, value in zip(node.keys, node.values, strict=True):
            if key is not None:
                found.extend(_collection_strings(key))
            if value is not None:
                found.extend(_collection_strings(value))
        return found
    if isinstance(node, ast.Call) and node.args:
        return [item for arg in node.args for item in _collection_strings(arg)]
    return []


def _alias_templates(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    templates = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call) or _call_name(child.func) != "AliasChoices":
            continue
        for arg in child.args:
            if not isinstance(arg, ast.JoinedStr):
                continue
            parts = []
            uses_name = False
            for piece in arg.values:
                if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                    parts.append(piece.value)
                elif isinstance(piece, ast.FormattedValue) and isinstance(
                    piece.value, ast.Name
                ):
                    parts.append("{name}")
                    uses_name = True
                else:
                    uses_name = False
                    break
            if uses_name:
                templates.append("".join(parts))
    return templates


def _passes_parameter_to_getenv(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if not node.args.args:
        return False
    parameter = node.args.args[0].arg
    return any(
        isinstance(child, ast.Call)
        and _is_getenv(child)
        and child.args
        and isinstance(child.args[0], ast.Name)
        and child.args[0].id == parameter
        for child in ast.walk(node)
    )


def _signature_default(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
        if arg.arg == "default" and default is not None:
            return _text(_const(default, {}))
    positional = node.args.args
    defaults = node.args.defaults
    start = len(positional) - len(defaults)
    for arg, default in zip(positional[start:], defaults, strict=True):
        if arg.arg == "default" and default is not None:
            return _text(_const(default, {}))
    return None


def _call_default(
    node: ast.Call, signature: str | None, constants: dict[str, object]
) -> str | None:
    if len(node.args) > 1:
        text = _text(_const(node.args[1], constants))
        if text is not None:
            return text
    for keyword in node.keywords:
        if keyword.arg == "default":
            text = _text(_const(keyword.value, constants))
            if text is not None:
                return text
    return signature


def _string_sequence(node: ast.AST) -> list[str]:
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return []
    values = []
    for elt in node.elts:
        if (
            isinstance(elt, ast.Constant)
            and isinstance(elt.value, str)
            and is_setting(elt.value)
        ):
            values.append(elt.value)
        else:
            return []
    return values


def _iter_names(generator: ast.AST, bound: dict[str, list[str]]) -> list[str]:
    if isinstance(generator, ast.comprehension):
        source = generator.iter
    elif isinstance(generator, ast.For):
        source = generator.iter
    else:
        return []
    if isinstance(source, ast.Name):
        return bound.get(source.id, [])
    return [item for item in _string_sequence(source)]


def _getenv_default(node: ast.AST, constants: dict[str, object]) -> str | None:
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and _is_getenv(child) and len(child.args) > 1:
            return _text(_const(child.args[1], constants))
    return None


def _reads_iter_name(node: ast.AST, generator: ast.AST) -> bool:
    target = (
        generator.target if isinstance(generator, (ast.comprehension, ast.For)) else None
    )
    if not isinstance(target, ast.Name):
        return False
    return any(
        isinstance(child, ast.Call)
        and _is_getenv(child)
        and child.args
        and isinstance(child.args[0], ast.Name)
        and child.args[0].id == target.id
        for child in ast.walk(node)
    )


def _prefixed(text: str) -> bool:
    return any(
        text.startswith(prefix) and len(text) > len(prefix) for prefix in SETTING_PREFIXES
    )


def _timeout_names(root: Path, node: ast.JoinedStr) -> list[str] | None:
    parts = node.values
    if len(parts) != 4:
        return None
    if not (
        isinstance(parts[0], ast.FormattedValue)
        and isinstance(parts[1], ast.Constant)
        and parts[1].value == "_OPENROUTER_"
        and isinstance(parts[2], ast.FormattedValue)
        and isinstance(parts[3], ast.Constant)
        and parts[3].value == "_TIMEOUT_SECONDS"
    ):
        return None
    tasks = _literal_strings(root / "src/argus/llm/openrouter_tasks.py", "OpenRouterTask")
    canonical = set(
        _call_strings(
            root / "src/argus/llm/openrouter_model_env.py", "CANONICAL_TIMEOUT_TASKS"
        )
    )
    if not tasks:
        return None
    return [
        f"{'CUADRAO' if task in canonical else 'ARGUS'}_OPENROUTER_{task.upper()}_TIMEOUT_SECONDS"
        for task in tasks
    ]


def _literal_strings(path: Path, target: str) -> list[str]:
    if not path.is_file():
        return []
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(item, ast.Name) and item.id == target for item in node.targets
        ):
            slice_node = (
                node.value.slice if isinstance(node.value, ast.Subscript) else None
            )
            if isinstance(slice_node, ast.Tuple):
                return [
                    elt.value
                    for elt in slice_node.elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                ]
    return []


def _call_strings(path: Path, target: str) -> list[str]:
    if not path.is_file():
        return []
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(item, ast.Name) and item.id == target for item in node.targets
        ):
            return _collection_strings(node.value)
    return []


def _kept(path: Path) -> bool:
    return not any(part in SKIP_DIRS for part in path.parts)


def _python_files(root: Path) -> list[Path]:
    roots = (root / "src", root / "workflows", root / "scripts" / "ops")
    return [path for base in roots if base.is_dir() for path in base.rglob("*.py") if _kept(path)]


def _typescript_files(root: Path) -> list[Path]:
    folders = (
        "web/app", "web/lib", "web/server", "web/components",
        "marketing/app", "marketing/lib", "marketing/components",
    )
    suffixes = {".ts", ".tsx", ".js", ".mjs"}
    found = []
    for folder in folders:
        base = root / folder
        if base.is_dir():
            found.extend(path for path in base.rglob("*") if path.suffix in suffixes and _kept(path))
    return found


_TS_ENV = re.compile(
    r"""(?:process\.env|import\.meta\.env)(?:\.([A-Z][A-Z0-9_]*)|\[['"]([A-Z][A-Z0-9_]*)['"]\])"""
)
_TS_RECORD = re.compile(r"""(?<![\w.])env\.([A-Z][A-Z0-9_]*)""")
_TS_DEFAULT = re.compile(r"""(?:\?\?|\|\|)\s*['"]([^'"\n]*)['"]""")
_COMMENT = re.compile(r"/\*.*?\*/|//.*?$", re.S | re.M)


def _scan_typescript(
    path: Path, root: Path, found: dict[str, list[tuple[str | None, str]]]
) -> None:
    owner = path.relative_to(root).as_posix()
    text = _COMMENT.sub("", path.read_text(errors="ignore"))
    for match in _TS_ENV.finditer(text):
        name = match.group(1) or match.group(2)
        if not is_setting(name):
            continue
        line_end = text.find("\n", match.start())
        window = text[match.start() : line_end if line_end != -1 else match.end()]
        default_match = _TS_DEFAULT.search(window)
        default = default_match.group(1) if default_match else None
        found.setdefault(name, []).append((default, owner))
    if "env:" in text or "env." in text:
        for match in _TS_RECORD.finditer(text):
            name = match.group(1)
            if is_setting(name):
                found.setdefault(name, []).append((None, owner))


def _owner_rank(item: tuple[str | None, str]) -> tuple[int, str, str]:
    default, owner = item
    return (owner.startswith("scripts/"), owner, default or "")


def scan(root: Path) -> tuple[dict[str, Read], list[str]]:
    found: dict[str, list[tuple[str | None, str]]] = {}
    unresolved: list[str] = []
    for path in _python_files(root):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        reader = _Python(path, root)
        reader.scan(tree)
        unresolved.extend(reader.unresolved)
        for name, defaults in reader.reads.items():
            found.setdefault(name, []).extend((item, reader.owner) for item in defaults)
    for path in _typescript_files(root):
        _scan_typescript(path, root, found)
    chosen: dict[str, Read] = {}
    for name, reads in found.items():
        explicit = [(default, owner) for default, owner in reads if default is not None]
        distinct = sorted({default for default, _owner in explicit})
        if len(distinct) > 1:
            unresolved.append(f"conflict {name} {' '.join(distinct)}")
        pool = explicit or reads
        default, owner = sorted(pool, key=_owner_rank)[0]
        chosen[name] = Read(default, owner)
    return chosen, unresolved


def _catalog(root: Path) -> tuple[dict[str, Read], str | None]:
    path = root / CATALOG_PATH
    if not path.is_file():
        return {}, "settings catalog is missing"
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}, "settings catalog is not json"
    rows = payload.get("settings") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}, "settings catalog has no settings"
    found: dict[str, Read] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            return {}, "settings catalog has a row without a name"
        default = row.get("default")
        owner = row.get("owner")
        if default is not None and not isinstance(default, str):
            return {}, f"{row['name']} default must be a string or null"
        if not isinstance(owner, str) or not owner:
            return {}, f"{row['name']} has no owner"
        found[row["name"]] = Read(default, owner)
    return found, None


def _manifest_names(root: Path) -> list[tuple[str, str]]:
    path = root / MANIFEST_PATH
    if not path.is_file():
        return []
    payload = json.loads(path.read_text())
    names = []
    for label, service in payload.get("services", {}).items():
        for entry in service.get("entries", []):
            names.append((label, entry["name"]))
    return names


def _copy_names(root: Path) -> list[tuple[str, str]]:
    found = []
    render_path = root / "render.yaml"
    if render_path.is_file():
        for match in re.finditer(
            r"(?m)^\s*- key:\s+([A-Z][A-Z0-9_]*)\s*$", render_path.read_text()
        ):
            found.append(("render.yaml", match.group(1)))
    return found


def problems(root: Path) -> list[str]:
    reads, unresolved = scan(root)
    listed, error = _catalog(root)
    found = [f"unresolved {item}" for item in unresolved]
    if error:
        found.append(error)
    for name in sorted(set(reads) - set(listed)):
        found.append(f"missing {name} read by {reads[name].owner}")
    for name in sorted(set(listed) - set(reads)):
        found.append(f"orphan {name}")
    for name in sorted(set(reads) & set(listed)):
        code, row = reads[name], listed[name]
        if row.default != code.default:
            found.append(f"default {name} list={row.default!r} code={code.default!r}")
        if row.owner != code.owner:
            found.append(f"owner {name} list={row.owner} code={code.owner}")
    known = set(listed)
    for label, name in _manifest_names(root):
        if name not in known:
            found.append(f"manifest {label} {name} is not in the settings list")
    for path, name in _copy_names(root):
        if name not in known:
            found.append(f"copy {path} {name} is not in the settings list")
    profile = root / ".github/private-alpha-release-profile.json"
    if profile.is_file() and '"env"' in profile.read_text():
        found.append("release profile still holds environment settings")
    return found


def write_catalog(root: Path) -> None:
    reads, unresolved = scan(root)
    if unresolved:
        raise SystemExit("unresolved dynamic settings: " + ", ".join(unresolved))
    rows = [
        {"name": name, "default": reads[name].default, "owner": reads[name].owner}
        for name in sorted(reads)
    ]
    path = root / CATALOG_PATH
    path.write_text(json.dumps({"version": 1, "settings": rows}, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[2]
    if argv and argv[0] == "--write":
        write_catalog(root)
        return 0
    found = problems(root)
    for item in found:
        print(item, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
