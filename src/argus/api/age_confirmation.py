import re
from datetime import datetime, timedelta, timezone
from typing import Annotated

from pydantic import BeforeValidator

_RFC3339 = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"
)


AGE_CONFIRMATION_REQUIRED = "age_confirmation_required"
AGE_CONFIRMATION_INVALID = "age_confirmation_invalid"


def parse_age_confirmation(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or _RFC3339.fullmatch(value) is None:
        raise ValueError(AGE_CONFIRMATION_INVALID)
    try:
        confirmed_at = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except (ValueError, OverflowError):
        raise ValueError(AGE_CONFIRMATION_INVALID) from None
    if confirmed_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError(AGE_CONFIRMATION_INVALID)
    return confirmed_at


def age_confirmation_response_code(errors: object) -> str | None:
    if not isinstance(errors, list) or not errors:
        return None
    for error in errors:
        if not isinstance(error, dict):
            return None
        loc = error.get("loc")
        if not loc or loc[-1] != "age_confirmed_at":
            return None
    if all(error.get("type") == "missing" for error in errors):
        return AGE_CONFIRMATION_REQUIRED
    return AGE_CONFIRMATION_INVALID


AgeConfirmation = Annotated[datetime | None, BeforeValidator(parse_age_confirmation)]
