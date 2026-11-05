"""The Supabase Admin API calls account deletion makes.

Placeholders and the final auth-user delete go through the Admin API only,
never through SQL on auth.users.
"""

from __future__ import annotations

from typing import Any, Protocol

# Long enough to outlive the product; GoTrue takes a Go duration.
PLACEHOLDER_BAN = "876000h"
PLACEHOLDER_DOMAIN = "cuadrao.invalid"


def placeholder_email(token: str) -> str:
    return f"exmiembro+{token}@{PLACEHOLDER_DOMAIN}"


class AuthAdmin(Protocol):
    def create_placeholder(self, *, user_id: str, email: str) -> None:
        """Create a banned, confirmed, passwordless user with that id.
        Must succeed, or report the id already exists, without side effects."""
        ...

    def user_exists(self, user_id: str) -> bool: ...

    def lock_user(self, user_id: str) -> None:
        """Ban the user so no refresh token or sign-in succeeds while the
        deletion run is in flight. Idempotent; a missing user is a no-op."""
        ...

    def delete_user(self, user_id: str) -> None:
        """Delete the auth user. Deleting a user that is already gone is a no-op."""
        ...


class SupabaseAuthAdmin:
    def __init__(self, client: Any) -> None:
        self._admin = client.auth.admin

    def create_placeholder(self, *, user_id: str, email: str) -> None:
        self._admin.create_user(
            {
                "id": user_id,
                "email": email,
                "email_confirm": True,
                # GoTrue sets banned_until = now + this duration. No password
                # and no phone. We send no user metadata; GoTrue's email
                # confirm writes {"email_verified": true} there, and the one
                # email identity holds the random email, the id and the
                # email_verified/phone_verified flags. Nothing personal.
                "ban_duration": PLACEHOLDER_BAN,
                "app_metadata": {"placeholder": True},
                "user_metadata": {},
            }
        )

    def _get(self, user_id: str) -> Any | None:
        try:
            response = self._admin.get_user_by_id(user_id)
        except Exception as exc:  # GoTrue answers 404 as an AuthApiError
            if getattr(exc, "status", None) == 404 or "not found" in str(exc).lower():
                return None
            raise
        return getattr(response, "user", None)

    def user_exists(self, user_id: str) -> bool:
        return self._get(user_id) is not None

    def lock_user(self, user_id: str) -> None:
        if self._get(user_id) is None:
            return
        # GoTrue revokes nothing on a ban, but refuses every refresh and
        # sign-in while banned_until is in the future: the session dies at
        # its access token's expiry, and the API rejects that token sooner
        # through the in-flight run (auth_sessions).
        self._admin.update_user_by_id(user_id, {"ban_duration": PLACEHOLDER_BAN})

    def delete_user(self, user_id: str) -> None:
        if self._get(user_id) is None:
            return
        self._admin.delete_user(user_id)
