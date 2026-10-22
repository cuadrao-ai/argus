from __future__ import annotations

import json
from pathlib import Path

import pytest
from argus.domain.business.transfer_mail import render_transfer_mail

CONTEXT = {
    "businessName": "Colmado Muñoz",
    "ownerName": "Ana",
    "targetName": "Rosa",
    "occurredAt": "2026-10-19T01:05:00+00:00",
    "expiresAt": "2026-10-26T01:05:00+00:00",
    "transferId": "4100626b-f480-4249-97bd-04bdc03f1a15",
    "spaceId": "39d12d09-bebe-4992-b6dc-cb1a84d52438",
}
VARIANTS = ("requested", "declined", "acceptedOwner", "acceptedTarget", "withdrawn")


@pytest.fixture(autouse=True)
def origin(monkeypatch):
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://app.example.test")
    monkeypatch.setenv("CUADRAO_EMAIL_ASSET_ORIGIN", "https://images.example.test")


@pytest.mark.parametrize("variant", VARIANTS)
def test_exact_html_and_plain_copy_snapshots(variant):
    expected = json.loads(Path("tests/fixtures/business_transfer_mail.json").read_text())
    assert render_transfer_mail(variant, CONTEXT) == expected[variant]


def test_request_deadline_uses_dominican_calendar_date_and_has_no_accept_token():
    content = render_transfer_mail("requested", CONTEXT)
    assert "La solicitud vence el 25 de octubre de 2026." in content["text"]
    assert "?transfer=" in content["text"]
    assert "/accept" not in content["text"] and "token=" not in content["text"]
    assert "Saludos,\nCuadrao" in content["text"]
    accepted = render_transfer_mail("acceptedOwner", CONTEXT)
    assert "18 de octubre de 2026 a las 9:05 p.\u202fm. (hora de RD)" in accepted["text"]


def test_values_are_escaped_once_and_token_names_inside_values_stay_literal():
    context = CONTEXT | {"ownerName": '<b>__CUADRAO_TARGET_NAME__ & "Ana"</b>'}
    rendered = render_transfer_mail("requested", context)
    assert (
        "&lt;b&gt;__CUADRAO_TARGET_NAME__ &amp; &quot;Ana&quot;&lt;/b&gt;"
        in rendered["html"]
    )
    assert context["ownerName"] in rendered["text"]
    assert context["ownerName"] in rendered["subject"]


@pytest.mark.parametrize("field", ("businessName", "ownerName", "targetName"))
@pytest.mark.parametrize("value", ("", "Ana\nBcc: elsewhere@example.test", "Ana\rtest"))
def test_header_and_body_fields_reject_empty_or_multiline_values(field, value):
    with pytest.raises(ValueError):
        render_transfer_mail("requested", CONTEXT | {field: value})


@pytest.mark.parametrize(
    "value",
    (
        "http://example.test",
        "https://user:pw@example.test",
        "https://example.test/path",
        "https://example.test?q=x",
        "https://example.test#x",
        "https://example.test\n",
    ),
)
def test_asset_origin_cannot_inject_or_redirect_image_paths(monkeypatch, value):
    monkeypatch.setenv("CUADRAO_EMAIL_ASSET_ORIGIN", value)
    with pytest.raises(ValueError):
        render_transfer_mail("requested", CONTEXT)


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("value", (None, "123 Road\nBcc: injected@example.test"))
def test_transactional_mail_ends_with_the_company_line_and_reads_no_postal_address(
    monkeypatch, variant, value
):
    if value is None:
        monkeypatch.delenv("MARKETING_POSTAL_ADDRESS", raising=False)
    else:
        monkeypatch.setenv("MARKETING_POSTAL_ADDRESS", value)
    rendered = render_transfer_mail(variant, CONTEXT)
    assert rendered["text"].endswith("\n\nCuadrao LLC")
    assert ">Cuadrao LLC</p>" in rendered["html"]
    assert "Road" not in rendered["text"] and "Road" not in rendered["html"]
