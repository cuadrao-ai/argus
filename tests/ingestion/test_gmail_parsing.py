"""Gmail parsing without trust: MIME limits, inert HTML, attachment policy,
sender allowlist rules and Gmail's own sender authentication."""

import pytest
from argus.domain.ingestion.gmail import attachments as files
from argus.domain.ingestion.gmail.authenticity import sender_authenticated
from argus.domain.ingestion.gmail.html_text import html_to_text
from argus.domain.ingestion.gmail.mime import MAX_PARTS, AttachmentPart, parse_message
from argus.domain.ingestion.gmail.senders import (
    InvalidSender,
    SenderRule,
    from_address,
    matches,
    normalize_sender,
    normalize_senders,
    sender_query,
)

from tests.ingestion.gmail_mailbox import (
    BANK,
    INJECTION,
    NOW,
    PDF_BYTES,
    alert_en,
    alert_es,
    auth_results,
    b64,
    malicious,
)


def test_plain_text_and_encoded_headers_are_decoded():
    mail = alert_es()
    mail.subject = "=?utf-8?q?Alerta_de_consumo_=C3=A1?="
    email = parse_message(mail.full(1))
    assert email.subject == "Alerta de consumo á"
    assert email.sender == f"alertas@{BANK}" and email.sender_domain == BANK
    assert "RD$ 1,250.00" in email.text
    assert email.received_at.tzinfo is not None and email.received_at < NOW
    assert email.attachments == ()


def test_html_only_message_becomes_text():
    email = parse_message(alert_en().full(1))
    assert email.text == (
        "SYNTHETIC. A purchase of USD 42.10 at FICTIONAL COFFEE was authorized "
        "on Sep 28, 2026."
    )


def test_hostile_html_keeps_only_visible_text_and_fetches_nothing():
    text = html_to_text(malicious().html or "")
    assert "fetch(" not in text and "alert(" not in text and "color:red" not in text
    assert "exfil" not in text and "tracker" not in text and "frame text" not in text
    assert "(hidden)" not in text
    # Visible injection text survives only as inert words.
    assert INJECTION in text and "SYNTHETIC visible line." in text


@pytest.mark.parametrize(
    "markup",
    [
        "<div hidden>secret</div>shown",
        '<span aria-hidden="true">secret</span>shown',
        '<p style="VISIBILITY : hidden">secret</p>shown',
        "<template><p>secret</p></template>shown",
        "<script>var a = '</div>secret';</script>shown",
        "<div style='display:none'><div><br>secret</div></div>shown",
        # A stray end tag of another element cannot end the hidden region.
        "<div hidden></p></span>secret</div>shown",
        "<div hidden><div></div>secret</div>shown",
        "<section hidden><div>secret</section>shown",
    ],
)
def test_hidden_markup_is_dropped(markup):
    assert html_to_text(markup) == "shown"


def test_an_unclosed_hidden_element_hides_everything_after_it():
    assert html_to_text("<p>visible</p><div hidden>secret<p>more secret") == "visible"


def test_unknown_or_bytes_codecs_fall_back_to_utf8():
    message = alert_es().full(1)
    leaf = message["payload"]["parts"][0]["parts"][0]
    leaf["headers"] = [
        {"name": "Content-Type", "value": "text/plain; charset=zlib_codec"}
    ]
    assert "RD$" in parse_message(message).text
    leaf["headers"] = [{"name": "Content-Type", "value": "text/plain; charset=nope-42"}]
    assert "RD$" in parse_message(message).text


def test_part_tree_is_bounded():
    leaf = {"partId": "x", "mimeType": "text/plain", "headers": [],
            "body": {"size": 1, "data": b64(b"x")}}  # fmt: skip
    message = alert_es().full(1)
    message["payload"]["parts"] = [dict(leaf) for _ in range(MAX_PARTS + 5)]
    assert parse_message(message).parts_truncated
    deep = dict(leaf)
    for _ in range(12):
        deep = {"partId": "d", "mimeType": "multipart/mixed", "headers": [],
                "body": {"size": 0}, "parts": [deep]}  # fmt: skip
    message["payload"] = {**message["payload"], "parts": [deep]}
    assert parse_message(message).parts_truncated


def test_attachments_are_described_from_metadata_before_any_download():
    email = parse_message(malicious().full(1))
    assert [(a.part_id, a.media_type, a.filename) for a in email.attachments] == [
        ("1", "application/x-msdownload", "payload.exe"),
        ("2", "application/pdf", "not-really.pdf"),
    ]
    decisions = files.admissible(email.attachments)
    assert [d.skip for d in decisions] == ["media_type", None]


def test_attachment_policy_caps_size_count_and_checks_signatures():
    big = AttachmentPart("1", "application/pdf", files.MAX_ATTACHMENT_BYTES + 1, "a.pdf")
    empty = AttachmentPart("2", "text/csv", 0, "b.csv")
    many = tuple(AttachmentPart(str(i), "image/png", 10, None) for i in range(12))
    skips = [d.skip for d in files.admissible((big, empty, *many))]
    assert skips[:2] == ["too_large", "empty"]
    assert skips[2:].count(None) == files.MAX_ATTACHMENTS and skips[-1] == "limit"
    pdf = AttachmentPart("3", "application/pdf", len(PDF_BYTES), "s.pdf")
    ref = files.reference("m1", pdf, PDF_BYTES)
    assert ref.external_id == "m1:3" and ref.size_bytes == len(PDF_BYTES)
    assert len(ref.sha256) == 64 and ref.media_type == "application/pdf"
    assert files.reference("m1", pdf, b"MZ fake") == "signature"
    csv = AttachmentPart("4", "text/csv", 5, "x.csv")
    assert files.reference("m1", csv, b"a\x00b") == "signature"


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("Alertas@Banco-Ejemplo.TEST ", "alertas@banco-ejemplo.test"),
        ("@banco-ejemplo.test", "banco-ejemplo.test"),
        ("mail.card-example.test", "mail.card-example.test"),
        ("a+b_c%d@x-y.test", "a+b_c%d@x-y.test"),
    ],
)
def test_senders_normalize(raw, normalized):
    assert normalize_sender(raw) == normalized


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "bank",
        "x OR in:anywhere",
        "a@b.test) OR (c",
        "from:x.test",
        '"quoted"@x.test',
        "a..b@x.test",
        "-bad.test",
        "bad-.test",
        "ex ample.test",
        "a@b@c.test",
        "x" * 300 + ".test",
    ],
)
def test_senders_that_could_inject_query_operators_are_refused(raw):
    with pytest.raises(InvalidSender):
        normalize_sender(raw)


def test_sender_list_is_deduplicated_and_bounded():
    assert normalize_senders(["B.test", "b.test", "a.test"]) == ("a.test", "b.test")
    with pytest.raises(InvalidSender):
        normalize_senders([f"s{i}.test" for i in range(21)])


def test_matching_is_exact_address_or_domain_and_subdomains():
    rules = [SenderRule("alerts@card-example.test", NOW), SenderRule(BANK, NOW)]
    assert matches("alerts@card-example.test", rules) is rules[0]
    assert matches("promo@card-example.test", rules) is None
    assert matches(f"estados@mail.{BANK}", rules) is rules[1]
    assert matches(f"alertas@{BANK}.evil.test", rules) is None
    assert matches(f"alertas@x{BANK}", rules) is None
    assert matches(None, rules) is None


def test_from_header_parsing_refuses_ambiguous_senders():
    assert (
        from_address('"Banco, Ejemplo" <A@Banco-Ejemplo.test>') == "a@banco-ejemplo.test"
    )
    assert from_address("a@x.test, b@y.test") is None
    # Defects or parser disagreement: no sender rather than a guess.
    assert from_address("Bank <a@bank.test") is None
    assert from_address("alerts@bank.test <evil@x.test>") is None
    assert from_address("a@bank.test@evil.test") is None
    assert from_address("Bank <a@bank.test>, ") is None
    assert from_address('"a@bank.test" <evil@x.test>') == "evil@x.test"
    assert from_address("no address here") is None
    assert from_address(None) is None


def test_query_is_built_from_the_allowlist_only():
    assert sender_query(("b.test", "a@c.test"), newer_than_days=90) == (
        "from:(a@c.test OR b.test) newer_than:90d"
    )


def _auth(value: str) -> list[tuple[str, str]]:
    return [("Authentication-Results", value)]


def test_gmail_authentication_results_decide_sender_authenticity():
    assert sender_authenticated(_auth(auth_results(BANK)), BANK)
    assert sender_authenticated(_auth(auth_results(f"mail.{BANK}")), f"mail.{BANK}")
    assert not sender_authenticated(_auth(auth_results(BANK, passed=False)), BANK)
    # Signed by a different domain than the From domain.
    assert not sender_authenticated(_auth(auth_results("other.test")), BANK)
    # Only Gmail's own topmost header counts; a sender-added "pass" below it
    # or a header from another server does not.
    forged = [
        ("Authentication-Results", auth_results(BANK, passed=False)),
        ("Authentication-Results", f"mx.google.com; dmarc=pass header.from={BANK}"),
    ]
    assert not sender_authenticated(forged, BANK)
    assert not sender_authenticated(
        _auth(f"evil.test; dmarc=pass header.from={BANK}"), BANK
    )
    assert not sender_authenticated([], BANK)
    assert sender_authenticated(
        _auth(f"mx.google.com; dkim=pass (good sig) header.d={BANK}"), f"x.{BANK}"
    )
