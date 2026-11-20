"""A support ticket from an owner the delete command refuses.

While transfer and close are off in the app, a person who owns an open Business
has no way to clear the refusal alone, so they ask support instead. The ticket
is the same ``feedback`` row of type ``account_deletion_request`` the old
fallback wrote. One per account: asking again files nothing new. Nothing is
deleted or locked here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

FEEDBACK_TYPE = "account_deletion_request"
SOURCE = "account_settings_business_owner"
MESSAGE = "Account deletion requested by a Business owner."


@dataclass(frozen=True)
class SupportRequest:
    business_ids: list[str]
    # False when this account already had one: the call wrote nothing.
    filed: bool


def file_once(
    connection: Any, user_id: str, business_ids: list[str], context: dict[str, Any]
) -> SupportRequest:
    """``connection`` is inside a transaction, which holds the lock until commit."""

    connection.execute(
        "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"{FEEDBACK_TYPE}:{user_id}",),
    )
    if connection.execute(
        "select 1 from public.feedback where user_id = %s and type = %s"
        " and context->>'source' = %s limit 1",
        (user_id, FEEDBACK_TYPE, SOURCE),
    ).fetchone():
        return SupportRequest(business_ids, filed=False)
    connection.execute(
        "insert into public.feedback(user_id, type, message, context)"
        " values (%s, %s, %s, %s::jsonb)",
        (
            user_id,
            FEEDBACK_TYPE,
            MESSAGE,
            json.dumps({**context, "source": SOURCE, "business_ids": business_ids}),
        ),
    )
    return SupportRequest(business_ids, filed=True)
