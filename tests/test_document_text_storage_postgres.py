"""Exercise the extraction JSONB adapter with synthetic text and no app schema."""

import os

import psycopg
import pytest
from psycopg.types.json import Jsonb

from tests.ingestion.test_document_text_storage import (
    document_bridge,
    extracted_batch,
    prepared_receipt,
)

__all__ = ["document_bridge", "prepared_receipt"]
DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DSN, reason="No disposable database configured")


@pytest.mark.asyncio
async def test_extracted_nul_fails_jsonb_then_cleaned_document_persists(prepared_receipt):
    original = extracted_batch("café\x00🧾")
    with psycopg.connect(DSN) as sql:
        sql.execute("create temporary table receipt_text_probe (batch jsonb not null)")
        with pytest.raises(psycopg.errors.UntranslatableCharacter) as failure:
            with sql.transaction():
                sql.execute(
                    "insert into receipt_text_probe (batch) values (%s)",
                    (Jsonb(original.model_dump(mode="json")),),
                )
        assert failure.value.sqlstate == "22P05"
        _, _, _, _, _, _, saved = await prepared_receipt(original)
        sql.execute(
            "insert into receipt_text_probe (batch) values (%s)",
            (Jsonb(saved.model_dump(mode="json")),),
        )
        stored = sql.execute("select batch from receipt_text_probe").fetchone()[0]
        assert stored["receipt"]["merchant"] == "café�🧾"
        assert stored["metadata"]["text_cleaning"] == {"nul_replacements": 4}
