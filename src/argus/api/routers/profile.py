from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Request, Response
from loguru import logger
from psycopg import connect
from pydantic import ValidationError

from argus.api import state as api_state
from argus.api.dependencies import (
    current_user,
    dev_memory_fallback_enabled,
    problem,
    require_account_capability,
)
from argus.api.documents import NO_STORE
from argus.api.guest_access import (
    AccountContext,
    account_context,
    public_account_access_enabled,
)
from argus.api.profile_images import (
    image_problem,
    picture_urls,
    read_image_upload,
    require_profile_images,
    storage_problem,
)
from argus.api.schemas import AppleIdentity, ProfilePatch, User, UserResponse
from argus.domain.apple_sign_in.identity import LinkedAppleIdentity, linked_apple_identity
from argus.domain.profile_images import (
    InvalidImage,
    ProfileImageStorageUnavailable,
    person,
)
from argus.domain.store import utcnow
from argus.domain.usage_limits import (
    GUEST_CONVERSATION_ALLOWANCE,
    GUEST_FEEDBACK_ALLOWANCE,
    GUEST_SIMULATION_ALLOWANCE,
)

router = APIRouter(prefix="/api/v1", tags=["profile"])


def _user_response(
    user: User, context: AccountContext, apple_identity: LinkedAppleIdentity | None = None
) -> UserResponse:
    return UserResponse(
        user=user,
        apple_identity=AppleIdentity(subject=apple_identity.subject)
        if apple_identity
        else None,
        photo_url=picture_urls("person", [user.id])[user.id],
        account_kind=context.kind,
        guest=(
            {
                "expires_at": context.expires_at,
                "conversation_id": context.conversation_id,
                "conversation_limit": GUEST_CONVERSATION_ALLOWANCE,
                "simulation_limit": GUEST_SIMULATION_ALLOWANCE,
                "feedback_limit": GUEST_FEEDBACK_ALLOWANCE,
            }
            if context.kind == "guest"
            else None
        ),
        capabilities=context.capabilities,
        public_account_access_enabled=public_account_access_enabled(),
    )


def _apple_identity(request: Request, user_id: str) -> LinkedAppleIdentity | None:
    mock_auth = any(
        os.getenv(name, "").strip().lower() == "true"
        for name in ("NEXT_PUBLIC_MOCK_AUTH", "CUADRAO_MOCK_AUTH")
    )
    if mock_auth and api_state.supabase_gateway is None and not api_state.DATABASE_URL:
        return None
    try:
        if not api_state.DATABASE_URL:
            raise RuntimeError("identity_storage_unconfigured")
        with connect(
            api_state.DATABASE_URL,
            connect_timeout=2,
            options="-c statement_timeout=2000 -c default_transaction_read_only=on",
        ) as connection:
            return linked_apple_identity(connection, user_id)
    except Exception:
        raise problem(
            request,
            status_code=503,
            code="apple_identity_unavailable",
            title="Identity unavailable",
            detail="Account identity could not be verified. Try again.",
        ) from None


@router.get("/me", response_model=UserResponse)
def get_me(
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> UserResponse:
    return _me(request, user)


def _me(request: Request, user: User) -> UserResponse:
    context = account_context(request)
    identity = _apple_identity(request, user.id) if context.kind == "registered" else None
    if api_state.supabase_gateway is not None:
        try:
            profile = api_state.supabase_gateway.get_user(user_id=user.id)
            if profile:
                return _user_response(profile, context, identity)
        except Exception as exc:
            if not dev_memory_fallback_enabled():
                raise
            logger.warning(
                "Supabase profile read failed; using dev memory fallback",
                error=str(exc),
                user_id=user.id,
            )
    return _user_response(user, context, identity)


@router.patch("/me", response_model=UserResponse)
def patch_me(
    patch: ProfilePatch,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> UserResponse:
    context = account_context(request)
    require_account_capability(
        request,
        "can_manage_account",
        detail="Sign in to manage a permanent profile.",
        reason="manage_account",
    )
    current = (
        api_state.supabase_gateway.get_user(user_id=user.id)
        if api_state.supabase_gateway is not None
        else api_state.store.users.get(user.id, user)
    )
    if current is None:
        current = user

    data = current.model_dump()
    updates = patch.model_dump(exclude_unset=True)
    updated_fields = sorted(updates)
    data.update(updates)
    if "language" in updates:
        # A saved language is a chosen one; the row keeps that fact beside it.
        language_confirmed = {**data["onboarding"], "language_confirmed": True}
        data["onboarding"] = updates["onboarding"] = language_confirmed
    data["updated_at"] = utcnow()
    try:
        updated = User.model_validate(data)
    except ValidationError as exc:
        raise problem(
            request,
            status_code=422,
            code="invalid_profile_patch",
            title="Invalid Profile Patch",
            detail="The profile update could not be applied.",
            context={"errors": exc.errors()},
        ) from exc

    identity = _apple_identity(request, user.id)
    if api_state.supabase_gateway is not None:
        try:
            # A derived field is not a column; the row stores what it derives from.
            updated = api_state.supabase_gateway.update_user(
                user.id,
                {
                    "id": user.id,
                    **updated.model_dump(mode="json", include=set(updates)),
                    "updated_at": updated.updated_at.isoformat(),
                },
            )
        except Exception as exc:
            if not dev_memory_fallback_enabled():
                raise
            logger.warning(
                "Supabase profile patch failed; using dev memory fallback",
                error=str(exc),
                user_id=user.id,
            )
    api_state.store.users[user.id] = updated
    logger.info(
        "Profile updated",
        user_id=user.id,
        fields=updated_fields,
    )
    return _user_response(updated, context, identity)


_PHOTO_RESPONSES = {
    403: {"description": "`account_conversion_required`: a guest has no profile photo."},
    413: {"description": "`image_too_large`: the picture is over 5 MiB."},
    415: {"description": "`image_media_type_unsupported`: not a JPEG, PNG or WebP."},
    422: {"description": "`image_invalid`: not one still picture of at least 64 pixels on each side and at most 25 million pixels in all (`context.reason`: `undecodable`, `too_small`, `animated`, `too_many_pixels`)."},
    503: {"description": "`profile_images_unavailable` or `profile_image_storage_unavailable`: pictures cannot be served or saved right now."},
}


def _manage_photo(request: Request) -> None:
    require_account_capability(
        request,
        "can_manage_account",
        detail="Sign in to change your profile photo.",
        reason="manage_account",
    )


@router.put("/me/photo", response_model=UserResponse, responses=_PHOTO_RESPONSES)
async def put_my_photo(
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> UserResponse:
    """Replace the person's photo with the raw picture in the body
    (`Content-Type: image/jpeg`, `image/png` or `image/webp`, at most 5 MiB,
    cropped square by the client). It is stored as a 256 px WebP square with
    its metadata dropped. The reply is the `GET /me` document."""

    _manage_photo(request)
    images = require_profile_images(request)
    media_type, content = await read_image_upload(request)
    try:
        images.replace(person(user.id), content, media_type)
    except InvalidImage as error:
        raise image_problem(request, error) from None
    except ProfileImageStorageUnavailable:
        raise storage_problem(request) from None
    return _me(request, user)


@router.delete(
    "/me/photo", status_code=204, responses={k: _PHOTO_RESPONSES[k] for k in (403, 503)}
)
def delete_my_photo(
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> Response:
    """Remove the person's photo; removing an absent photo is a 204 too."""

    _manage_photo(request)
    images = require_profile_images(request)
    try:
        images.remove(person(user.id))
    except ProfileImageStorageUnavailable:
        raise storage_problem(request) from None
    return Response(status_code=204, headers=NO_STORE)
