import re
from datetime import datetime, timedelta, timezone
from typing import Annotated

from pydantic import BeforeValidator

_RFC3339 = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"
)


def parse_age_confirmation(value: object) -> datetime:
    if not isinstance(value, str) or _RFC3339.fullmatch(value) is None:
        raise ValueError("age_confirmation_required")
    try:
        confirmed_at = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        raise ValueError("age_confirmation_required") from None
    if confirmed_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError("age_confirmation_future")
    return confirmed_at


AgeConfirmation = Annotated[datetime, BeforeValidator(parse_age_confirmation)]
