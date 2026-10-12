import io
from email.message import EmailMessage

import pytest
from argus.domain.ingestion.documents.config import DocumentExtractionSettings
from argus.domain.ingestion.documents.email_source import parse_email
from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.preparation import prepare_document, validate_source
from PIL import Image


def png() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(stream, format="PNG")
    return stream.getvalue()


def message(
    *attachments: tuple[bytes, str, str, str], body="Cash purchase DOP 150", html=False
):
    msg = EmailMessage()
    msg["From"] = "sender@example.test"
    msg["To"] = "inbox@example.test"
    msg.set_content(body, subtype="html" if html else "plain")
    for content, maintype, subtype, filename in attachments:
        msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)
    return msg.as_bytes()


def test_email_body_and_attachments_are_parsed_without_choosing_an_owner():
    parsed = parse_email(
        message((b"date,amount\n2026-10-09,150", "text", "csv", "receipt.csv"))
    )
    assert parsed.text == "Cash purchase DOP 150\n"
    assert [(p.filename, p.media_type) for p in parsed.attachments] == [
        ("receipt.csv", "text/csv")
    ]


def test_email_html_does_not_fetch_or_keep_scripts():
    parsed = parse_email(
        message(
            body='<p>Compra DOP 150</p><script>steal()</script><img src="http://localhost/private">',
            html=True,
        )
    )
    assert parsed.text == "Compra DOP 150"
    assert not parsed.attachments


def test_email_becomes_one_document_with_its_image_and_csv_pages():
    content = message(
        (png(), "image", "png", "recibo.png"), (b"a,b\n1,2\n", "text", "csv", "rows.csv")
    )
    validate_source(content, "message/rfc822")
    prepared = prepare_document(content, "message/rfc822")
    assert prepared.pages == 3
    assert len(prepared.images) == 1
    assert prepared.text.startswith("Page 1 (email message text):\nCash purchase DOP 150")
    assert "Attachment 'rows.csv', starting at page 3:" in prepared.text
    assert '["1", "2"]' in prepared.text


def test_email_without_text_body_still_counts_the_body_page():
    prepared = prepare_document(
        message((png(), "image", "png", "recibo.png"), body=" "), "message/rfc822"
    )
    assert prepared.pages == 2
    assert prepared.text is None


@pytest.mark.parametrize(
    "content,code",
    [
        (
            message(
                (b"MZevil", "application", "octet-stream", "receipt.pdf.exe"), body=" "
            ),
            "unsupported_email_attachment",
        ),
        (message((b"not an image", "image", "png", "broken.png")), "invalid_document"),
        (b"", "document_empty"),
        (b"no headers at all", "invalid_document"),
    ],
)
def test_unsupported_or_broken_email_content_fails_before_capture(content, code):
    with pytest.raises(DocumentExtractionError, match=code):
        validate_source(content, "message/rfc822")


def test_email_attachments_honor_the_page_budget():
    content = message((png(), "image", "png", "a.png"), (png(), "image", "png", "b.png"))
    with pytest.raises(DocumentExtractionError, match="document_page_limit"):
        prepare_document(
            content, "message/rfc822", DocumentExtractionSettings(max_pages=2)
        )


def test_nested_message_attachments_are_noted_and_never_opened():
    outer = EmailMessage()
    outer["From"] = "sender@example.test"
    outer.set_content("Forwarded")
    inner = EmailMessage()
    inner["From"] = "other@example.test"
    inner.set_content("Inner")
    outer.add_attachment(inner)
    parsed = parse_email(outer.as_bytes())
    assert parsed.text == "Forwarded\n" and not parsed.attachments
    assert [(p.media_type, p.reason) for p in parsed.skipped] == [
        ("message/rfc822", "unsupported")
    ]
    blank = EmailMessage()
    blank["From"] = "sender@example.test"
    blank.set_content(" ")
    blank.add_attachment(inner)
    with pytest.raises(DocumentExtractionError, match="unsupported_email_attachment"):
        prepare_document(blank.as_bytes(), "message/rfc822")


def test_unsupported_and_inline_parts_are_noted_and_never_block_the_readable_parts():
    msg = EmailMessage()
    msg["From"] = "sender@example.test"
    msg.set_content("Factura adjunta")
    msg.add_attachment(png(), maintype="image", subtype="png", filename="recibo.png")
    msg.add_attachment(b"GIF89a", maintype="image", subtype="gif", filename="logo.gif")
    msg.add_attachment(
        b"sig", maintype="application", subtype="pkcs7-signature", filename="smime.p7s"
    )
    msg.add_attachment(
        b"BEGIN:VCALENDAR", maintype="text", subtype="calendar", filename="invite.ics"
    )
    inline = EmailMessage()
    inline.set_content(
        png(),
        maintype="image",
        subtype="png",
        disposition="inline",
        cid="<logo@example.test>",
    )
    msg.attach(inline)
    parsed = parse_email(msg.as_bytes())
    assert [part.filename for part in parsed.attachments] == ["recibo.png"]
    assert sorted((part.filename, part.reason) for part in parsed.skipped) == [
        ("attachment", "inline"),
        ("invite.ics", "unsupported"),
        ("logo.gif", "unsupported"),
        ("smime.p7s", "unsupported"),
    ]
    validate_source(msg.as_bytes(), "message/rfc822")
    prepared = prepare_document(msg.as_bytes(), "message/rfc822")
    assert prepared.pages == 2 and len(prepared.images) == 1
    assert (
        "Parts not read: " in prepared.text
        and "logo.gif (image/gif, unsupported)" in prepared.text
    )


def test_html_body_is_used_only_without_plain_text_and_large_html_is_read_not_refused():
    msg = EmailMessage()
    msg["From"] = "sender@example.test"
    msg.set_content("Texto plano")
    msg.add_alternative("<p>HTML</p>" + "<p>relleno</p>" * 5000, subtype="html")
    parsed = parse_email(msg.as_bytes())
    assert parsed.text == "Texto plano\n"
    only_html = EmailMessage()
    only_html["From"] = "sender@example.test"
    only_html.set_content(
        "<p>Compra DOP 150</p>" + "<!-- " + "x" * (70 * 1024) + " -->", subtype="html"
    )
    assert parse_email(only_html.as_bytes()).text == "Compra DOP 150"
