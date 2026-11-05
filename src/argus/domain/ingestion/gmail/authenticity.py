"""Was the ``From`` domain authenticated by Gmail's own receiving server?

An allowlisted address in ``From`` is trivially forged, and a forged "bank
alert" must not become an import draft. Gmail prepends one
``Authentication-Results`` header (authserv-id ``mx.google.com``, RFC 8601) to
every message it receives; a sender can add its own copies below it, so only
the topmost header is read, and only when Gmail wrote it.

The message counts as authenticated when that header reports ``dmarc=pass``
for the ``From`` domain, or ``dkim=pass`` with a signing domain aligned (equal
or parent/child) with it. This parses a structured header; it does not judge
what the message says. Messages that fail are skipped and counted, never
silently imported.
"""

from __future__ import annotations

GMAIL_AUTHSERV_ID = "mx.google.com"


def _without_comments(value: str) -> str:
    out: list[str] = []
    depth = 0
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif not depth:
            out.append(char)
    return "".join(out)


def _aligned(signing: str, sender: str) -> bool:
    signing = signing.strip().lower().lstrip("@").rpartition("@")[2]
    sender = sender.lower()
    if not signing or "." not in signing:
        return False
    return (
        signing == sender
        or sender.endswith("." + signing)
        or signing.endswith("." + sender)
    )


def sender_authenticated(
    headers: list[tuple[str, str]], sender_domain: str | None
) -> bool:
    if not sender_domain:
        return False
    topmost = next((v for k, v in headers if k.lower() == "authentication-results"), None)
    if topmost is None:
        return False
    sections = [s.strip() for s in _without_comments(topmost).split(";")]
    if not sections or sections[0].split()[:1] != [GMAIL_AUTHSERV_ID]:
        return False
    for section in sections[1:]:
        tokens = section.split()
        if not tokens or "=" not in tokens[0]:
            continue
        method, _, result = tokens[0].lower().partition("=")
        if result != "pass":
            continue
        properties = dict(token.split("=", 1) for token in tokens[1:] if "=" in token)
        if method == "dmarc" and _aligned(
            properties.get("header.from", ""), sender_domain
        ):
            return True
        if method == "dkim" and any(
            _aligned(properties.get(key, ""), sender_domain)
            for key in ("header.d", "header.i")
        ):
            return True
    return False
