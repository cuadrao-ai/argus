import socket

import pytest
from argus.domain.ingestion.documents.config import SOURCE_MAX_BYTES
from argus.domain.ingestion.documents.ecf_checks import read_ecf
from argus.domain.ingestion.documents.models import DocumentExtractionError
from argus.domain.ingestion.documents.preparation import prepare_document


def laughs():
    declarations = ['<!ENTITY a "ha">']
    for previous, current in zip("abcdefghi", "bcdefghij", strict=False):
        declarations.append(f'<!ENTITY {current} "' + f"&{previous};" * 10 + '">')
    return ("<!DOCTYPE ECF [" + "".join(declarations) + "]><ECF>&j;</ECF>").encode()


@pytest.mark.parametrize("attack", ["laughs", "file", "http", "dtd", "oversized"])
def test_xml_rejected_without_external_access(monkeypatch, tmp_path, attack):
    canary = tmp_path / "private.txt"
    canary.write_text("must never be read")
    payloads = {
        "laughs": laughs(),
        "file": f'<!DOCTYPE ECF [<!ENTITY x SYSTEM "{canary.as_uri()}">]><ECF>&x;</ECF>'.encode(),
        "http": b'<!DOCTYPE ECF [<!ENTITY x SYSTEM "http://127.0.0.1:9/private">]><ECF>&x;</ECF>',
        "dtd": b'<!DOCTYPE ECF SYSTEM "http://127.0.0.1:9/external.dtd"><ECF/>',
        "oversized": b"<ECF>" + b"x" * SOURCE_MAX_BYTES + b"</ECF>",
    }

    def no_network(*args, **kwargs):
        pytest.fail("XML parsing attempted network access")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    payload = payloads[attack]
    with pytest.raises(DocumentExtractionError):
        prepare_document(payload, "application/xml")
    assert read_ecf(payload) is None
