"""Local-only API for the flags-off rehearsal on argus-biz-flagsoff. Never committed.

FLAG_STATE picks the flag set (ON, S1, S2, S3, S4). Two seams are replaced:
the document extractor (a stub with fixed reads keyed by sha256) and the
WhatsApp media source (local files). Outbound WhatsApp is off, and every proxy
variable points at a dead local port so a stray provider call fails locally.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
WORKTREE = Path("/Users/garces/Documents/projects/repos/argus-worktrees/business-pilot-spaces")


def _env_file(name: str) -> dict[str, str]:
    pairs = {}
    for line in (HERE / name).read_text().splitlines():
        key, _, value = line.partition("=")
        if key:
            pairs[key] = value.strip().strip('"')
    return pairs


stack, wa = _env_file("stack.env"), _env_file("wa.env")
assert stack["API_URL"] == "http://127.0.0.1:57791" and ":57792/" in stack["DB_URL"], "argus-biz-flagsoff only"

STATES = {
    "ON": {},
    "S1": {"ARGUS_BUSINESS_PILOT_ENABLED": "false"},
    "S2": {"ARGUS_BUSINESS_PILOT_ENABLED": "false", "ARGUS_WHATSAPP_INTAKE_ENABLED": "false"},
    "S3": {"ARGUS_BUSINESS_PILOT_ENABLED": "false", "ARGUS_DOCUMENT_EXTRACTION_ENABLED": "false"},
    "S4": {
        "ARGUS_INGESTION_ENABLED": "false",
        "ARGUS_DOCUMENT_EXTRACTION_ENABLED": "false",
        "ARGUS_DOCUMENT_JOBS_ENABLED": "false",
        "ARGUS_BUSINESS_PILOT_ENABLED": "false",
        "ARGUS_WHATSAPP_INTAKE_ENABLED": "false",
    },
}
STATE = os.environ["FLAG_STATE"]
FLAGS = {
    "ARGUS_FINANCIAL_ACCOUNTS_ENABLED": "true",
    "ARGUS_INGESTION_ENABLED": "true",
    "ARGUS_DOCUMENT_EXTRACTION_ENABLED": "true",
    "ARGUS_DOCUMENT_JOBS_ENABLED": "true",
    "ARGUS_BUSINESS_PILOT_ENABLED": "true",
    "ARGUS_WHATSAPP_INTAKE_ENABLED": "true",
    "ARGUS_WHATSAPP_OUTBOUND_ENABLED": "false",
    "ARGUS_ACCOUNT_DELETION_ENABLED": "true",
    **STATES[STATE],
}
os.environ.update(
    {
        "APP_ENV": "local",
        "ARGUS_PERSISTENCE_MODE": "supabase",
        "SUPABASE_URL": stack["API_URL"],
        "SUPABASE_ANON_KEY": stack["ANON_KEY"],
        "SUPABASE_SERVICE_ROLE_KEY": stack["SERVICE_ROLE_KEY"],
        "SUPABASE_JWT_SECRET": stack["JWT_SECRET"],
        "DATABASE_URL": stack["DB_URL"],
        "OPENROUTER_API_KEY": "",
        "ARGUS_VISION_MODEL": "",
        "ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED": "true",
        "ARGUS_GUEST_ACCESS_ENABLED": "false",
        "ARGUS_MOCK_AUTH": "false",
        "ARGUS_DOCUMENT_JOBS_SWEEP_SECONDS": "5",
        "ARGUS_WHATSAPP_APP_SECRET": wa["WA_APP_SECRET"],
        "ARGUS_WHATSAPP_VERIFY_TOKEN": wa["WA_VERIFY_TOKEN"],
        "ARGUS_WHATSAPP_SENDER_KEY": wa["WA_SENDER_KEY"],
        "ARGUS_WHATSAPP_ACCESS_TOKEN": "local-unused-access-token",
        "ARGUS_WHATSAPP_PHONE_NUMBER_ID": "100000000000001",
        "ARGUS_APP_ORIGIN": "http://localhost:3641",
        "ARGUS_CORS_ALLOW_ORIGINS": "http://localhost:3641",
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "127.0.0.1,localhost",
        **FLAGS,
    }
)
sys.path[:0] = [str(WORKTREE / "src"), str(WORKTREE)]

from argus.domain.ingestion.contract import Attachment  # noqa: E402
from argus.domain.ingestion.documents.extractor import batch_from_result  # noqa: E402
from argus.domain.ingestion.documents.models import ExtractionResult  # noqa: E402
from argus.domain.ingestion.whatsapp.media import FetchedMedia, MediaUnavailable  # noqa: E402

CALLS = HERE / "stub-calls.log"


class StubExtractor:
    """Returns the fixed read for a known synthetic receipt; refuses anything else."""

    async def extract(self, content, filename, media_type, connection_id, observed_at):  # noqa: ANN001
        digest = hashlib.sha256(content).hexdigest()
        read = json.loads((HERE / "reads.json").read_text()).get(digest)
        with CALLS.open("a") as log:
            log.write(f"{datetime.now(timezone.utc).isoformat()} state={STATE} {connection_id} {digest[:12]} {'known' if read else 'unknown'}\n")
        if read is None:
            from argus.domain.ingestion.documents.models import DocumentExtractionError

            raise DocumentExtractionError("document_unreadable")
        result = ExtractionResult.model_validate(read)
        batch = batch_from_result(result, digest, connection_id, observed_at, 1)
        attachment = Attachment(
            external_id=digest, sha256=digest, media_type=media_type,
            size_bytes=len(content), filename=filename,
        )
        return batch.model_copy(update={
            "candidates": tuple(c.model_copy(update={"attachments": (attachment,)}) for c in batch.candidates),
            "metadata": {"pages": 1, "media_type": media_type, "sha256": digest, "model": "local-stub"},
        })


class LocalMedia:
    """Serves WhatsApp media ids from local files; never contacts Meta."""

    def __init__(self, **_: object) -> None:
        pass

    async def fetch(self, media_id: str) -> FetchedMedia:
        path = HERE / "media" / f"{media_id}.png"
        if not path.is_file():
            raise MediaUnavailable("whatsapp_media_expired")
        return FetchedMedia(content=path.read_bytes(), mime_type="image/png")


import argus.api.documents as documents_api  # noqa: E402
import argus.api.whatsapp as whatsapp_api  # noqa: E402

documents_api.DocumentExtractor = lambda *args, **kwargs: StubExtractor()
whatsapp_api.GraphMedia = LocalMedia

import uvicorn  # noqa: E402
from argus.api.main import app  # noqa: E402

if __name__ == "__main__":
    import argus

    flags = {k: os.environ.get(k) for k in sorted(FLAGS)}
    print("argus from", argus.__file__, "state", STATE, "flags", json.dumps(flags), flush=True)
    uvicorn.run(app, host="127.0.0.1", port=8641, log_level="info")
