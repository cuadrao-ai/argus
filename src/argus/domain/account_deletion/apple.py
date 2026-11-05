from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from argus.domain.apple_sign_in.credentials import (
    AppleRevocationPending,
    StoredAppleCredential,
)
from argus.domain.apple_sign_in.credentials_postgres import (
    PostgresAppleCredentialRepository,
)
from argus.domain.apple_sign_in.identity import (
    AppleIdentityUnavailable,
    LinkedAppleIdentity,
    linked_apple_identity,
)


class AccountDeletionAdmissionError(Exception):
    def __init__(self, code: str, status: int = 503) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class AppleDeletionState:
    identity: LinkedAppleIdentity | None
    credential: StoredAppleCredential | None
    unavailable: bool = False


def lock_apple_state(connection: Any, user_id: str) -> tuple[Any, AppleDeletionState]:
    connection.execute("set transaction isolation level read committed")
    user = connection.execute(
        "select raw_app_meta_data from auth.users where id = %s::uuid for update",
        (user_id,),
    ).fetchone()
    try:
        identity = linked_apple_identity(connection, user_id, lock=True)
        unavailable = False
    except AppleIdentityUnavailable:
        identity, unavailable = None, True
    credential = PostgresAppleCredentialRepository.get_on(
        connection, user_id=user_id, lock=True
    )
    return user, AppleDeletionState(identity, credential, unavailable)


def require_admission(state: AppleDeletionState, apple: Any) -> None:
    if state.unavailable:
        raise AccountDeletionAdmissionError("account_deletion_unavailable")
    if state.identity is None:
        return
    row = state.credential
    if row is None or row.apple_subject != state.identity.subject:
        raise AccountDeletionAdmissionError("apple_reauthorization_required", 409)
    if apple is None:
        raise AccountDeletionAdmissionError("account_deletion_unavailable")
    try:
        apple.ensure_readable(row)
    except AppleRevocationPending:
        raise AccountDeletionAdmissionError(
            "apple_reauthorization_required", 409
        ) from None
    except Exception:
        raise AccountDeletionAdmissionError("account_deletion_unavailable") from None
