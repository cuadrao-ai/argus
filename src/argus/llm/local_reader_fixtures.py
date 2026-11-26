"""Synthetic document-model answers shared by local walks and Business tests."""

from typing import Any

from argus.domain.ingestion.documents.models import ExtractionResult

# The original bytes of tests/document_extraction_fixtures/receipt-dop.png.
_COLMADO_SHA256 = "009f3082c0052c66be647a12a9c0967470c041fb648733cf45ba077740da25c3"


def hardware_receipt(day: str) -> dict[str, Any]:
    return {
        "payment_status": "paid",
        "merchant": "FERRETERIA LA ESQUINA SRL",
        "occurred_on": day,
        "currency": "DOP",
        "items": [
            {"id": "1", "description": "Pintura blanca 1 gal", "total": "1850.00"},
            {"id": "2", "description": "Brochas x3", "total": "1073.73"},
        ],
        "subtotal": "2923.73",
        "tax": "526.27",
        "total": "3450.00",
    }


def purchase(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "page": 1,
        "row": 1,
        "evidence": "transaction",
        "status": "posted",
        "amount": receipt["total"],
        "currency": receipt["currency"],
        "occurred_on": receipt["occurred_on"],
        "direction": "outflow",
        "kind_hint": "expense",
        "merchant": receipt["merchant"],
    }


def response_body(document_sha256: str | None) -> dict[str, Any]:
    day = "2026-09-10"
    if document_sha256 == _COLMADO_SHA256:
        receipt = {
            "merchant": "Colmado Nube de Papel",
            "occurred_on": day,
            "currency": "DOP",
            "items": [
                {"id": "1", "description": "Arroz", "total": "150.00"},
                {"id": "2", "description": "Leche", "total": "100.50"},
            ],
            "total": "250.50",
            "payment_status": "paid",
            "payment_form": "01",
        }
    else:
        receipt = hardware_receipt(day)
        receipt.update(
            rnc="199990021", ncf="B0100002488", itbis=receipt["tax"], payment_form="01"
        )
    content = ExtractionResult.model_validate(
        {
            "complete": True,
            "readable": True,
            "pages_read": [1],
            "observations": [purchase(receipt)],
            "receipt": receipt,
        }
    ).model_dump_json()
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ]
    }
