"""Provider credentials sealed at rest and bound to their connection."""

import base64
import hashlib
import hmac
import os

import pytest
from argus.domain.ingestion.secrets import (
    KEY_ENV,
    SecretBox,
    SecretBoxUnavailable,
    SecretUnreadable,
)


def box() -> SecretBox:
    return SecretBox(os.urandom(32))


def test_round_trip_and_no_plaintext_in_envelope():
    sealer = box()
    sealed = sealer.seal("access-sandbox-abc", source="plaid", connection_id="c1")
    assert b"access-sandbox-abc" not in sealed
    assert sealer.open(sealed, source="plaid", connection_id="c1") == "access-sandbox-abc"


def test_envelope_copied_to_another_connection_does_not_open():
    sealer = box()
    sealed = sealer.seal("token", source="plaid", connection_id="c1")
    with pytest.raises(SecretUnreadable):
        sealer.open(sealed, source="plaid", connection_id="c2")
    with pytest.raises(SecretUnreadable):
        sealer.open(sealed, source="gmail", connection_id="c1")
    with pytest.raises(SecretUnreadable):
        box().open(sealed, source="plaid", connection_id="c1")
    with pytest.raises(SecretUnreadable):
        sealer.open(b"\x02" + sealed[1:], source="plaid", connection_id="c1")


def test_key_comes_from_env_and_absence_keeps_connectors_off(monkeypatch):
    monkeypatch.delenv(KEY_ENV, raising=False)
    with pytest.raises(SecretBoxUnavailable):
        SecretBox.from_env()
    monkeypatch.setenv(KEY_ENV, "not base64!!")
    with pytest.raises(SecretBoxUnavailable):
        SecretBox.from_env()
    monkeypatch.setenv(KEY_ENV, base64.urlsafe_b64encode(b"short").decode())
    with pytest.raises(SecretBoxUnavailable):
        SecretBox.from_env()
    monkeypatch.setenv(
        KEY_ENV, base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")
    )
    assert SecretBox.from_env().seal("x", source="gmail", connection_id="c")


def test_digest_is_keyed_and_purpose_separated():
    first, second = box(), box()
    value = "jane@example.test"
    assert first.digest(value, purpose="gmail") == first.digest(value, purpose="gmail")
    assert first.digest(value, purpose="gmail") != first.digest(value, purpose="other")
    assert first.digest(value, purpose="gmail") != second.digest(value, purpose="gmail")
    assert value not in first.digest(value, purpose="gmail")


def test_key_id_names_the_key_without_revealing_it():
    """Stored next to every ciphertext (Lane 6, Priya B1): the same key gives
    the same id, another key another one, and it is neither the key nor a
    digest of it that any other purpose produces."""
    raw = os.urandom(32)
    first, again, other = SecretBox(raw), SecretBox(raw), box()
    assert first.key_id == again.key_id != other.key_id
    assert len(first.key_id) == 32 and set(first.key_id) <= set("0123456789abcdef")
    assert raw.hex()[:32] != first.key_id
    assert first.key_id not in first.digest("argus-ingestion-key-id:v1", purpose="x")


def test_key_id_uses_the_versioned_hmac_contract():
    raw = os.urandom(32)
    expected = hmac.new(raw, b"argus-ingestion-key-id:v1", hashlib.sha256).hexdigest()[
        :32
    ]
    assert SecretBox(raw).key_id == expected
    assert SecretBox(raw).key_id != hashlib.sha256(raw).hexdigest()[:32]
