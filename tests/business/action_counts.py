"""For a drafts-only app, which holds no receipt list: its actions answer
with the counts of a Business that has no rows."""

from __future__ import annotations

from argus.api.routers.business_drafts import counts_after
from argus.domain.business.receipt_activity import aggregate_activity, inbox_counts
from fastapi import FastAPI

NO_ROWS = {**aggregate_activity([]), **inbox_counts([])}


def count_no_rows(app: FastAPI) -> None:
    app.dependency_overrides[counts_after] = lambda: lambda: NO_ROWS
