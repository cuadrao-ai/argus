"""The hub's ``SourceAdapter`` for Gmail: provider revocation and cleanup.

``revoke`` posts the refresh token to Google's revocation endpoint, which ends
the grant. A token Google no longer knows (``invalid_token``) is already
revoked, so that counts as success and is reported as ``already_revoked``;
any other failure raises and the hub reports it while still deleting the
local credential.

``forget`` runs after the local disconnect and deletes the connection's sender
allowlist: it has no use once the mailbox is gone.
"""

from __future__ import annotations

from argus.domain.ingestion.connections import SourceConnection
from argus.domain.ingestion.gmail.client import GmailClient, GmailError
from argus.domain.ingestion.gmail.senders import SenderRepository


class GmailRevocationUnavailable(RuntimeError):
    pass


class GmailAdapter:
    source = "gmail"

    def __init__(self, client: GmailClient, senders: SenderRepository) -> None:
        self.client = client
        self.senders = senders

    def revoke(self, connection: SourceConnection, credential: str | None) -> str | None:
        if not credential:
            raise GmailRevocationUnavailable("no readable refresh token")
        try:
            self.client.revoke(credential)
        except GmailError as exc:
            # Google answers a token it no longer holds with invalid_token
            # (or invalid_grant): already revoked, nothing left to do.
            if exc.status == 400 and {"invalid_token", "invalid_grant"} & set(
                exc.reasons
            ):
                return "already_revoked"
            raise GmailRevocationUnavailable(exc.reason) from None

    def forget(self, connection: SourceConnection) -> None:
        self.senders.delete(connection_id=connection.id)
