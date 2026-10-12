"""Structural guard: a receipt view leaves the API only through the draft
overlay in ``argus.api.business_drafts``. A module that called
``receipt.summary()``, ``receipt.detail()``, ``service.search``,
``service.updates``, ``service.overview``, ``service.inbox`` or
``service.receipts`` on its own would show a receipt's legacy state although
a bridge draft is linked, which is what the inbox did on staging.

The scan is syntactic: every call in ``src/argus`` whose method is one of
those names, read from the parsed tree rather than from lines of text. The
view builders are the zero-argument ``summary()`` and ``detail()``; the
service reads are the five methods called on a receiver named ``service``
(``context.service`` in a router). Two places are exempt on purpose: the
overlay module, which is where the service is read, and the domain package
that defines the views and the service."""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path(__file__).parents[2] / "src" / "argus"
OVERLAY = SOURCE / "api" / "business_drafts.py"
DEFINITIONS = SOURCE / "domain" / "business"
VIEW_BUILDERS = frozenset({"summary", "detail"})
SERVICE_READS = frozenset({"search", "updates", "overview", "inbox", "receipts"})


def _receiver(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _builds_a_view(call: ast.Call) -> bool:
    if not isinstance(call.func, ast.Attribute):
        return False
    method = call.func.attr
    if method in VIEW_BUILDERS:
        return not call.args and not call.keywords
    return method in SERVICE_READS and _receiver(call.func.value) == "service"


def _view_calls(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        f"{path.relative_to(SOURCE)}:{node.lineno}:{node.func.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _builds_a_view(node)
    ]


def test_no_module_but_the_overlay_builds_a_receipt_view():
    offenders = [
        call
        for path in sorted(SOURCE.rglob("*.py"))
        if path != OVERLAY and DEFINITIONS not in path.parents
        for call in _view_calls(path)
    ]
    assert offenders == [], (
        "a receipt view is built outside business_drafts.py; route it through"
        " bridged(), receipt_summary(), receipt_summaries(), receipt_detail(),"
        f" search_with_drafts(), updates_with_drafts() or overview_with_drafts(): {offenders}"
    )


def test_the_overlay_module_is_where_the_service_is_read():
    """The exemption is deliberate: the overlay reads the service's receipts
    (``receipt_summaries``, ``search_with_drafts`` and ``updates_with_drafts``
    all call ``receipts()``) and builds the views it overlays."""
    methods = {call.rsplit(":", 1)[1] for call in _view_calls(OVERLAY)}
    assert {"receipts", "search", "updates", "overview", "summary", "detail"} <= methods


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
    ):
        assert helper in source
