"""Fail when the settings catalog and the code disagree.

The catalog is `scripts/ops/settings_catalog.generated.json`. Each row names a setting and its distinct default/reader pairs. Single-reader
rows retain the compact default/owner form.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

CATALOG_PATH = Path("scripts/ops/settings_catalog.generated.json")
MANIFEST_PATH = Path("scripts/ops/staging_env_manifest.json")
NAME = re.compile(r"[A-Z][A-Z0-9_]*")
SKIP_DIRS = {
    ".next",
    "__pycache__",
    "__tests__",
    "coverage",
    "dist",
    "e2e",
    "node_modules",
    "tests",
}
# Documentation and dated evidence are quoted records, not executable Python sources.
PYTHON_SKIP_ROOTS = {"docs"}
SKIP_ENV = {
    "CI",
    "HOME",
    "HOSTNAME",
    "LANG",
    "LOGNAME",
    "OLDPWD",
    "PATH",
    "PWD",
    "SHELL",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONHASHSEED",
    "PYTHONPATH",
    "TEMP",
    "TERM",
    "TMP",
    "TMPDIR",
    "USER",
    "VIRTUAL_ENV",
}
SKIP_PREFIXES = ("ACTIONS_", "GITHUB_", "NODE_", "NPM_", "RUNNER_")


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
    return ast.unparse(node.func) in {
        "os.getenv",
        "getenv",
        "os.environ.get",
        "environ.get",
    }


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
        self.parents: dict[ast.AST, ast.AST] = {}
        self.environ_aliases: set[tuple[ast.AST, str]] = set()
        self.bindings: set[tuple[ast.AST, str]] = set()
        self.tree: ast.AST = ast.Module(body=[], type_ignores=[])

    def add(self, name: str, default: str | None) -> None:
        if is_setting(name):
            self.reads.setdefault(name, []).append(default)

    def scan(self, tree: ast.AST) -> None:
        self.tree = tree
        self.parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                self.bindings.add((self._scope(node), node.id))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                args += [arg for arg in (node.args.vararg, node.args.kwarg) if arg]
                self.bindings.update((node, arg.arg) for arg in args)
        self._constants(tree)
        while True:
            previous = set(self.environ_aliases)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and self._environment_source(node.value):
                    self.environ_aliases.update(
                        (self._scope(target), target.id)
                        for target in node.targets
                        if isinstance(target, ast.Name)
                    )
            if previous == self.environ_aliases:
                break
        self._wrappers(tree)
        self._classes(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                self._call(node)
            elif isinstance(node, ast.Subscript):
                self._subscript(node)
            elif isinstance(node, ast.For):
                self._item_filter(node)

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
            if not isinstance(node, ast.ClassDef) or not any(
                _call_name(base) == "BaseSettings" for base in node.bases
            ):
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
                default = _signature_default(node)
                if default is None:
                    default = next(
                        (
                            self._default(
                                child, _call_default(child, None, self.constants)
                            )
                            for child in ast.walk(node)
                            if isinstance(child, ast.Call) and _is_getenv(child)
                        ),
                        None,
                    )
                self.wrappers[node.name] = default

    def _call(self, node: ast.Call) -> None:
        if self._is_getenv(node):
            self._getenv(node)
            return
        name = _call_name(node.func)
        if name == "setting_value" and node.args:
            suffix = _string_arg(node.args[0], self.constants)
            default = (
                _text(_const(node.args[1], self.constants))
                if len(node.args) > 1
                else None
            )
            if suffix:
                self.add(f"CUADRAO_{suffix}", self._default(node, default))
                self.add(f"ARGUS_{suffix}", self._default(node, default))
            return
        if name in self.wrappers and node.args:
            for target in self._names(node.args[0]):
                self.add(
                    target,
                    self._default(
                        node, _call_default(node, self.wrappers[name], self.constants)
                    ),
                )
            return

    def _getenv(self, node: ast.Call) -> None:
        if not node.args:
            return
        default = self._default(node, _call_default(node, None, self.constants))
        arg = node.args[0]
        names = self._names(arg)
        for text in names:
            self.add(text, default)
        if isinstance(arg, ast.JoinedStr):
            names = _timeout_names(self.root, arg)
            if names is None:
                self.unresolved.append(f"{self.owner}:{getattr(node, 'lineno', 0)}")
                return
            for name in names:
                self.add(name, default)
        elif not names:
            scope = self._scope(arg)
            wrapper_parameter = (
                isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef))
                and scope.name in self.wrappers
                and isinstance(arg, ast.Name)
                and arg.id == scope.args.args[0].arg
            )
            alias_parameter = (
                isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef))
                and scope.name == "setting_value"
                and isinstance(arg, ast.Name)
                and any(
                    isinstance(child, ast.For)
                    and isinstance(child.target, ast.Name)
                    and child.target.id == arg.id
                    and isinstance(child.iter, ast.Call)
                    and _call_name(child.iter.func) == "setting_names"
                    for child in ast.walk(scope)
                )
            )
            if not wrapper_parameter and not alias_parameter:
                self.unresolved.append(
                    f"{self.owner}:{node.lineno} dynamic environment name {ast.unparse(arg)}"
                )

    def _bound(self, scope: ast.AST, name: str) -> bool:
        return (scope, name) in self.bindings

    def _binding_scope(self, node: ast.AST, name: str) -> ast.AST:
        scope = self._scope(node)
        while scope is not self.tree:
            if self._bound(scope, name):
                return scope
            scope = self._scope(scope)
        return self.tree

    def _shadowed(self, node: ast.AST, name: str) -> bool:
        return self._bound(self._binding_scope(node, name), name)

    def _environment(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            scope = self._binding_scope(node, node.id)
            return (scope, node.id) in self.environ_aliases or (
                node.id == "environ" and not self._bound(scope, node.id)
            )
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "environ"
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and not self._shadowed(node, "os")
        )

    def _environment_source(self, node: ast.AST) -> bool:
        if self._environment(node):
            return True
        if isinstance(node, ast.IfExp):
            return self._environment_source(node.body) or self._environment_source(
                node.orelse
            )
        return (
            isinstance(node, ast.Call)
            and _call_name(node.func) == "dict"
            and bool(node.args)
            and self._environment_source(node.args[0])
        )

    def _item_filter(self, node: ast.For) -> None:
        if not (
            isinstance(node.target, ast.Tuple)
            and len(node.target.elts) == 2
            and isinstance(node.target.elts[0], ast.Name)
            and isinstance(node.iter, ast.Call)
            and isinstance(node.iter.func, ast.Attribute)
            and node.iter.func.attr == "items"
            and self._environment(node.iter.func.value)
        ):
            return
        key = node.target.elts[0].id
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Compare)
                and isinstance(child.left, ast.Name)
                and child.left.id == key
            ):
                for operation, value in zip(child.ops, child.comparators, strict=True):
                    if isinstance(operation, (ast.In, ast.NotIn)):
                        for name in self._names(value):
                            self.add(name, None)

    def _is_getenv(self, node: ast.Call) -> bool:
        if isinstance(node.func, ast.Name):
            return node.func.id == "getenv" and not self._shadowed(node, "getenv")
        if not isinstance(node.func, ast.Attribute):
            return False
        if node.func.attr == "get":
            return self._environment(node.func.value)
        return (
            node.func.attr == "getenv"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            and not self._shadowed(node, "os")
        )

    def _default(self, node: ast.AST, default: str | None) -> str | None:
        if default:
            return default
        child = node
        while child in self.parents:
            parent = self.parents[child]
            if isinstance(parent, ast.BoolOp) and isinstance(parent.op, ast.Or):
                for value in parent.values[parent.values.index(child) + 1 :]:
                    fallback = _text(_const(value, self.constants))
                    if fallback is not None:
                        return fallback
                child = parent
            elif isinstance(parent, ast.Attribute) and parent.value is child:
                child = parent
            elif isinstance(parent, ast.Call) and parent.func is child:
                child = parent
            else:
                break
        return default

    def _subscript(self, node: ast.Subscript) -> None:
        if not isinstance(node.ctx, ast.Load) or not self._environment(node.value):
            return
        for text in self._names(node.slice):
            self.add(text, self._default(node, None))

    def _scope(self, node: ast.AST) -> ast.AST:
        while node in self.parents:
            node = self.parents[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                return node
        return self.tree

    def _names(self, node: ast.AST, seen: frozenset[ast.AST] = frozenset()) -> list[str]:
        if node in seen:
            return []
        seen = seen | {node}
        if isinstance(node, ast.Constant):
            return [node.value] if isinstance(node.value, str) else []
        if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
            return [name for child in node.elts for name in self._names(child, seen)]
        if isinstance(node, ast.Starred):
            return self._names(node.value, seen)
        if isinstance(node, ast.IfExp):
            return self._names(node.body, seen) + self._names(node.orelse, seen)
        if isinstance(node, ast.Dict):
            return [name for child in node.values for name in self._names(child, seen)]
        if isinstance(node, ast.Subscript):
            return self._names(node.value, seen)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
        ):
            return self._names(node.func.value, seen)
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "value"
            and isinstance(node.value, ast.Name)
        ):
            enum_names = self._enum_read_names(node)
            if enum_names:
                return enum_names
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            scope = self._scope(node)
            parsers = set()
            for child in ast.walk(scope):
                if isinstance(child, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == node.value.id
                    for target in child.targets
                ):
                    if (
                        isinstance(child.value, ast.Call)
                        and isinstance(child.value.func, ast.Attribute)
                        and child.value.func.attr == "parse_args"
                    ):
                        parsers.add(ast.unparse(child.value.func.value))
            for child in ast.walk(scope):
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "add_argument"
                    and ast.unparse(child.func.value) in parsers
                ):
                    options = [_string_arg(arg, self.constants) for arg in child.args]
                    destination = next(
                        (
                            _string_arg(item.value, self.constants)
                            for item in child.keywords
                            if item.arg == "dest"
                        ),
                        None,
                    )
                    if (
                        destination == node.attr
                        or "--" + node.attr.replace("_", "-") in options
                    ):
                        return [
                            name
                            for keyword in child.keywords
                            if keyword.arg == "default"
                            for name in self._names(keyword.value, seen)
                        ]
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            for statement in self.tree.body:
                if not isinstance(statement, ast.ImportFrom) or not statement.module:
                    continue
                for alias in statement.names:
                    if (alias.asname or alias.name) == node.value.id:
                        return self._import_names(
                            f"{statement.module}.{alias.name}", node.attr
                        )
        if not isinstance(node, ast.Name):
            return []
        scope = self._scope(node)
        parameter = isinstance(
            scope, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) and node.id in {arg.arg for arg in scope.args.args}
        scopes = (
            [scope, self.tree] if scope is not self.tree and not parameter else [scope]
        )
        for current in scopes:
            found = []
            for child in ast.walk(current):
                if self._scope(child) is not current:
                    continue
                if isinstance(child, (ast.Assign, ast.AnnAssign)):
                    targets = (
                        child.targets if isinstance(child, ast.Assign) else [child.target]
                    )
                    if child.value and any(
                        isinstance(target, ast.Name) and target.id == node.id
                        for target in targets
                    ):
                        found.extend(self._names(child.value, seen))
                elif (
                    isinstance(child, (ast.For, ast.comprehension))
                    and isinstance(child.target, ast.Name)
                    and child.target.id == node.id
                ):
                    found.extend(self._names(child.iter, seen))
                elif isinstance(child, ast.ImportFrom) and child.module:
                    for alias in child.names:
                        if (alias.asname or alias.name) == node.id:
                            found.extend(self._import_names(child.module, alias.name))
            if found:
                return found
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parameters = [arg.arg for arg in scope.args.args]
            if node.id in parameters and scope.name not in self.wrappers:
                position = parameters.index(node.id)
                return [
                    name
                    for call in ast.walk(self.tree)
                    if isinstance(call, ast.Call)
                    and _call_name(call.func) == scope.name
                    and len(call.args) > position
                    for name in self._names(call.args[position], seen)
                ]
        return []

    def _enum_read_names(self, node: ast.Attribute) -> list[str]:
        member = node.value.id
        parent = node
        while parent in self.parents:
            parent = self.parents[parent]
            loops = (
                [parent]
                if isinstance(parent, ast.For)
                else parent.generators
                if isinstance(
                    parent, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
                )
                else []
            )
            for loop in loops:
                if (
                    not isinstance(loop.target, ast.Name)
                    or loop.target.id != member
                    or not isinstance(loop.iter, ast.Name)
                ):
                    continue
                if self._binding_scope(node.value, member) is not self._scope(
                    loop.target
                ):
                    return []
                name = loop.iter.id
                if self._shadowed(loop.iter, name):
                    return []
                tree = self.tree
                for statement in self.tree.body:
                    if not isinstance(statement, ast.ImportFrom) or not statement.module:
                        continue
                    for alias in statement.names:
                        if (alias.asname or alias.name) == name:
                            path = (
                                self.root
                                / "src"
                                / Path(*statement.module.split(".")).with_suffix(".py")
                            )
                            if not path.is_file():
                                return []
                            tree, name = ast.parse(path.read_text()), alias.name
                for statement in tree.body:
                    if (
                        isinstance(statement, ast.ClassDef)
                        and statement.name == name
                        and any(_call_name(base) == "Enum" for base in statement.bases)
                    ):
                        return [
                            child.value.value
                            for child in statement.body
                            if isinstance(child, (ast.Assign, ast.AnnAssign))
                            and isinstance(child.value, ast.Constant)
                            and isinstance(child.value.value, str)
                        ]
        return []

    def _import_names(self, module: str, name: str) -> list[str]:
        path = self.root / "src" / Path(*module.split(".")).with_suffix(".py")
        if not path.is_file() or path == self.path:
            return []
        imported = ast.parse(path.read_text())
        for statement in imported.body:
            if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                targets = (
                    statement.targets
                    if isinstance(statement, ast.Assign)
                    else [statement.target]
                )
                if statement.value and any(
                    isinstance(target, ast.Name) and target.id == name
                    for target in targets
                ):
                    return _collection_strings(statement.value)
        return []


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
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8", errors="surrogateescape")
    return [
        root / relative
        for relative in tracked.split("\0")
        if relative
        and Path(relative).parts[0] not in PYTHON_SKIP_ROOTS
        and _kept(Path(relative))
        and (root / relative).is_file()
    ]


def _typescript_files(root: Path) -> list[Path]:
    suffixes = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"}
    return [
        path
        for package in ("web", "marketing")
        for path in (root / package).rglob("*")
        if path.suffix in suffixes
        and _kept(path.relative_to(root))
        and not re.search(r"\.(?:test|spec|d)\.[^.]+$", path.name)
    ]


_TS_TOKEN = re.compile(
    r"""//[^\n]*|/\*.*?\*/|/(?:\\.|\[(?:\\.|[^\]\\])*\]|[^/\\\n])+/[dgimsuvy]*|'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"|`(?:\\.|[^`\\])*`|[A-Za-z_$][\w$]*|\d+(?:\.\d+)?|\?\?|\|\||===|!==|==|!=|=>|[^\s]""",
    re.S,
)


def _ts_tokens(path: Path) -> list[str]:
    return [
        token
        for token in _TS_TOKEN.findall(path.read_text(errors="ignore"))
        if not token.startswith(("//", "/*"))
    ]


def _ts_literal(token: str) -> str | None:
    if token.startswith(("'", '"')):
        return token[1:-1]
    if token in {"true", "false"} or re.fullmatch(r"\d+(?:\.\d+)?", token):
        return token
    return None


def _typescript_env_functions(paths: list[Path]) -> dict[Path, set[str]]:
    functions: dict[Path, set[str]] = {}
    for path in paths:
        tokens = _ts_tokens(path)
        bindings = _ts_aliases(tokens, set())
        for index in range(len(tokens) - 4):
            if tokens[index + 1 : index + 6] != ["(", "process", ".", "env", ")"]:
                continue
            if not _ts_binding("process", index, bindings, True):
                continue
            name = tokens[index]
            for match in re.finditer(
                r"import\s*\{([^}]+)\}\s*from\s*['\"]([^'\"]+)['\"]", path.read_text()
            ):
                for binding in match[1].split(","):
                    parts = binding.strip().split()
                    if not parts or parts[-1] != name:
                        continue
                    if match[2].startswith("@/"):
                        package = next(
                            parent
                            for parent in path.parents
                            if parent.name in {"web", "marketing"}
                        )
                        imported = package / match[2][2:]
                    else:
                        imported = path.parent / match[2]
                    candidates = (
                        [imported]
                        if imported.suffix
                        else [
                            imported.with_suffix(suffix)
                            for suffix in (".ts", ".tsx", ".js", ".mjs")
                        ]
                    )
                    for candidate in candidates:
                        if candidate.is_file():
                            functions.setdefault(candidate.resolve(), set()).add(parts[0])
    return functions


def _ts_binding(
    name: str,
    index: int,
    bindings: list[tuple[str, int, int, bool]],
    default: bool = False,
) -> bool:
    matching = [
        (start, environment)
        for bound, start, end, environment in bindings
        if name == bound and start <= index < end
    ]
    return max(matching, default=(-1, default))[1]


def _ts_aliases(
    tokens: list[str], functions: set[str]
) -> list[tuple[str, int, int, bool]]:
    bindings = []
    for index, token in enumerate(tokens):
        if token == "function" and index + 3 < len(tokens) and tokens[index + 2] == "(":
            depth, end = 1, index + 3
            while end < len(tokens) and depth:
                depth += (tokens[end] == "(") - (tokens[end] == ")")
                end += 1
            parameters = tokens[index + 3 : end - 1]
            start = end
            while start < len(tokens) and tokens[start] != "{":
                start += 1
            end, depth = start + 1, 1
            while end < len(tokens) and depth:
                depth += (tokens[end] == "{") - (tokens[end] == "}")
                end += 1
            parameter_start, nesting = 0, 0
            for offset in range(len(parameters) + 1):
                if (
                    offset == len(parameters)
                    or parameters[offset] == ","
                    and nesting == 0
                ):
                    parameter = parameters[parameter_start:offset]
                    if parameter:
                        direct = any(
                            parameter[i : i + 4] == ["=", "process", ".", "env"]
                            for i in range(len(parameter))
                        )
                        environment = (
                            direct
                            or parameter_start == 0
                            and tokens[index + 1] in functions
                        )
                        bindings.append((parameter[0], start, end, environment))
                    parameter_start = offset + 1
                elif parameters[offset] in {"(", "[", "{", "<"}:
                    nesting += 1
                elif parameters[offset] in {")", "]", "}", ">"}:
                    nesting -= 1
        if token in {"const", "let", "var"} and index + 1 < len(tokens):
            depth, end = 0, index + 2
            while end < len(tokens):
                depth += (tokens[end] == "{") - (tokens[end] == "}")
                if depth < 0:
                    break
                end += 1
            environment = tokens[index + 2 : index + 6] == [
                "=",
                "process",
                ".",
                "env",
            ] and _ts_binding("process", index, bindings, True)
            bindings.append((tokens[index + 1], index, end, environment))
    return bindings


def _ts_default(tokens: list[str], offset: int) -> str | None:
    default = None
    while offset < len(tokens):
        if tokens[offset] == ")":
            offset += 1
        elif tokens[offset : offset + 2] == ["?", "."]:
            offset += 1
        elif tokens[offset : offset + 4] in (
            [".", "trim", "(", ")"],
            [".", "toLowerCase", "(", ")"],
        ):
            offset += 4
        elif tokens[offset] in {"??", "||"} and offset + 1 < len(tokens):
            literal = _ts_literal(tokens[offset + 1])
            if literal is None:
                break
            default = literal
            if default:
                break
            offset += 2
        else:
            break
    return default


def _scan_typescript(
    path: Path,
    root: Path,
    found: dict[str, list[tuple[str | None, str]]],
    functions: set[str],
) -> None:
    owner = path.relative_to(root).as_posix()
    tokens = _ts_tokens(path)
    aliases = _ts_aliases(tokens, functions)
    for index, token in enumerate(tokens):
        offset = index
        if tokens[index : index + 3] == ["process", ".", "env"] and _ts_binding(
            "process", index, aliases, True
        ):
            offset += 3
        elif tokens[index : index + 5] == ["import", ".", "meta", ".", "env"]:
            offset += 5
        elif _ts_binding(token, index, aliases):
            offset += 1
        else:
            continue
        name = None
        if tokens[offset : offset + 1] == ["."] and offset + 1 < len(tokens):
            name = tokens[offset + 1]
            offset += 2
        elif (
            tokens[offset : offset + 1] == ["["]
            and offset + 2 < len(tokens)
            and tokens[offset + 2] == "]"
        ):
            name = _ts_literal(tokens[offset + 1])
            offset += 3
        if not name or not is_setting(name) or tokens[offset : offset + 1] == ["="]:
            continue
        found.setdefault(name, []).append((_ts_default(tokens, offset), owner))


def _owner_rank(item: tuple[str | None, str]) -> tuple[int, str, bool, str]:
    default, owner = item
    return (owner.startswith("scripts/"), owner, default is not None, default or "")


def scan(root: Path) -> tuple[dict[str, tuple[Read, ...]], list[str]]:
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
    typescript = _typescript_files(root)
    env_functions = _typescript_env_functions(typescript)
    for path in typescript:
        _scan_typescript(path, root, found, env_functions.get(path.resolve(), set()))
    chosen = {
        name: tuple(
            Read(default, owner) for default, owner in sorted(set(reads), key=_owner_rank)
        )
        for name, reads in found.items()
    }
    return chosen, unresolved


def _catalog(root: Path) -> tuple[dict[str, tuple[Read, ...]], str | None]:
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
    found: dict[str, tuple[Read, ...]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            return {}, "settings catalog has a row without a name"
        name = row["name"]
        if name in found:
            return {}, f"duplicate setting {name}"
        if "reads" in row:
            if "default" in row or "owner" in row:
                return {}, f"{name} mixes compact and per-reader defaults"
            reads = row["reads"]
        else:
            reads = [row]
        if not isinstance(reads, list) or not reads:
            return {}, f"{name} has no reads"
        parsed = []
        for read in reads:
            if not isinstance(read, dict):
                return {}, f"{name} has an invalid read"
            default, owner = read.get("default"), read.get("owner")
            if default is not None and not isinstance(default, str):
                return {}, f"{name} default must be a string or null"
            if not isinstance(owner, str) or not owner:
                return {}, f"{name} has no owner"
            item = Read(default, owner)
            if item in parsed:
                return {}, f"{name} has a duplicate read"
            parsed.append(item)
        found[name] = tuple(
            sorted(parsed, key=lambda read: _owner_rank((read.default, read.owner)))
        )
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
        found.append(f"missing {name} read by {reads[name][0].owner}")
    for name in sorted(set(listed) - set(reads)):
        found.append(f"orphan {name}")
    for name in sorted(set(reads) & set(listed)):
        if listed[name] != reads[name]:
            found.append(f"reads {name} list={listed[name]!r} code={reads[name]!r}")
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
    rows = []
    for name, items in sorted(reads.items()):
        values = [{"default": item.default, "owner": item.owner} for item in items]
        row = (
            {"name": name, **values[0]}
            if len(values) == 1
            else {"name": name, "reads": values}
        )
        rows.append(row)
    path = root / CATALOG_PATH
    path.write_text(json.dumps({"version": 2, "settings": rows}, indent=2) + "\n")


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
