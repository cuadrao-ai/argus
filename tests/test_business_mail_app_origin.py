import pytest
from argus.domain.business.close_mail import render_close_mail
from argus.domain.business.transfer_mail import render_transfer_mail


@pytest.fixture
def context(faker):
    return {
        "businessName": faker.company(),
        "ownerName": faker.name(),
        "targetName": faker.name(),
        "occurredAt": "2026-10-19T01:05:00+00:00",
        "expiresAt": "2026-10-26T01:05:00+00:00",
        "closedAt": "2026-10-19T01:05:00+00:00",
        "purgeAt": "2026-11-19T01:05:00+00:00",
        "transferId": faker.uuid4(),
        "reopenPath": f"/biz?lifecycle=manage&business={faker.uuid4()}",
    }


@pytest.mark.parametrize("preferred", ["https://app.example.test", None, ""])
@pytest.mark.parametrize("kind", ["close", "transfer"])
def test_business_mail_app_origin(context, monkeypatch, preferred, kind):
    legacy = "https://legacy.example.test"
    monkeypatch.setenv("ARGUS_APP_ORIGIN", legacy)
    if preferred is None:
        monkeypatch.delenv("CUADRAO_APP_ORIGIN", raising=False)
    else:
        monkeypatch.setenv("CUADRAO_APP_ORIGIN", preferred)

    def render():
        if kind == "close":
            return render_close_mail(context, kind="owner_closed")
        return render_transfer_mail("requested", context)

    if preferred == "":
        with pytest.raises(ValueError, match="HTTPS origin"):
            render()
    else:
        rendered = render()
        expected = legacy if preferred is None else preferred
        assert expected + "/biz?" in rendered["text"]
        assert expected + "/biz?" in rendered["html"]
        if preferred is not None:
            assert legacy not in rendered["text"]
            assert legacy not in rendered["html"]
