from uuid import uuid4

import pytest
from argus.api.routers.whatsapp import LinkCodeRequest
from pydantic import ValidationError


@pytest.mark.parametrize(
    "extra", ["owner_id", "space_id", "sender_link_id", "grant_id", "route"]
)
def test_owner_command_cannot_supply_authority_or_route(extra):
    with pytest.raises(ValidationError):
        LinkCodeRequest.model_validate(
            {
                "disclosure_token": "a" * 64,
                extra: str(uuid4()),
            }
        )


@pytest.mark.parametrize("token", ["", "a" * 63, "A" * 64, None, 1])
def test_disclosure_token_requires_exact_digest(token):
    with pytest.raises(ValidationError):
        LinkCodeRequest(disclosure_token=token)
