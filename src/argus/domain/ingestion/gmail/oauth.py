"""Google OAuth web-server flow for one Gmail mailbox.

``authorize`` returns Google's consent URL: ``gmail.readonly`` only, offline
access (a refresh token), ``prompt=consent``, incremental authorization, PKCE
S256 and a sealed single-use ``state`` bound to the person (see ``state``).

``callback`` redeems the state, exchanges the code with the PKCE verifier,
refuses a grant without ``gmail.readonly`` (granular consent lets a person
untick it), reads the mailbox address with ``users.getProfile`` and then:

- creates the connection (``external_ref`` = keyed digest of the address,
  ``label`` = masked address, refresh token sealed under the new id); or
- for a mailbox this person already connected, replaces that live
  connection's credential (reconnect), keeping its cursor and freshness; or
- for a mailbox another person connected, refuses without revoking anything,
  because revoking would end that person's grant too.

The access token from the exchange is used for the profile read and dropped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

from loguru import logger

from argus.domain.ingestion.connections import DuplicateConnection, SourceConnection
from argus.domain.ingestion.gmail.client import GmailClient, GmailError
from argus.domain.ingestion.gmail.config import (
    AUTHORIZE_URL,
    SCOPE,
    GmailConfig,
    mailbox_ref,
    masked_label,
)
from argus.domain.ingestion.gmail.failures import TOKEN_REVOKED
from argus.domain.ingestion.gmail.senders import SenderRepository, SenderRule
from argus.domain.ingestion.gmail.state import OAuthStates
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.secrets import SecretBoxUnavailable
from argus.domain.owner_scope import PERSONAL

# Google issued a time-limited grant (refresh_token_expires_in); re-authorizing
# clears it.
ACCESS_TIME_LIMITED = "gmail_access_time_limited"


class ScopeNotGranted(RuntimeError):
    """The person did not allow reading Gmail; nothing was stored."""


class RefreshTokenMissing(RuntimeError):
    """Google issued no refresh token; nothing was stored."""


class MailboxOwnedElsewhere(RuntimeError):
    """This mailbox is connected by a different person."""


@dataclass(frozen=True)
class AuthorizationRequest:
    authorization_url: str
    expires_at: datetime


@dataclass(frozen=True)
class ConnectResult:
    connection: SourceConnection
    created: bool
    senders: list[SenderRule]


class GmailOAuth:
    def __init__(
        self,
        hub: IngestionHub,
        client: GmailClient,
        config: GmailConfig,
        states: OAuthStates,
        senders: SenderRepository,
    ) -> None:
        self.hub = hub
        self.client = client
        self.config = config
        self.states = states
        self.senders = senders

    def authorize(self, *, user_id: str) -> AuthorizationRequest:
        pending = self.states.issue(user_id=user_id)
        query = urlencode(
            {
                "client_id": self.config.client_id,
                "redirect_uri": self.config.redirect_uri,
                "response_type": "code",
                "scope": SCOPE,
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "true",
                "state": pending.state,
                "code_challenge": pending.code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return AuthorizationRequest(f"{AUTHORIZE_URL}?{query}", pending.expires_at)

    def callback(
        self,
        *,
        user_id: str,
        code: str,
        state: str,
        senders: tuple[str, ...] | None,
    ) -> ConnectResult:
        box = self.hub.box
        if box is None:
            raise SecretBoxUnavailable("credential sealing is not configured")
        verifier = self.states.redeem(user_id=user_id, state=state)
        grant = self.client.exchange_code(code=code, verifier=verifier)
        if SCOPE not in grant.scopes:
            # Partial consent: the token cannot read mail. With incremental
            # authorization an earlier gmail.readonly grant would be listed
            # here, so none exists and revoking cannot end a live connection.
            self._discard(grant.refresh_token or grant.access_token)
            raise ScopeNotGranted()
        if grant.refresh_token is None:
            # Not revoked: the grant may back this person's live connection.
            # The unused access token expires on its own within the hour.
            raise RefreshTokenMissing()
        try:
            row, created = self._store(user_id, grant.access_token, grant.refresh_token)
        except MailboxOwnedElsewhere:
            # Never revoke: the grant is the other person's too.
            raise
        except Exception:
            # Nothing stored the new grant (profile refused, Google down, a
            # database failure): release it rather than leave access the
            # person cannot see. Google revokes the whole grant, so a failed
            # reconnect also ends the previous credential of that mailbox;
            # the connection then asks for authorization again.
            self._discard(grant.refresh_token)
            raise
        try:
            return self._configure(row, created, grant.refresh_expires_in, senders)
        except Exception:
            # The grant is stored but the connection is not fully set up (a
            # time-limited grant without its warning, senders not saved).
            # Undo rather than leave a partly applied connection.
            self._undo(user_id, row, created, grant.refresh_token)
            raise

    def _configure(
        self,
        row: SourceConnection,
        created: bool,
        refresh_expires_in: int | None,
        senders: tuple[str, ...] | None,
    ) -> ConnectResult:
        now = self.hub.clock()
        if refresh_expires_in is not None:
            # Not blocking: syncs work until Google ends the grant, then the
            # connection moves to needs_reauth. The person is told ahead.
            row = self.hub.connections.flag_attention(
                connection_id=row.id, code=ACCESS_TIME_LIMITED, now=now
            )
        if senders is not None:
            rules = self.senders.replace(
                user_id=row.user_id, connection_id=row.id, senders=senders, now=now
            )
        else:
            rules = self.senders.list(connection_id=row.id)
        return ConnectResult(row, created, rules)

    def _undo(
        self, user_id: str, row: SourceConnection, created: bool, refresh_token: str
    ) -> None:
        """Release the grant. A new connection is ended and its senders
        forgotten; a reconnected one asks for authorization again, as when the
        store itself fails (Google revokes the whole grant)."""

        self._discard(refresh_token)
        try:
            if created:
                self.hub.connections.disconnect(
                    user_id=user_id, connection_id=row.id, now=self.hub.clock()
                )
                self.senders.delete(connection_id=row.id)
            else:
                self.hub.connections.record_failure(
                    connection_id=row.id,
                    code=TOKEN_REVOKED,
                    status="needs_reauth",
                    now=self.hub.clock(),
                )
        except Exception as exc:
            # The grant is revoked either way; the next sync finds that and
            # asks for authorization again.
            logger.warning(
                "Failed Gmail connection could not be rolled back",
                failure_mode=type(exc).__name__,
            )

    def _store(
        self, user_id: str, access_token: str, refresh_token: str
    ) -> tuple[SourceConnection, bool]:
        box = self.hub.box
        assert box is not None
        profile = self.client.profile(access_token)
        ref = mailbox_ref(profile.email, box)
        live = self.hub.connections.find_live(source="gmail", external_ref=ref)
        mine = [row for row in live if row.user_id == user_id]
        if live and not mine:
            raise MailboxOwnedElsewhere()
        if mine:
            return self._reseal(mine[0], refresh_token), False
        connection_id = str(uuid.uuid4())
        try:
            row = self.hub.connections.create(
                user_id=user_id,
                source="gmail",
                external_ref=ref,
                label=masked_label(profile.email),
                now=self.hub.clock(),
                secret=box.seal(
                    refresh_token, source="gmail", connection_id=connection_id
                ),
                connection_id=connection_id,
                secret_key=box.key_id,
                scope=PERSONAL,
            )
        except DuplicateConnection as duplicate:
            if duplicate.elsewhere:
                # Another person's callback for this mailbox won the insert;
                # the live reference is unique across people.
                raise MailboxOwnedElsewhere() from None
            # This person's concurrent callback won the insert.
            existing = self.hub.connections.get(
                user_id=user_id, connection_id=duplicate.existing_id, scope=PERSONAL
            )
            return self._reseal(existing, refresh_token), False
        return row, True

    def _reseal(self, row: SourceConnection, refresh_token: str) -> SourceConnection:
        """Reconnect: the newest grant replaces the stored one. The old token is
        not revoked: Google revokes the whole grant, which now includes the new
        token too."""

        assert self.hub.box is not None
        return self.hub.connections.set_secret(
            connection_id=row.id,
            secret=self.hub.box.seal(refresh_token, source="gmail", connection_id=row.id),
            status="active",
            now=self.hub.clock(),
            secret_key=self.hub.box.key_id,
        )

    def _discard(self, token: str) -> None:
        try:
            self.client.revoke(token)
        except GmailError as exc:
            logger.info("Unused Google grant could not be revoked", reason=exc.reason)
