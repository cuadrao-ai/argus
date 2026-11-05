import asyncio
from uuid import uuid4

import pytest
from argus.domain.business.fiscal_sandbox import provider as transport
from argus.domain.business.fiscal_sandbox.config import Settings
from argus.domain.business.fiscal_sandbox.contracts import Case, digest
from argus.domain.business.fiscal_sandbox.provider import Provider, ProviderError
from argus.domain.business.invoicing.preparation import payload

from tests import test_business_invoice_editor as fixtures

draft = fixtures.draft


def pdf(text):
    stream = b"BT /F1 12 Tf 20 100 Td (" + text.encode() + b") Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
    ]
    body, offsets = b"%PDF-1.4\n", [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(body))
        body += str(index).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    start = len(body)
    body += b"xref\n0 6\n0000000000 65535 f \n"
    body += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    return (
        body + f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["xml", "pdf"])
async def test_saved_revision_artifacts_are_bound_to_expected_values(
    draft, case_factory, kind, monkeypatch
):
    allocation = case_factory()
    prepared = payload(draft, allocation, fixtures.issuer(allocation))
    case = Case.model_validate(
        {
            **allocation.model_dump(mode="json"),
            "payload": prepared,
            "payload_digest": digest(prepared),
            "invoice_id": uuid4(),
            "invoice_revision_id": uuid4(),
            "manifest_digest": digest(allocation.model_dump(mode="json")),
        }
    )
    provider_id = "synthetic-provider-id"
    path = (
        f"/users/{uuid4()}/synthetic/opaque/invoice/"
        + ("pdf/" if kind == "pdf" else "")
        + f"{provider_id}.{kind}"
    )
    url = "https://" + transport.STORAGE_HOST + path
    provider = Provider(
        Settings(storage_host=transport.STORAGE_HOST, storage_path_prefix="/users/")
    )
    xml = f"<ECF><Encabezado><IdDoc><eNCF>{case.number}</eNCF></IdDoc><Emisor><RNCEmisor>{case.issuer}</RNCEmisor></Emisor><Comprador><RNCComprador>131111222</RNCComprador></Comprador><Totales><MontoTotal>35.40</MontoTotal></Totales></Encabezado></ECF>".encode()
    content = (
        pdf(f"{case.number} {case.issuer} Total DOP 35.40") if kind == "pdf" else xml
    )

    async def fetch(method, target, **kwargs):
        assert method == "GET" and target == url
        assert kwargs.get("token") is None
        return content, "application/" + kind

    async def addresses(*args, **kwargs):
        return [(None, None, None, None, ("8.8.8.8", 443))]

    monkeypatch.setattr(transport, "curl", fetch)
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", addresses)
    assert await provider.artifact(case, provider_id, kind, url) == content
    content = (
        pdf(f"{case.number} {case.issuer} Total DOP 99.00")
        if kind == "pdf"
        else xml.replace(b"35.40", b"99.00")
    )
    with pytest.raises(ProviderError, match="artifact_invoice_mismatch"):
        await provider.artifact(case, provider_id, kind, url)
