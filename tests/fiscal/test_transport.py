from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.domain.business.fiscal_sandbox import provider as module
from argus.domain.business.fiscal_sandbox.config import Settings
from argus.domain.business.fiscal_sandbox.contracts import FiscalPrepare, digest
from argus.domain.business.fiscal_sandbox.provider import (
    STORAGE_HOST,
    Provider,
    ProviderError,
    observation,
)
from pydantic import ValidationError


def test_prepare_rejects_caller_invoice_fields():
    with pytest.raises(ValidationError):
        FiscalPrepare(case_id="e32", number="E320000000001", payload={})


def test_sanitized_diagnostic_keeps_code_and_digest_only():
    raw = json.dumps(
        {
            "id": str(uuid4()),
            "status": "FINISHED",
            "legalStatus": "ACCEPTED",
            "error": {"code": "1385", "message": "private signed url or token"},
        }
    ).encode()
    event = observation(raw, "poll")
    assert event.code == "1385"
    assert "private signed" not in event.model_dump_json()
    assert event.evidence_digest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://" + STORAGE_HOST + "/users/anything.xml",
        "https://127.0.0.1/a.pdf",
        "https://" + STORAGE_HOST + ".attacker.test/a.xml",
        "https://user:pass@" + STORAGE_HOST + "/users/a.xml",
        "https://" + STORAGE_HOST + ":444/users/a.xml",
        "https://" + STORAGE_HOST + "/users/../private/a.xml",
    ],
)
async def test_artifact_destination_denied_before_contact(case_factory, url, monkeypatch):
    contacted = False

    async def fail(*args, **kwargs):
        nonlocal contacted
        contacted = True
        raise AssertionError("must not contact")

    monkeypatch.setattr(module, "curl", fail)
    adapter = Provider(Settings(storage_host=STORAGE_HOST, storage_path_prefix="/users/"))
    with pytest.raises(ProviderError, match="artifact_destination_denied"):
        await adapter.artifact(case_factory(), str(uuid4()), "xml", url)
    assert not contacted


@pytest.mark.asyncio
async def test_private_dns_is_rejected(case_factory, monkeypatch):
    provider_id = str(uuid4())
    url = f"https://{STORAGE_HOST}/users/{uuid4()}/opaque/ulid/invoice/doc-{provider_id}.xml?secret=query"

    async def addresses(*args, **kwargs):
        return [(None, None, None, None, ("127.0.0.1", 443))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", addresses)
    with pytest.raises(ProviderError, match="artifact_destination_denied"):
        await Provider(
            Settings(storage_host=STORAGE_HOST, storage_path_prefix="/users/")
        ).artifact(case_factory(), provider_id, "xml", url)


@pytest.mark.asyncio
async def test_storage_has_no_bearer_and_pins_dns(case_factory, monkeypatch):
    case = case_factory()
    provider_id = str(uuid4())
    url = f"https://{STORAGE_HOST}/users/{uuid4()}/opaque/ulid/invoice/doc-{provider_id}.xml?secret=query"

    async def addresses(*args, **kwargs):
        return [(None, None, None, None, ("8.8.8.8", 443))]

    seen = {}

    async def fetch(method, target, **kwargs):
        seen.update(method=method, target=target, **kwargs)
        return (
            f"<ECF><Encabezado><IdDoc><eNCF>{case.number}</eNCF></IdDoc><Emisor><RNCEmisor>{case.issuer}</RNCEmisor></Emisor></Encabezado></ECF>".encode(),
            "application/xml",
        )

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", addresses)
    monkeypatch.setattr(module, "curl", fetch)
    raw = await Provider(
        Settings(storage_host=STORAGE_HOST, storage_path_prefix="/users/")
    ).artifact(case, provider_id, "xml", url)
    assert raw.startswith(b"<ECF>")
    assert "token" not in seen
    assert seen["resolve"] == STORAGE_HOST + ":443:8.8.8.8"


@pytest.mark.asyncio
async def test_curl_secret_only_stdin_no_retry_redirect_or_proxy(monkeypatch):
    captured = {}

    class Input:
        def write(self, value):
            captured["stdin"] = value

        async def drain(self):
            pass

        def close(self):
            pass

    class Output:
        done = False

        async def read(self, cap):
            if self.done:
                return b""
            self.done = True
            return b"{}\n200\napplication/json"

    async def spawn(*args, **kwargs):
        captured.update(args=args, options=kwargs)

        async def wait():
            return 0

        return SimpleNamespace(stdin=Input(), stdout=Output(), wait=wait, returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    await module.curl(
        "POST",
        module.API_ORIGIN + "/invoices",
        token="synthetic-secret",
        payload={"safe": True},
    )
    assert captured["args"] == ("/usr/bin/curl", "-q", "--config", "-")
    assert "synthetic-secret" not in str(captured["args"])
    config = captured["stdin"].decode()
    assert "retry = 0" in config and "max-redirs = 0" in config
    assert 'noproxy = "*"' in config
    assert "location" not in config
    assert "HTTPS_PROXY" not in captured["options"]["env"]


@pytest.mark.asyncio
async def test_curl_cancellation_kills_and_awaits_child(monkeypatch):
    entered = asyncio.Event()
    child = SimpleNamespace(returncode=None)

    class Input:
        def write(self, value):
            pass

        async def drain(self):
            pass

        def close(self):
            pass

    class Output:
        async def read(self, cap):
            entered.set()
            await asyncio.Event().wait()

    child.stdin, child.stdout = Input(), Output()
    child.killed, child.awaited = False, False

    def kill():
        child.killed = True
        child.returncode = -9

    async def wait():
        child.awaited = True
        return child.returncode

    child.kill, child.wait = kill, wait

    async def spawn(*args, **kwargs):
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    task = asyncio.create_task(module.curl("GET", module.API_ORIGIN + "/invoices/id"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert child.killed and child.awaited


def test_manifest_digest_and_alias_fail_closed(tmp_path, case_factory):
    case = case_factory()
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps([case.model_dump(mode="json")]))
    settings = Settings(
        enabled=True,
        business_id=str(case.business_id),
        manifest_path=str(path),
        manifest_sha256="0" * 64,
        api_token="synthetic-token",
        callback_secret="synthetic-secret",
        storage_host=STORAGE_HOST,
        storage_path_prefix="/users/",
    )
    with pytest.raises(ValueError, match="fiscal_manifest_digest"):
        settings.cases()
    assert not Settings().enabled and not Settings().contact_enabled
    assert digest(case.payload) == case.payload_digest


@pytest.mark.asyncio
async def test_opaque_provider_id_is_supported_and_path_injection_denied(
    case_factory, monkeypatch
):
    case = case_factory()
    provider_id = "01M5PAAHR9R8SP2P9RYJAV24J0"

    async def fetch(method, url, **kwargs):
        assert method == "GET" and url.endswith("/" + provider_id)
        return json.dumps(
            {
                "id": provider_id,
                "companyIdentification": case.issuer,
                "documentNumber": case.number,
            }
        ).encode(), "application/json"

    monkeypatch.setattr(module, "curl", fetch)
    result = await Provider(Settings()).status(case, provider_id)
    assert result.provider_id == provider_id
    with pytest.raises(ProviderError, match="invalid_provider_id"):
        await Provider(Settings()).status(case, "../secrets?token=value")


@pytest.mark.parametrize(
    "code",
    [
        "privateBearerToken",
        "token_secret_1385",
        "https://secret.test/a",
        "99999999999999999999",
    ],
)
def test_arbitrary_diagnostic_code_never_echoes(code):
    event = observation(json.dumps({"error": {"code": code}}).encode(), "poll")
    assert event.code == "provider_diagnostic"
    assert code not in event.model_dump_json()


def test_offline_manifest_harness_preserves_fixed_template_fields(tmp_path, case_factory):
    import hashlib

    from scripts.qa.fiscal_sandbox_contract import verify

    template = case_factory()
    source = tmp_path / "source.json"
    source.write_text(json.dumps(template.payload))
    case = template.model_copy(
        update={"fixture_digest": hashlib.sha256(source.read_bytes()).hexdigest()}
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([case.model_dump(mode="json")]))
    approved = hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert verify(manifest, approved, case.business_id, {"E32": source}) == 1
    changed_payload = json.loads(json.dumps(case.payload))
    changed_payload["totals"]["totalAmount"] = 119
    changed = case.model_copy(
        update={"payload": changed_payload, "payload_digest": digest(changed_payload)}
    )
    manifest.write_text(json.dumps([changed.model_dump(mode="json")]))
    with pytest.raises(ValueError, match="fixture_fixed_fields_changed"):
        verify(
            manifest,
            hashlib.sha256(manifest.read_bytes()).hexdigest(),
            case.business_id,
            {"E32": source},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "problem", ["wrong_issuer", "wrong_number", "missing_identity", "doctype"]
)
async def test_xml_must_match_immutable_case(case_factory, monkeypatch, problem):
    case = case_factory()
    provider_id = "01J00000000000000000000000"
    url = f"https://{STORAGE_HOST}/users/{uuid4()}/opaque/ulid/invoice/doc-{provider_id}.xml?private=signed"
    issuer = "999999999" if problem == "wrong_issuer" else case.issuer
    number = "E320000000000" if problem == "wrong_number" else case.number
    raw = f"<ECF><Encabezado><IdDoc><eNCF>{number}</eNCF></IdDoc><Emisor><RNCEmisor>{issuer}</RNCEmisor></Emisor></Encabezado></ECF>".encode()
    if problem == "missing_identity":
        raw = b"<ECF/>"
    if problem == "doctype":
        raw = b'<!DOCTYPE ECF [<!ENTITY private SYSTEM "file:///etc/passwd">]>' + raw

    async def addresses(*args, **kwargs):
        return [(None, None, None, None, ("8.8.8.8", 443))]

    async def fetch(*args, **kwargs):
        return raw, "application/xml"

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", addresses)
    monkeypatch.setattr(module, "curl", fetch)
    with pytest.raises(ProviderError, match="artifact_invalid"):
        await Provider(
            Settings(storage_host=STORAGE_HOST, storage_path_prefix="/users/")
        ).artifact(case, provider_id, "xml", url)


@pytest.mark.asyncio
@pytest.mark.parametrize("overflow", [False, True])
async def test_curl_reads_multichunk_to_eof_and_bounds_total(monkeypatch, overflow):
    body = b"x" * 100000
    chunks = [
        body[:40000],
        body[40000:80000],
        body[80000:],
        b"\n200\napplication/xml",
        b"",
    ]
    child = SimpleNamespace(returncode=None, killed=False, awaited=False)

    class Input:
        def write(self, value):
            pass

        async def drain(self):
            pass

        def close(self):
            pass

    class Output:
        async def read(self, cap):
            return chunks.pop(0)

    async def wait():
        child.awaited = True
        if not child.killed:
            child.returncode = 0
        return child.returncode

    def kill():
        child.killed = True
        child.returncode = -9

    async def spawn(*args, **kwargs):
        return child

    child.stdin, child.stdout, child.wait, child.kill = Input(), Output(), wait, kill
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    if overflow:
        monkeypatch.setattr(module, "_MAX", 70000)
        with pytest.raises(ProviderError, match="response_too_large"):
            await module.curl("GET", module.API_ORIGIN + "/invoices/id")
        assert child.killed and child.awaited
    else:
        result, media = await module.curl("GET", module.API_ORIGIN + "/invoices/id")
        assert result == body and media == "application/xml"
        assert not child.killed and child.awaited
