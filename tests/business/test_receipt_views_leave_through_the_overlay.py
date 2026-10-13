"""Structural guard: a receipt view leaves the API only through the draft
overlay in ``argus.api.business_drafts``. A module that reached
``receipt.summary``, ``receipt.detail``, ``service.search``,
``service.updates``, ``service.overview``, ``service.inbox``,
``service.receipts``, ``service.expenses`` or ``service.expense`` on its own
would show a receipt's legacy state although a bridge draft is linked, which
is what the inbox did on staging, or a saved expense with no receipt to open.

The scan reads the parsed tree of every module under ``src/argus``. It flags
any attribute access to those names on a service or a receipt, not only a
direct call: a call with arguments, a bound method kept in a variable and
called later, ``getattr`` with the name as a string, and simple aliases made
in the same function (``s = context.service``, ``for r in
service.receipts(scope)``, a comprehension over them, an index into them).
A service is the name ``service``, any ``.service`` attribute, or an alias of
one; a receipt is the name ``receipt``, what a service's ``receipt``,
``receipts`` or ``inbox`` read returns, or an alias of those. Two places are
exempt on purpose: the overlay module ``argus/api/business_drafts.py``, which
is where the service is read, and the whole ``argus/domain/business`` package,
which defines the views and the service."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).parents[2] / "src" / "argus"
OVERLAY = SOURCE / "api" / "business_drafts.py"
DEFINITIONS = SOURCE / "domain" / "business"
VIEW_BUILDERS = frozenset({"summary", "detail"})
SERVICE_READS = frozenset(
    {"search", "updates", "overview", "inbox", "receipts", "expenses", "expense"}
)
RECEIPT_READS = frozenset({"receipt", "receipts", "inbox"})
SERVICE, RECEIPT = "service", "receipt"


def _getattr_name(node: ast.expr) -> tuple[ast.expr, str] | None:
    """``getattr(x, "name")`` read as the attribute access ``x.name``."""

    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    ):
        return node.args[0], node.args[1].value
    return None


class _Scope:
    """One function body: the aliases it makes and the accesses it flags."""

    def __init__(self) -> None:
        self.roots: dict[str, str] = {}
        self.methods: dict[str, str] = {}
        self.offenses: list[tuple[int, str]] = []

    def root(self, node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            if node.id == SERVICE:
                return SERVICE
            if node.id == RECEIPT:
                return RECEIPT
            return self.roots.get(node.id)
        if isinstance(node, ast.Attribute):
            if node.attr == SERVICE:
                return SERVICE
            if node.attr in RECEIPT_READS and self.root(node.value) == SERVICE:
                return RECEIPT
            return None
        if isinstance(node, ast.Subscript):
            return self.root(node.value)
        if isinstance(node, ast.Call):
            read = _getattr_name(node)
            if read is not None:
                receiver, name = read
                if name == SERVICE:
                    return SERVICE
                if name in RECEIPT_READS and self.root(receiver) == SERVICE:
                    return RECEIPT
                return None
            # What a service's receipt read returns is a receipt (or receipts).
            return RECEIPT if self.root(node.func) == RECEIPT else None
        return None

    def access(self, node: ast.expr) -> tuple[ast.expr, str] | None:
        """An attribute access, spelled with a dot or through ``getattr``."""

        if isinstance(node, ast.Attribute):
            return node.value, node.attr
        return _getattr_name(node)

    def bind(self, target: ast.expr, value: ast.expr) -> None:
        if not isinstance(target, ast.Name):
            return
        access = self.access(value)
        if access is not None:
            receiver, name = access
            root = self.root(receiver)
            if (root == SERVICE and name in SERVICE_READS) or (
                root == RECEIPT and name in VIEW_BUILDERS
            ):
                self.methods[target.id] = name
                return
        root = self.root(value)
        if root is not None:
            self.roots[target.id] = root

    def visit(self, node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(
                child, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)
            ):
                # The element is visited before its generators; bind their targets first.
                for generator in child.generators:
                    self.bind(generator.target, generator.iter)
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    self.bind(target, child.value)
            elif (
                isinstance(child, (ast.AnnAssign, ast.NamedExpr))
                and child.value is not None
            ):
                self.bind(child.target, child.value)
            elif isinstance(child, (ast.For, ast.AsyncFor, ast.comprehension)):
                self.bind(child.target, child.iter)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                method = self.methods.get(child.func.id)
                if method is not None:
                    self.offenses.append((child.lineno, method))
            access = self.access(child)
            if access is not None:
                receiver, name = access
                root = self.root(receiver)
                if (root == SERVICE and name in SERVICE_READS) or (
                    root == RECEIPT and name in VIEW_BUILDERS
                ):
                    self.offenses.append((child.lineno, name))
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                nested = _Scope()
                nested.roots.update(self.roots)
                nested.methods.update(self.methods)
                nested.visit(child)
                self.offenses.extend(nested.offenses)
            else:
                self.visit(child)


def view_offenses(source: str) -> list[tuple[int, str]]:
    """Every place the source reaches a receipt view or a service read on its own."""

    scope = _Scope()
    scope.visit(ast.parse(source))
    return sorted(set(scope.offenses))


def test_no_module_but_the_overlay_builds_a_receipt_view():
    offenders = [
        f"{path.relative_to(SOURCE)}:{line}:{name}"
        for path in sorted(SOURCE.rglob("*.py"))
        if path != OVERLAY and DEFINITIONS not in path.parents
        for line, name in view_offenses(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        "a receipt view is built outside business_drafts.py; route it through"
        " bridged(), receipt_summary(), receipt_summaries(), receipt_detail(),"
        " search_with_drafts(), updates_with_drafts(), overview_with_drafts() or"
        f" expenses_with_receipts(): {offenders}"
    )


@pytest.mark.parametrize(
    "snippet,expected",
    [
        (
            "def f(context):\n    return context.service.search(context.scope, q, 5)\n",
            ["search"],
        ),
        (
            "def f(context):\n    s = context.service\n    return s.search(q)\n",
            ["search"],
        ),
        ("def f(service):\n    return getattr(service, 'updates')(scope)\n", ["updates"]),
        ("def f(receipt):\n    m = receipt.summary\n    return m()\n", ["summary"]),
        ("def f(receipt):\n    return receipt.summary(extra)\n", ["summary"]),
        ("def f(receipt):\n    return receipt.detail\n", ["detail"]),
        (
            "def f(service, scope):\n    for r in service.receipts(scope):\n        yield r.summary()\n",
            ["receipts", "summary"],
        ),
        (
            "def f(service, scope):\n    return [x.detail() for x in service.inbox(scope)]\n",
            ["detail", "inbox"],
        ),
        (
            "def f(service, scope):\n    rows = service.receipts(scope)\n    return rows[0].summary()\n",
            ["receipts", "summary"],
        ),
        (
            "def f(service, scope):\n    one = service.receipt(scope, i)\n    return one.detail()\n",
            ["detail"],
        ),
        (
            "def f(context):\n    return context.service.expense(context.scope, i)\n",
            ["expense"],
        ),
        # Not a Business service or receipt: left alone.
        ("def f(pattern, text):\n    return pattern.search(text)\n", []),
        ("def f(error):\n    return error.detail\n", []),
        ("def f():\n    return financial_accounts_service().search(q, 5)\n", []),
        ("def f(row):\n    return row.summary\n", []),
    ],
)
def test_the_guard_reads_aliases_getattr_and_calls_with_arguments(snippet, expected):
    assert sorted({name for _, name in view_offenses(snippet)}) == sorted(expected)


def test_the_overlay_module_is_where_the_service_is_read():
    """The exemption is deliberate: the overlay reads the service's receipts
    (``receipt_summaries``, ``search_with_drafts`` and ``updates_with_drafts``
    all call ``receipts()``) and builds the views it overlays."""
    names = {name for _, name in view_offenses(OVERLAY.read_text(encoding="utf-8"))}
    assert {
        "receipts",
        "search",
        "updates",
        "overview",
        "expenses",
        "summary",
        "detail",
    } <= names


def test_the_overlay_module_owns_every_helper_the_routers_use():
    source = OVERLAY.read_text()
    for helper in (
        "def bridged(",
        "def receipt_summary(",
        "def receipt_summaries(",
        "def receipt_detail(",
        "def search_with_drafts(",
        "def updates_with_drafts(",
        "def overview_with_drafts(",
        "def expenses_with_receipts(",
    ):
        assert helper in source
