"""Held lifecycle templates render queued facts without transport calls."""

import pytest
from argus.domain.business.close_mail import render_close_mail


@pytest.fixture
def context():
    return {
        "businessName": "Tienda <Río> & __CUADRAO_OWNER_NAME__",
        "ownerName": "Ana <Rosa>",
        "closedAt": "2026-10-18T02:00:01+00:00",
        "purgeAt": "2026-11-19T02:03:07+00:00",
        "reopenPath": "/biz?lifecycle=manage&business=4fd88ea2-b7b4-4943-b399-664cf3bf9756",
    }


@pytest.mark.parametrize("kind", ["owner_closed", "purge_reminder", "member_reopened"])
@pytest.mark.parametrize("locale", ["es-419", "en"])
def test_new_templates_use_queued_facts_and_one_canonical_footer(
    context, monkeypatch, kind, locale
):
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://app.example.test")
    rendered = render_close_mail(context, kind=kind, locale=locale)
    assert context["businessName"] in rendered["subject"]
    assert "Tienda &lt;Río&gt; &amp; __CUADRAO_OWNER_NAME__" in rendered["html"]
    assert "__CUADRAO_OWNER_NAME__" in rendered["text"]
    assert "<Río>" not in rendered["html"]
    assert rendered["text"].endswith("\n\nCuadrao LLC")
    assert rendered["text"].count("\nCuadrao\n") == 1
    assert "unsubscribe" not in rendered["html"]
    if locale == "en":
        assert 'lang="en"' in rendered["html"]
        assert "Regards,\nCuadrao" in rendered["text"]
        assert "Need help? Email hola@cuadrao.ai" in rendered["text"]
        assert "Saludos" not in rendered["text"]
    else:
        assert "Saludos,\nCuadrao" in rendered["text"]
    if kind == "member_reopened":
        assert "https://app.example.test/biz\n" in rendered["text"]
        assert "Ana &lt;Rosa&gt;" in rendered["html"]
        assert "lifecycle=manage" not in rendered["text"]
    else:
        assert "https://app.example.test" + context["reopenPath"] in rendered["text"]
        assert "lifecycle=manage&amp;business=" in rendered["html"]
        assert "22:03:07" in rendered["text"]
        date = "18 de noviembre de 2026" if locale == "es-419" else "November 18, 2026"
        assert date in rendered["text"]
        closed = "17 de octubre de 2026" if locale == "es-419" else "October 17, 2026"
        assert closed in rendered["text"]


def test_existing_rows_default_to_spanish_and_member_closed_stays_compatible(context):
    rendered = render_close_mail(context)
    assert rendered["subject"] == f"{context['businessName']} se cerró en Cuadrao"
    assert "ya no tienes acceso" in rendered["text"]
    assert "17 de octubre de 2026" in rendered["text"]


@pytest.mark.parametrize("kind", ["owner_closed", "purge_reminder", "member_reopened"])
def test_held_rows_without_a_recipient_locale_default_to_spanish(
    context, monkeypatch, kind
):
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://app.example.test")
    assert render_close_mail(context, kind=kind) == render_close_mail(
        context, kind=kind, locale="es-419"
    )


@pytest.mark.parametrize("field", ["closedAt", "purgeAt"])
def test_timezone_naive_queued_dates_are_rejected(context, field):
    context[field] = "2026-10-18T02:00:00"
    with pytest.raises(ValueError, match="timezone"):
        render_close_mail(context)


@pytest.mark.parametrize("field", ["businessName", "ownerName", "closedAt", "purgeAt"])
@pytest.mark.parametrize("value", ["", "bad\r\nheader", "bad\x00value", "bad\tvalue"])
def test_unsafe_queued_fields_are_rejected(context, field, value):
    context[field] = value
    with pytest.raises(ValueError):
        render_close_mail(context)


@pytest.mark.parametrize(
    "path",
    [
        "https://outside.example.test/biz",
        "//outside.example.test/biz",
        "/biz#manage",
        "/biz?lifecycle=manage&business=bad",
        "/biz?lifecycle=close&business=4fd88ea2-b7b4-4943-b399-664cf3bf9756",
        "/biz?lifecycle=manage&business=4fd88ea2-b7b4-4943-b399-664cf3bf9756&extra=1",
        "/biz?lifecycle=manage&business=4fd88ea2-b7b4-4943-b399-664cf3bf9756&business=4fd88ea2-b7b4-4943-b399-664cf3bf9756",
        "/biz?lifecycle=manage&business=4fd88ea2-b7b4-4943-b399-664cf3bf9756#",
    ],
)
def test_owner_links_reject_unexpected_navigation(context, monkeypatch, path):
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", "https://app.example.test")
    context["reopenPath"] = path
    with pytest.raises(ValueError):
        render_close_mail(context, kind="owner_closed")


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "http://app.example.test",
        "https://app.example.test/path",
        "https://user:pass@app.example.test",
        "https://app.example.test/#",
        "https://app.example.test/\t",
    ],
)
def test_application_origin_is_required_and_validated(context, monkeypatch, origin):
    monkeypatch.setenv("CUADRAO_APP_ORIGIN", origin)
    monkeypatch.delenv("ARGUS_APP_ORIGIN", raising=False)
    with pytest.raises(ValueError):
        render_close_mail(context, kind="owner_closed")


def test_unknown_kind_and_locale_fail_closed(context):
    with pytest.raises(ValueError):
        render_close_mail(context, kind="unknown")
    with pytest.raises(ValueError):
        render_close_mail(context, locale="unknown")
