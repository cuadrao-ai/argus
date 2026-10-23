import json
from pathlib import Path

import httpx
import pytest
from argus.domain.ingestion.whatsapp.config import WhatsAppSettings

from scripts.ops import check_whatsapp_pilot as pilot

TOKEN = "synthetic-private-token"
NUMBER = "100000000000001"


@pytest.mark.parametrize(
    "status,code,subcode,expected,reason",
    [
        (401, 190, 463, "invalid", "expired"),
        (401, 190, 464, "invalid", "token_user_unconfirmed"),
        (401, 190, 467, "invalid", "invalid_or_revoked"),
        (403, 200, None, "denied", "permission_denied"),
        (400, 10, None, "denied", "permission_denied"),
        (429, 4, None, "unverified", "number_access_unverified"),
        (500, 1, None, "unverified", "number_access_unverified"),
    ],
)
def test_credential_failure_is_safe_and_never_retried(
    status: int, code: int, subcode: int | None, expected: str, reason: str
) -> None:
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "GET"
        assert request.url.host == "graph.facebook.com"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert dict(request.url.params) == {"fields": "id"}
        return httpx.Response(
            status,
            json={
                "error": {
                    "code": code,
                    "error_subcode": subcode,
                    "message": f"{TOKEN} sender 15550109999 media SECRETWORDS",
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = pilot.probe_credential(
            client, token=TOKEN, number_id=NUMBER, version="v23.0"
        )
    assert len(calls) == 1
    assert (result["status"], result["reason"]) == (expected, reason)
    for secret in (TOKEN, "15550109999", "SECRETWORDS"):
        assert secret not in json.dumps(result)


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"id": NUMBER}, "authorized"),
        ({"id": "100000000000002"}, "unverified"),
        ([], "unverified"),
    ],
)
def test_success_means_only_number_access(payload: object, expected: str) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as client:
        result = pilot.probe_credential(
            client, token=TOKEN, number_id=NUMBER, version="v23.0"
        )
    assert result["status"] == expected
    assert "delivered" not in result.values()


def test_transport_failure_is_unverified_and_redirect_is_not_followed() -> None:
    calls = []

    def redirect(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://unsafe.example/private"})

    with httpx.Client(
        transport=httpx.MockTransport(redirect), follow_redirects=True
    ) as client:
        assert (
            pilot.probe_credential(
                client, token=TOKEN, number_id=NUMBER, version="v23.0"
            )["status"]
            == "unverified"
        )
    assert len(calls) == 1

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(f"{TOKEN} SECRETWORDS")

    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        result = pilot.probe_credential(
            client, token=TOKEN, number_id=NUMBER, version="v23.0"
        )
    assert result == {"status": "unverified", "reason": "transport"}


def test_response_size_is_bounded() -> None:
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, content=b"x" * (pilot.MAX_RESPONSE_BYTES + 1)
            )
        )
    ) as client:
        assert pilot.probe_credential(
            client, token=TOKEN, number_id=NUMBER, version="v23.0"
        ) == {"status": "unverified", "reason": "response_limit"}


def test_elapsed_limit_stops_response_processing(monkeypatch) -> None:
    from types import SimpleNamespace

    times = iter([0.0, 11.0])
    monkeypatch.setattr(pilot, "time", SimpleNamespace(monotonic=lambda: next(times)))
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"id": NUMBER})
        )
    ) as client:
        assert pilot.probe_credential(
            client, token=TOKEN, number_id=NUMBER, version="v23.0"
        ) == {"status": "unverified", "reason": "response_limit"}


def test_invalid_number_cannot_create_a_request() -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid number made a request")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        assert pilot.probe_credential(
            client, token=TOKEN, number_id="../SECRETWORDS", version="v23.0"
        ) == {"status": "unverified", "reason": "number_id_invalid"}


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b'{"message":"unrelated"}\n',
        b'{"message":"WhatsApp delivery verified","extra":{"messages":0,"statuses":1}}\n',
    ],
)
def test_no_failed_event_cannot_prove_delivery_or_failure(
    tmp_path: Path, content: bytes
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(content)
    result = pilot.delivery_observation(path)
    assert result["status"] == "unverified"
    assert result["failures"] == []
    assert pilot.delivery_observation(None)["reason"] == "no_observation"


def test_delivery_evidence_rederives_safe_reason_and_discards_private_text(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        json.dumps(
            {
                "record": {
                    "extra": {
                        "event": "whatsapp_delivery_failed",
                        "graph_code": "131026",
                        "failure_reason": TOKEN,
                        "sender": "15550109999",
                        "media_url": "https://unsafe.example",
                    }
                }
            }
        )
        + "\n"
    )
    result = pilot.delivery_observation(path)
    assert result["status"] == "failed"
    assert result["failures"] == [{"code": "131026", "reason": "undeliverable"}]
    for secret in (TOKEN, "15550109999", "unsafe.example"):
        assert secret not in json.dumps(result)


def test_delivery_failure_is_visible_in_the_runtime_formatted_log(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        json.dumps(
            {
                "message": "2026-10-23 WARNING - WhatsApp outbound delivery failed: code=131026 reason=undeliverable"
            }
        )
        + "\n"
    )
    assert pilot.delivery_observation(path)["failures"] == [
        {"code": "131026", "reason": "undeliverable"}
    ]


@pytest.mark.parametrize(
    "content",
    [b"SECRETWORDS", b"[]", b'{"extra":[]}', b"x" * (pilot.MAX_EVENTS_BYTES + 1)],
)
def test_bad_or_large_event_file_has_no_arbitrary_output(
    tmp_path: Path, content: bytes
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(content)
    assert pilot.delivery_observation(path) == {
        "status": "unverified",
        "reason": "events_invalid",
        "failures": [],
    }


def test_default_cli_makes_no_request_and_preserves_unknown_delivery(
    monkeypatch, capsys
) -> None:
    settings = WhatsAppSettings(
        intake_enabled=True,
        verify_token="synthetic-verify",
        app_secret="synthetic-app",
        sender_key="synthetic-sender",
        access_token=TOKEN,
        phone_number_id=NUMBER,
    )
    monkeypatch.setattr(pilot, "load_whatsapp_settings", lambda: settings)

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline mode made a request")

    monkeypatch.setattr(pilot.httpx, "Client", forbidden)
    assert pilot.main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["configuration"] == "configured"
    assert report["credential"]["status"] == "not_checked"
    assert report["delivery"]["status"] == "unverified"
    assert report["end_to_end"] == "unverified"
    assert TOKEN not in json.dumps(report)
