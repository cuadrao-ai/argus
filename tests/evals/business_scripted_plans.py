from __future__ import annotations

from copy import deepcopy
from typing import Any


def known(value: Any) -> dict[str, Any]:
    return {"state": "known", "value": value}


SCRIPTED_PLANS: dict[tuple[str, int], list[dict[str, Any]]] = {
    ("es_owner_funds_no_receipt", 0): [
        {
            "action": "business_propose_activity",
            "facts": {"kind": known("expense"), "amount": known("850")},
            "source_ids": ["@source"],
        },
        {
            "action": "business_ask",
            "draft": {"from_action": 0},
            "field": "funding",
            "asked_of": "owner",
            "prompt": "¿Con qué dinero lo pagaste?",
        },
    ],
    ("es_owner_funds_no_receipt", 1): [
        {
            "action": "business_propose_activity",
            "draft": {"draft_id": "@draft_a", "version": 1},
            "facts": {
                "funding": known({"kind": "owner_funds"}),
                "receipt_state": known("no_receipt"),
            },
            "source_ids": ["@source"],
            "answers_question_id": "@question_funding",
        },
        {
            "action": "business_ask",
            "draft": {"draft_id": "@draft_a", "version": 2},
            "field": "occurred_on",
            "asked_of": "owner",
            "prompt": "¿Qué día ocurrió la compra?",
        },
    ],
    ("es_owner_funds_no_receipt", 2): [
        {
            "action": "business_propose_activity",
            "draft": {"draft_id": "@draft_a", "version": 2},
            "facts": {
                "occurred_on": known("2026-10-09"),
                "business_share": known({"kind": "all"}),
            },
            "source_ids": ["@source"],
            "answers_question_id": "@question_occurred_on",
        }
    ],
    ("en_funding_correction", 0): [
        {
            "action": "business_propose_activity",
            "facts": {"kind": known("expense"), "amount": known("420")},
            "source_ids": ["@source"],
        },
        {
            "action": "business_ask",
            "draft": {"from_action": 0},
            "field": "funding",
            "asked_of": "owner",
            "prompt": "¿Cuál cuenta pagó la compra?",
        },
    ],
    ("en_funding_correction", 1): [
        {
            "action": "business_propose_activity",
            "draft": {"draft_id": "@draft_b", "version": 1},
            "facts": {
                "funding": known({"kind": "business_account", "account_id": "@shop_cash"})
            },
            "source_ids": ["@source"],
            "answers_question_id": "@question_funding",
        }
    ],
    ("en_funding_correction", 2): [
        {
            "action": "business_propose_activity",
            "draft": {"draft_id": "@draft_b", "version": 2},
            "facts": {"funding": known({"kind": "owner_funds"})},
            "source_ids": ["@source"],
        }
    ],
    ("es_owner_does_not_know_amount", 0): [
        {
            "action": "business_propose_activity",
            "facts": {"kind": known("expense")},
            "source_ids": ["@source"],
        },
        {
            "action": "business_ask",
            "draft": {"from_action": 0},
            "field": "amount",
            "asked_of": "owner",
            "prompt": "¿Cuánto costaron los productos?",
        },
    ],
    ("es_owner_does_not_know_amount", 1): [
        {
            "action": "business_propose_activity",
            "draft": {"draft_id": "@draft_c", "version": 1},
            "facts": {"amount": {"state": "owner_does_not_know"}},
            "source_ids": ["@source"],
            "answers_question_id": "@question_amount",
        }
    ],
    ("es_cross_client_approval_injection", 0): [
        {"action": "business_explain_status", "draft_id": "@draft_foreign"}
    ],
    ("en_amount_not_supplied", 0): [
        {
            "action": "business_propose_activity",
            "facts": {"kind": known("expense")},
            "source_ids": ["@source"],
        },
        {
            "action": "business_ask",
            "draft": {"from_action": 0},
            "field": "amount",
            "asked_of": "owner",
            "prompt": "How much did the cloths cost?",
        },
    ],
    ("en_replay_stale_and_current_grant", 0): [
        {
            "action": "business_propose_activity",
            "facts": {
                "kind": known("expense"),
                "amount": known("75"),
                "funding": known({"kind": "owner_funds"}),
                "receipt_state": known("no_receipt"),
                "occurred_on": known("2026-10-09"),
                "business_share": known({"kind": "all"}),
            },
            "source_ids": ["@source"],
        }
    ],
    ("en_replay_stale_and_current_grant", 2): [
        {
            "action": "business_propose_activity",
            "draft": {"draft_id": "@draft_e", "version": 1},
            "facts": {"amount": known("78")},
            "source_ids": ["@source"],
        }
    ],
}


def scripted_plan(case_id: str, step_index: int, bindings: dict[str, str]) -> dict:
    actions = deepcopy(SCRIPTED_PLANS[case_id, step_index])

    def bind(value: Any) -> Any:
        if isinstance(value, str) and value.startswith("@"):
            return bindings[value[1:]]
        if isinstance(value, dict):
            return {key: bind(item) for key, item in value.items()}
        if isinstance(value, list):
            return [bind(item) for item in value]
        return value

    return {"schema_version": 1, "actions": bind(actions)}
