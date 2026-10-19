from __future__ import annotations

from datetime import datetime
from typing import Any

from argus.api.schemas import Language


class SupabaseSignupMixin:
    def signup(
        self,
        email: str,
        password: str,
        captcha_token: str,
        display_name: str | None = None,
        username: str | None = None,
        language: Language = "en",
        guest_signup_handoff: dict[str, str] | None = None,
        age_confirmed_at: datetime | None = None,
    ) -> dict[str, Any]:
        try:
            metadata: dict[str, Any] = {
                "display_name": display_name,
                "username": username,
                "language": language,
            }
            if age_confirmed_at is not None:
                metadata["age_confirmed_at"] = age_confirmed_at.isoformat()
            if guest_signup_handoff is not None:
                metadata["argus_guest_signup"] = guest_signup_handoff
            response = self._auth().sign_up(
                {
                    "email": email,
                    "password": password,
                    "options": {
                        "data": metadata,
                        "captcha_token": captcha_token,
                    },
                }
            )
            if not response.user:
                raise RuntimeError("Signup failed: No user returned.")
            return response.model_dump(mode="json")
        except Exception as e:
            raise RuntimeError(f"Signup failed: {e}") from e

    def record_age_confirmation(self, user_id: str, confirmed_at: datetime) -> None:
        (
            self.client.table("profiles")
            .update({"age_confirmed_at": confirmed_at.isoformat()})
            .eq("id", user_id)
            .is_("age_confirmed_at", "null")
            .execute()
        )
