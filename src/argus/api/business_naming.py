from fastapi import Request

from argus.api.business_spaces import space_missing_problem
from argus.api.dependencies import problem
from argus.api.documents import NO_STORE
from argus.domain.business.spaces import SpaceStore


def require_business_name(request: Request, spaces: SpaceStore, space_id: str) -> None:
    space = spaces.get(space_id)
    if space is None:
        raise space_missing_problem(request)
    if space.name_required:
        raise problem(
            request,
            status_code=409,
            code="business_name_required",
            title="Conflict",
            detail="Save the Business name before continuing.",
            headers=NO_STORE,
        )
