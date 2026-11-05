"""May account deletion give up on a credential that does not open? (Lane 6, B1)

A credential that does not open looks the same whether it is dead or live for a
process that holds another key (a rolling key rotation, an operator on a stale
environment, a misconfigured key). Account deletion may give up on it only in
the first case: a wrong key must never drop a live Plaid, Gmail or Apple token.

Every sealing path stores ``SecretBox.key_id`` next to the ciphertext
(``secret_key_fingerprint``, migration 20261004090000 section 7). The one check,
for every provider and for Apple before #802's ``discard_unreadable``: the
credential is known dead only when it was sealed under the key this process
holds (the fingerprints match) and it still does not open. A different
fingerprint, or none (sealed before Lane 6), is ``unproven``: nothing is
dropped, the step stays pending, and an operator decides
(``force_complete_step``) once it has been pending for 7 days. No key on this
process is ``unavailable``. Nothing else (seal times, other people's
credentials) counts as evidence.
"""

from __future__ import annotations

import hmac
from typing import Literal

from argus.domain.ingestion.secrets import SecretBox

KeyCheck = Literal["verified", "unproven", "unavailable"]


def check_current_key(box: SecretBox | None, *, key_id: str | None) -> KeyCheck:
    """``key_id`` is the fingerprint stored with the credential that did not
    open (None when it predates the fingerprint)."""

    if box is None:
        return "unavailable"
    if key_id is None or not hmac.compare_digest(str(key_id), box.key_id):
        return "unproven"
    return "verified"
