import pytest
from argus.domain.apple_sign_in.identity import (
    AppleIdentityUnavailable,
    LinkedAppleIdentity,
    parse_linked_apple_identity,
)

from tests.apple_sign_in_support import SUBJECT


def identity(subject=SUBJECT, provider="apple"):
    return {
        "provider": provider,
        "provider_id": subject,
        "identity_data": {"sub": subject},
    }


@pytest.mark.parametrize("rows", [[], [identity(provider="email")]])
def test_only_positive_absence_returns_none(rows):
    assert parse_linked_apple_identity(rows) is None


@pytest.mark.parametrize(
    "rows",
    [
        [identity(), identity("other")],
        [{"provider": "apple", "provider_id": SUBJECT, "identity_data": {}}],
        [
            {
                "provider": "apple",
                "provider_id": "other",
                "identity_data": {"sub": SUBJECT},
            }
        ],
        [identity(" ")],
        [identity("")],
        [identity("a" * 513)],
        [None],
        [{}],
    ],
)
def test_malformed_or_conflicting_identity_is_unavailable(rows):
    with pytest.raises(AppleIdentityUnavailable) as raised:
        parse_linked_apple_identity(rows)
    assert SUBJECT not in str(raised.value)


def test_matching_duplicate_subject_is_unambiguous_and_private():
    linked = parse_linked_apple_identity([identity(), identity()])
    assert linked == LinkedAppleIdentity(SUBJECT)
    assert SUBJECT not in repr(linked)
