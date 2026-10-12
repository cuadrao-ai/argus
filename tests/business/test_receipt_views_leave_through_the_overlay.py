"""Structural guard: a receipt view leaves the API only through the draft
overlay in ``argus.api.business_drafts``. A router that called
``receipt.summary()``, ``service.search``, ``service.updates``,
``service.overview`` or ``service.inbox`` on its own would show a receipt's
legacy state although a bridge draft is linked, which is what the inbox did
on staging."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

API = Path(__file__).parents[2] / "src" / "argus" / "api"
OVERLAY = API / "business_drafts.py"
BYPASSES = (
    r"\.summary\(\)",
    r"\.detail\(\)",
    r"service\.search\(",
    r"service\.updates\(",
    r"service\.overview\(",
    r"service\.inbox\(",
    r"service\.receipts\(",
)


@pytest.mark.parametrize("pattern", BYPASSES)
def test_no_api_module_but_the_overlay_builds_a_receipt_view(pattern):
    offenders = [
        f"{path.relative_to(API)}:{number}"
        for path in sorted(API.rglob("*.py"))
        if path != OVERLAY
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if re.search(pattern, line)
    ]
    assert offenders == [], (
        f"{pattern} is used outside business_drafts.py; route it through bridged(),"
        f" receipt_summary(), receipt_summaries(), receipt_detail(), search_with_drafts(),"
        f" updates_with_drafts() or overview_with_drafts(): {offenders}"
    )


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
