"""The private diagnostic never enters receipt intake or sends a reply."""

import asyncio
import copy
import json
import os
import stat
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from argus.api.routers.whatsapp import webhook_router
from argus.api.whatsapp import build_whatsapp, require_whatsapp_surface
from argus.domain.ingestion.whatsapp.config import WhatsAppSettings
from argus.domain.ingestion.whatsapp.diagnostic_control import DiagnosticControl
from argus.domain.ingestion.whatsapp.diagnostic_once import (
    DiagnosticHeld,
    DiagnosticOnce,
    WorkerIdentity,
)
from argus.domain.ingestion.whatsapp.media import GraphMedia
from faker import Faker
from fastapi import FastAPI

from tests.ingestion.whatsapp_support import APP_SECRET, sign


@pytest.fixture
def scope():
    fake = Faker()
    fake.seed_instance(972)
    now = int(time.time())
    return dict(
        diagnostic_id="synthetic-once",
        nonce="unbound",
        release_sha="a" * 40,
        instance_id="synthetic-instance",
        deployment_id="synthetic-deployment",
        topology_observed_at=now,
        instances=1,
        workers=1,
        expires_at=now + 120,
        sender=fake.numerify("1555#######"),
        app_id=fake.numerify("8##############"),
        subject_id=fake.numerify("9##############"),
        waba_id=fake.numerify("4##############"),
        phone_id=fake.numerify("5##############"),
        owner_id=fake.uuid4(),
        business_id=fake.uuid4(),
    )


def event(scope: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": scope["waba_id"],
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": scope["phone_id"]},
                            "messages": [
                                {
                                    "from": scope["sender"],
                                    "id": "wamid.SYNTHETIC_ONCE=",
                                    "timestamp": str(int(time.time())),
                                    "type": "document",
                                    "document": {
                                        "id": "700000000000001",
                                        "mime_type": "application/pdf",
                                        "caption": "PRIVATE_CAPTION",
                                        "filename": "PRIVATE_FILENAME.pdf",
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


@pytest.fixture
def directory():
    fake = Faker()
    path = Path("temp") / ("d-" + fake.hexify("^^^^^^"))
    yield path.resolve()
    if path.exists() and not path.is_symlink():
        for child in path.iterdir():
            child.unlink()
        path.rmdir()


@pytest.fixture
def world(scope, monkeypatch):
    token = "synthetic-initialized-token"
    settings = WhatsAppSettings(
        diagnostic_enabled=True,
        access_token=token,
        app_secret=APP_SECRET,
        sender_key="synthetic-key",
        phone_number_id=scope["phone_id"],
    )
    monkeypatch.setenv("CUADRAO_WHATSAPP_ACCESS_TOKEN", "synthetic-new-settings-token")
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.headers["Authorization"] == f"Bearer {token}"
        assert request.url.host == "graph.facebook.com"
        assert request.extensions["timeout"]["read"] == 10
        if request.url.path.endswith("/debug_token"):
            assert request.url.params["input_token"] == token
            return httpx.Response(
                200,
                json={
                    "data": {
                        "is_valid": True,
                        "type": "SYSTEM_USER",
                        "app_id": scope["app_id"],
                        "user_id": scope["subject_id"],
                        "scopes": ["whatsapp_business_messaging"],
                        "expires_at": 0,
                    }
                },
            )
        assert request.url.path == "/v23.0/700000000000001"
        return httpx.Response(
            200,
            json={
                "id": "700000000000001",
                "mime_type": "application/pdf",
                "file_size": 14,
                "url": "https://evil.example/PRIVATE_SIGNED_URL",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    media = GraphMedia(
        client=client, access_token=token, graph_api_version="v23.0", max_bytes=1000
    )
    media.fetch = AsyncMock(side_effect=AssertionError("download forbidden"))
    media._download = AsyncMock(side_effect=AssertionError("download forbidden"))
    controller = DiagnosticOnce(
        media=media,
        settings=settings,
        scope_check=Mock(return_value=True),
        identity=WorkerIdentity(
            release_sha=scope["release_sha"], instance_id=scope["instance_id"]
        ),
    )
    scope["nonce"] = controller.nonce
    return SimpleNamespace(
        controller=controller,
        calls=calls,
        client=client,
        media=media,
        scope=scope,
        body=json.dumps(event(scope)).encode(),
        settings=settings,
    )


async def armed(world, directory):
    control = DiagnosticControl(world.controller, directory)
    assert await control.start()
    assert world.controller.arm(world.scope)
    return control


def test_diagnostic_is_default_off() -> None:
    assert WhatsAppSettings().diagnostic_enabled is False


@pytest.mark.asyncio
async def test_disarmed_controller_has_no_network_or_intake() -> None:
    controller = DiagnosticOnce(media=None, settings=WhatsAppSettings(), scope_check=None)
    assert controller.status()["state"] == "disarmed"
    with pytest.raises(DiagnosticHeld):
        await controller.observe(b"{}")
    assert controller.status()["state"] == "disarmed"


@pytest.mark.asyncio
async def test_one_event_uses_initialized_header_and_keeps_only_private_metadata(
    world, directory
):
    control = await armed(world, directory)
    try:
        await asyncio.gather(*(world.controller.observe(world.body) for _ in range(5)))
        result = json.loads(control.result_path.read_bytes())
        assert len(world.calls) == 2
        assert result["get_attempts"] == 2
        assert result["header_matches_runtime"] is True
        assert result["header_matches_selected"] is False
        assert result["identity"]["matched"] is True
        assert result["media"]["matched"] is True
        assert result["event"]["sender_match"] is True
        assert result["scope_match_reading_off"] is True
        assert not any(result["side_effects"].values())
        assert world.controller.state == "sealed"
        assert not world.controller.arm(world.scope)
        assert not control.path.exists()
        assert control.result_path.stat().st_size <= 65536
        assert stat.S_IMODE(control.result_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        text = control.result_path.read_text()
        for private in (
            "PRIVATE_CAPTION",
            "PRIVATE_FILENAME",
            "PRIVATE_SIGNED_URL",
            world.scope["sender"],
            "synthetic-initialized-token",
            "synthetic-new-settings-token",
        ):
            assert private not in text
        world.media.fetch.assert_not_called()
        world.media._download.assert_not_called()
    finally:
        control.close()
        await world.client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("nonce", "stale"),
        ("release_sha", "b" * 40),
        ("instance_id", "another"),
        ("instances", 2),
        ("workers", 2),
        ("topology_observed_at", 1),
        ("expires_at", 1),
        ("expires_at", 9999999999),
        ("phone_id", "999"),
        ("sender", "bad/url"),
        ("owner_id", "not-a-uuid"),
        ("unexpected", "payload"),
        ("instances", True),
    ],
)
async def test_bad_arm_seals_without_provider_requests(world, directory, field, value):
    control = DiagnosticControl(world.controller, directory)
    assert await control.start()
    world.scope[field] = value
    try:
        assert not world.controller.arm(world.scope)
        assert world.controller.state == "sealed"
        assert world.calls == []
        assert not control.path.exists()
    finally:
        control.close()
        await world.client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    ["waba", "phone", "sender", "multiple", "stale", "mime", "malformed", "message_id"],
)
async def test_mismatched_or_ambiguous_delivery_never_reaches_provider(
    world, directory, mutation
):
    control = await armed(world, directory)
    payload = event(world.scope)
    entry = payload["entry"][0]
    value = entry["changes"][0]["value"]
    message = value["messages"][0]
    if mutation == "waba":
        entry["id"] = "999"
    if mutation == "phone":
        value["metadata"]["phone_number_id"] = "999"
    if mutation == "sender":
        message["from"] = "19999999999"
    if mutation == "multiple":
        value["messages"].append(copy.deepcopy(message))
    if mutation == "stale":
        message["timestamp"] = "1"
    if mutation == "mime":
        message["document"]["mime_type"] = "image/png"
    if mutation == "message_id":
        message["id"] = "https://evil.example"
    body = b"[]" if mutation == "malformed" else json.dumps(payload).encode()
    try:
        if mutation in {"sender", "malformed"}:
            with pytest.raises(DiagnosticHeld):
                await world.controller.observe(body)
        else:
            await world.controller.observe(body)
        assert world.controller.state == "sealed"
        assert world.calls == []
        assert not control.path.exists()
        assert not any(world.controller.result["side_effects"].values())
    finally:
        control.close()
        await world.client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("scope_result", [False, RuntimeError("PRIVATE_SCOPE_ERROR")])
async def test_readonly_scope_failure_stops_before_graph(world, directory, scope_result):
    control = await armed(world, directory)
    check = world.controller.scope_check
    if isinstance(scope_result, Exception):
        check.side_effect = scope_result
    else:
        check.return_value = scope_result
    try:
        await world.controller.observe(world.body)
        assert world.calls == []
        assert world.controller.state == "sealed"
        assert "PRIVATE_SCOPE_ERROR" not in control.result_path.read_text()
    finally:
        control.close()
        await world.client.aclose()


@pytest.mark.asyncio
async def test_expiry_closes_socket_and_duplicate_stays_quarantined(world, directory):
    control = await armed(world, directory)
    world.controller.clock = lambda: world.scope["expires_at"]
    try:
        await world.controller.observe(world.body)
        await world.controller.observe(world.body)
        assert world.calls == []
        assert world.controller.state == "sealed"
        assert not control.path.exists()
    finally:
        control.close()
        await world.client.aclose()


@pytest.mark.asyncio
async def test_idle_expiry_and_restart_never_rearm(world, directory):
    control = await armed(world, directory)
    control.schedule_expiry(0)
    await asyncio.sleep(0.01)
    assert world.controller.state == "sealed"
    assert world.calls == []
    control.close()
    restarted = DiagnosticOnce(
        media=world.media,
        settings=world.settings,
        scope_check=Mock(return_value=True),
        identity=world.controller.identity,
    )
    next_control = DiagnosticControl(restarted, directory)
    try:
        assert await next_control.start()
        assert restarted.state == "disarmed"
        assert restarted.nonce != world.controller.nonce
        assert not restarted.arm(world.scope)
    finally:
        next_control.close()
        await world.client.aclose()


@pytest.mark.asyncio
async def test_same_host_second_controller_cannot_serve_or_arm(world, directory):
    control = DiagnosticControl(world.controller, directory)
    assert await control.start()
    other = DiagnosticOnce(
        media=world.media,
        settings=world.settings,
        scope_check=Mock(return_value=True),
        identity=world.controller.identity,
    )
    second = DiagnosticControl(other, directory)
    try:
        assert not await second.start()
        assert other.state == "sealed"
        assert not other.arm({**world.scope, "nonce": other.nonce})
        assert control.exclusive()
        assert control.path.exists()
        assert world.calls == []
    finally:
        control.close()
        second.close()
        await world.client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("unsafe", ["symlink", "mode", "foreign_file", "stale_socket"])
async def test_private_control_refuses_unsafe_paths_without_clobbering(
    world, directory, unsafe
):
    if unsafe == "symlink":
        directory.symlink_to(directory.parent, target_is_directory=True)
    else:
        directory.mkdir(mode=0o700)
        if unsafe == "mode":
            directory.chmod(0o755)
        if unsafe == "foreign_file":
            (directory / "owner.lock").write_text("unrelated")
        if unsafe == "stale_socket":
            (directory / "control.sock").write_text("unrelated")
    control = DiagnosticControl(world.controller, directory)
    try:
        assert not await control.start()
        assert world.controller.state == "sealed"
        assert world.calls == []
        if unsafe == "foreign_file":
            assert (directory / "owner.lock").read_text() == "unrelated"
        if unsafe == "stale_socket":
            assert (directory / "control.sock").read_text() == "unrelated"
    finally:
        control.close()
        if unsafe == "symlink":
            directory.unlink()
        await world.client.aclose()


async def command(path, payload):
    reader, writer = await asyncio.open_unix_connection(str(path))
    writer.write(json.dumps(payload).encode() + b"\n")
    await writer.drain()
    data = json.loads(await reader.readline())
    writer.close()
    await writer.wait_closed()
    return data


@pytest.mark.asyncio
async def test_private_socket_status_arm_and_foreign_peer_rejection(
    world, directory, monkeypatch
):
    control = DiagnosticControl(world.controller, directory)
    assert await control.start()
    try:
        assert stat.S_IMODE(control.path.stat().st_mode) == 0o600
        assert (await command(control.path, {"action": "status"}))[
            "nonce"
        ] == world.controller.nonce
        monkeypatch.setattr(
            "argus.domain.ingestion.whatsapp.diagnostic_control._peer_uid",
            lambda _: os.geteuid() + 1,
        )
        assert await command(control.path, {"action": "arm", "scope": world.scope}) == {
            "accepted": False
        }
        assert world.controller.state == "disarmed"
        monkeypatch.setattr(
            "argus.domain.ingestion.whatsapp.diagnostic_control._peer_uid",
            lambda _: os.geteuid(),
        )
        assert await command(control.path, {"action": "arm", "scope": world.scope}) == {
            "accepted": True
        }
        assert world.calls == []
    finally:
        control.close()
        await world.client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "signed,enabled,armed_state,expected",
    [
        (False, True, True, 401),
        (True, True, True, 200),
        (True, True, False, 503),
        (True, False, False, 200),
    ],
)
async def test_signature_precedes_diagnostic_and_off_behavior_is_unchanged(
    world,
    directory,
    signed,
    enabled,
    armed_state,
    expected,
):
    control = await armed(world, directory) if armed_state else None
    intake = SimpleNamespace(
        handle=AsyncMock(),
        transport=SimpleNamespace(send=AsyncMock()),
        destination=SimpleNamespace(capture=AsyncMock()),
    )
    runtime = SimpleNamespace(
        settings=world.settings,
        intake=intake,
        diagnostic=world.controller if enabled else None,
    )
    app = FastAPI()
    app.include_router(webhook_router)
    app.dependency_overrides[require_whatsapp_surface] = lambda: runtime

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "synthetic-request"
        return await call_next(request)

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhooks/whatsapp",
                content=world.body,
                headers={
                    "X-Hub-Signature-256": sign(world.body)
                    if signed
                    else "sha256=invalid"
                },
            )
        assert response.status_code == expected
        if enabled:
            intake.handle.assert_not_called()
            intake.transport.send.assert_not_called()
            intake.destination.capture.assert_not_called()
            assert len(world.calls) == (2 if expected == 200 else 0)
        else:
            intake.handle.assert_awaited_once()
            assert world.calls == []
    finally:
        if control:
            control.close()
        await world.client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "condition", ["good", "owner", "business", "link", "reading", "unknown_reading"]
)
async def test_runtime_uses_actual_media_and_readonly_business_checks(scope, condition):
    settings = WhatsAppSettings(
        diagnostic_enabled=True,
        access_token="synthetic-token",
        sender_key="synthetic-key",
        phone_number_id=scope["phone_id"],
    )
    space = SimpleNamespace(
        id=scope["business_id"],
        custodian_id=scope["owner_id"],
        country="DO",
        currency="DOP",
    )
    if condition == "owner":
        space.custodian_id = Faker().uuid4()
    if condition == "business":
        space.id = Faker().uuid4()
    spaces = Mock()
    spaces.open_space.return_value = space
    store = Mock()
    store.sender_link.return_value = (
        None
        if condition == "link"
        else SimpleNamespace(destination_owner_id=scope["owner_id"])
    )
    permission = Mock()
    permission.enabled.return_value = condition == "reading"
    documents = SimpleNamespace(
        hub=SimpleNamespace(clock=lambda: None, box=None),
        business_receipt_consent=None if condition == "unknown_reading" else permission,
    )
    from argus.domain.ingestion.whatsapp.diagnostic_once import Arm

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: pytest.fail("network forbidden"))
    ) as client:
        runtime = build_whatsapp(
            settings, documents=documents, spaces=spaces, store=store, client=client
        )
        assert runtime.diagnostic.media is runtime.intake.media
        assert runtime.diagnostic.scope_check(Arm.model_validate(scope)) is (
            condition == "good"
        )
        store.claim.assert_not_called()
        store.settle.assert_not_called()
        store.issue_code.assert_not_called()
        store.redeem_code.assert_not_called()
        spaces.ensure.assert_not_called()


@pytest.mark.asyncio
async def test_repeated_arm_permanently_seals_before_any_request(world, directory):
    control = await armed(world, directory)
    try:
        assert not world.controller.arm(world.scope)
        await world.controller.observe(world.body)
        assert world.controller.state == "sealed"
        assert world.calls == []
        assert world.controller.result["outcome"] == "repeat_arm_rejected"
        assert not any(world.controller.result["side_effects"].values())
    finally:
        control.close()
        await world.client.aclose()


@pytest.mark.asyncio
async def test_mixed_senders_get_retryable_hold_without_dropping_ordinary_delivery(
    world, directory
):
    control = await armed(world, directory)
    payload = event(world.scope)
    messages = payload["entry"][0]["changes"][0]["value"]["messages"]
    messages.append({**messages[0], "from": "19999999999"})
    try:
        for _ in range(2):
            with pytest.raises(DiagnosticHeld):
                await world.controller.observe(json.dumps(payload).encode())
        assert world.calls == []
        assert world.controller.state == "sealed"
    finally:
        control.close()
        await world.client.aclose()


@pytest.mark.asyncio
async def test_duplicate_json_keys_and_private_record_collision_stop_safely(
    world, directory
):
    control = await armed(world, directory)
    control.result_path.write_text("unrelated-private-file")
    hostile = world.body.replace(b'"object":', b'"object": "conflict", "object":', 1)
    try:
        await world.controller.observe(hostile)
        assert world.calls == []
        assert world.controller.state == "sealed"
        assert world.controller.result == {"outcome": "private_record_unavailable"}
        assert control.result_path.read_text() == "unrelated-private-file"
        assert not control.path.exists()
    finally:
        control.close()
        await world.client.aclose()


@pytest.mark.asyncio
async def test_cancellation_after_dispatch_seals_and_keeps_attempt_count(
    world, directory
):
    control = await armed(world, directory)

    async def interrupted(*args, **kwargs):
        raise asyncio.CancelledError

    world.client.get = interrupted
    try:
        with pytest.raises(asyncio.CancelledError):
            await world.controller.observe(world.body)
        result = json.loads(control.result_path.read_bytes())
        assert result["get_attempts"] == 1
        assert result["outcome"] == "stopped"
        assert world.controller.state == "sealed"
        assert not control.path.exists()
        await world.controller.observe(world.body)
    finally:
        control.close()
        await world.client.aclose()


@pytest.mark.asyncio
async def test_owner_cli_controls_only_existing_worker_socket(
    world, directory, monkeypatch, capsys
):
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "diagnostic_cli", "scripts/ops/arm_whatsapp_diagnostic_once.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    control = DiagnosticControl(world.controller, directory)
    assert await control.start()
    original_path = cli.Path
    monkeypatch.setattr(
        cli,
        "Path",
        lambda value: directory
        if str(value).startswith("/tmp/cuadrao-whatsapp-diagnostic-")
        else original_path(value),
    )
    scope_path = directory / "arm.json"
    scope_path.write_text(json.dumps(world.scope))
    scope_path.chmod(0o600)
    try:
        monkeypatch.setattr(sys, "argv", ["helper", "status"])
        assert await asyncio.to_thread(cli.main) == 0
        assert json.loads(capsys.readouterr().out)["nonce"] == world.controller.nonce
        monkeypatch.setattr(sys, "argv", ["helper", "arm", "--scope", str(scope_path)])
        assert await asyncio.to_thread(cli.main) == 0
        assert json.loads(capsys.readouterr().out) == {"accepted": True}
        assert world.controller.state == "armed"
        assert world.calls == []
    finally:
        control.close()
        await world.client.aclose()


@pytest.mark.asyncio
async def test_evidence_symlink_never_overwrites_foreign_file(world, directory):
    control = await armed(world, directory)
    unrelated = directory / "unrelated"
    unrelated.write_text("keep this")
    control.result_path.symlink_to(unrelated)
    try:
        await world.controller.observe(world.body)
        assert unrelated.read_text() == "keep this"
        assert world.controller.state == "sealed"
        assert world.controller.result == {"outcome": "private_record_unavailable"}
    finally:
        control.close()
        await world.client.aclose()


def test_linux_peer_credentials_use_kernel_uid(monkeypatch):
    import socket
    import struct

    from argus.domain.ingestion.whatsapp.diagnostic_control import _peer_uid

    monkeypatch.setattr(socket, "SO_PEERCRED", 17, raising=False)
    peer = Mock()
    peer.getsockopt.return_value = struct.pack("3i", 123, os.geteuid(), os.getegid())
    assert _peer_uid(SimpleNamespace(get_extra_info=lambda _: peer)) == os.geteuid()
    peer.getsockopt.assert_called_once_with(socket.SOL_SOCKET, 17, 12)
