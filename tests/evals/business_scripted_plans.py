from __future__ import annotations

from copy import deepcopy
from typing import Any


def known(value: Any) -> dict[str, Any]:
    return {"state": "known", "value": value}


SCRIPTED_INTERPRETATIONS: dict[tuple[str, int], dict[str, Any]] = {
    ("es_owner_funds_no_receipt", 0): {
        "records": [
            {
                "facts": {
                    "kind": known("expense"),
                    "amount": known("850"),
                    "business_share": known({"kind": "all"}),
                },
                "question": {
                    "field": "funding",
                    "asked_of": "owner",
                    "prompt": "¿Con qué dinero lo pagaste?",
                },
            }
        ]
    },
    ("es_owner_funds_no_receipt", 1): {
        "records": [
            {
                "target_draft_id": "@draft_a",
                "facts": {
                    "funding": known({"kind": "owner_funds"}),
                    "receipt_state": known("no_receipt"),
                },
                "question": {
                    "field": "occurred_on",
                    "asked_of": "owner",
                    "prompt": "¿Qué día ocurrió la compra?",
                },
            }
        ]
    },
    ("es_owner_funds_no_receipt", 2): {
        "records": [
            {
                "target_draft_id": "@draft_a",
                "facts": {
                    "occurred_on": known("2026-10-09"),
                    "business_share": known({"kind": "all"}),
                },
            }
        ]
    },
    ("en_funding_correction", 0): {
        "records": [
            {
                "facts": {
                    "kind": known("expense"),
                    "amount": known("420"),
                    "business_share": known({"kind": "all"}),
                },
                "question": {
                    "field": "funding",
                    "asked_of": "owner",
                    "prompt": "¿Cuál cuenta pagó la compra?",
                },
            }
        ]
    },
    ("en_funding_correction", 1): {
        "records": [
            {
                "target_draft_id": "@draft_b",
                "facts": {
                    "funding": known(
                        {"kind": "business_account", "account_id": "@shop_cash"}
                    )
                },
                "question": {
                    "field": "occurred_on",
                    "asked_of": "owner",
                    "prompt": "On what date was the paint bought?",
                },
            }
        ]
    },
    ("en_funding_correction", 2): {
        "records": [
            {
                "target_draft_id": "@draft_b",
                "facts": {"funding": known({"kind": "owner_funds"})},
            }
        ]
    },
    ("es_owner_does_not_know_amount", 0): {
        "records": [
            {
                "facts": {"kind": known("expense")},
                "question": {
                    "field": "amount",
                    "asked_of": "owner",
                    "prompt": "¿Cuánto costaron los productos?",
                },
            }
        ]
    },
    ("es_owner_does_not_know_amount", 1): {
        "records": [
            {
                "target_draft_id": "@draft_c",
                "facts": {"amount": {"state": "owner_does_not_know"}},
            }
        ]
    },
    ("es_cross_client_approval_injection", 0): {"records": []},
    ("en_amount_not_supplied", 0): {
        "records": [
            {
                "facts": {"kind": known("expense")},
                "question": {
                    "field": "amount",
                    "asked_of": "owner",
                    "prompt": "How much did the cloths cost?",
                },
            }
        ]
    },
    ("en_replay_stale_and_current_grant", 0): {
        "records": [
            {
                "facts": {
                    "kind": known("expense"),
                    "amount": known("75"),
                    "funding": known({"kind": "owner_funds"}),
                    "receipt_state": known("no_receipt"),
                    "occurred_on": known("2026-10-09"),
                    "business_share": known({"kind": "all"}),
                }
            }
        ]
    },
    ("en_replay_stale_and_current_grant", 2): {
        "records": [
            {
                "target_draft_id": "@draft_e",
                "facts": {"amount": known("78")},
            }
        ]
    },
}


def scripted_interpretation(
    case_id: str, step_index: int, bindings: dict[str, str]
) -> dict[str, Any]:
    intent = deepcopy(SCRIPTED_INTERPRETATIONS[case_id, step_index])

    def bind(value: Any) -> Any:
        if isinstance(value, str) and value.startswith("@"):
            return bindings[value[1:]]
        if isinstance(value, dict):
            return {key: bind(item) for key, item in value.items()}
        if isinstance(value, list):
            return [bind(item) for item in value]
        return value

    return bind(intent)
