"""#234 — structural generated-vs-checked OpenAPI compatibility gate."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml
from argus.api import openapi_compat
from argus.api.main import app
from argus.api.ops_contract import (
    ACCESS_REQUEST_APPROVE_PATH,
    REQUESTED_SIGNUP_DENIAL_PATH,
)

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "docs" / "api" / "openapi.yaml"


@pytest.fixture(scope="module")
def generated() -> dict:
    return app.openapi()


@pytest.fixture(scope="module")
def checked() -> dict:
    return yaml.safe_load(ARTIFACT.read_text(encoding="utf-8"))


def test_generated_and_checked_artifacts_are_structurally_compatible(
    generated: dict, checked: dict
) -> None:
    failures = openapi_compat.structural_failures(generated, checked)
    assert failures == [], "\n".join(failures)


def test_search_declares_bounded_visible_conversation_recall(
    generated: dict,
) -> None:
    operation = generated["paths"]["/api/v1/search"]["get"]
    parameters = {parameter["name"]: parameter for parameter in operation["parameters"]}

    query = parameters["q"]
    assert query["in"] == "query"
    assert query["required"] is True
    assert query["schema"]["maxLength"] == 512

    conversation_ids = parameters["conversation_id"]
    assert conversation_ids["in"] == "query"
    assert conversation_ids["required"] is False
    assert conversation_ids["schema"] == {
        "anyOf": [
            {
                "items": {"type": "string", "format": "uuid"},
                "type": "array",
                "minItems": 1,
                "maxItems": 50,
            },
            {"type": "null"},
        ],
        "title": "Conversation Id",
    }
    search_item = generated["components"]["schemas"]["SearchItem"]
    assert search_item["properties"]["archived"] == {
        "type": "boolean",
        "title": "Archived",
    }
    assert "archived" in search_item["required"]
    unavailable = operation["responses"]["503"]
    assert "search temporarily unavailable" in unavailable["description"].lower()
    assert unavailable["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Error"
    }


def test_decision_note_write_schema_caps_new_notes_without_narrowing_reads(
    generated: dict,
) -> None:
    schemas = generated["components"]["schemas"]
    create_note = schemas["DecisionNoteCreate"]["properties"]["note"]["anyOf"][0]
    dossier_note = schemas["SearchDossierDecision"]["properties"]["note"]["anyOf"][0]
    action_note = schemas["SearchDecisionAction"]["properties"]["note"]["anyOf"][0]

    assert create_note["maxLength"] == 500
    assert dossier_note["maxLength"] == 2000
    assert action_note["maxLength"] == 2000


def test_dossier_decision_action_requires_typed_availability(generated: dict) -> None:
    schema = generated["components"]["schemas"]["SearchDecisionAction"]

    assert "availability" in schema["required"]
    assert schema["properties"]["availability"] == {
        "type": "string",
        "enum": ["available", "account_conversion_required"],
        "title": "Availability",
    }


def test_dossier_reads_declare_client_capability_negotiation(generated: dict) -> None:
    for path in (
        "/api/v1/search",
        "/api/v1/conversations/{conversation_id}/run-dossiers",
    ):
        parameters = {
            parameter["name"]: parameter
            for parameter in generated["paths"][path]["get"]["parameters"]
        }
        capability = parameters["X-Argus-Client-Capabilities"]
        assert capability["in"] == "header"
        assert capability["required"] is False
        assert capability["schema"]["anyOf"][0] == {
            "type": "string",
            "maxLength": 1024,
        }


def test_prefix_appears_exactly_once_per_public_operation(
    generated: dict, checked: dict
) -> None:
    for document in (generated, checked):
        for method, path in openapi_compat.public_operations(document):
            assert path.startswith("/api/v1/"), (method, path)
            assert path.count("/api/v1") == 1, (method, path)
    assert checked.get("servers") in (None, [])


def test_exclusions_are_exactly_the_named_operations(checked: dict) -> None:
    assert openapi_compat.EXCLUDED_OPERATIONS == frozenset(
        {
            ("get", "/health"),
            ("get", "/internal/readiness"),
            ("post", ACCESS_REQUEST_APPROVE_PATH),
            ("post", REQUESTED_SIGNUP_DENIAL_PATH),
            ("post", "/api/v1/dev/reset"),
        }
    )
    for method, path in openapi_compat.EXCLUDED_OPERATIONS:
        assert checked.get("paths", {}).get(path, {}).get(method) is None, (
            method,
            path,
        )


def test_access_request_is_public_but_internal_ops_routes_are_exactly_excluded(
    generated: dict,
    checked: dict,
) -> None:
    assert "post" in generated["paths"]["/api/v1/auth/access-requests"]
    assert "post" in checked["paths"]["/api/v1/auth/access-requests"]
    assert "post" in generated["paths"][ACCESS_REQUEST_APPROVE_PATH]
    assert checked.get("paths", {}).get(ACCESS_REQUEST_APPROVE_PATH) is None
    assert "post" in generated["paths"][REQUESTED_SIGNUP_DENIAL_PATH]
    assert checked.get("paths", {}).get(REQUESTED_SIGNUP_DENIAL_PATH) is None


def test_access_request_contract_requires_acceptance_and_documents_failures(
    generated: dict,
    checked: dict,
) -> None:
    for document in (generated, checked):
        schema = document["components"]["schemas"]["AccessRequestAccepted"]
        assert schema["required"] == ["accepted"]
        assert "default" not in schema["properties"]["accepted"]

        responses = document["paths"]["/api/v1/auth/access-requests"]["post"]["responses"]
        assert set(responses) == {"202", "403", "422", "429", "503"}
        for status_code in ("403", "429", "503"):
            assert (
                responses[status_code]["content"]["application/json"]["schema"]["$ref"]
                == "#/components/schemas/Error"
            )


def test_unapproved_exclusion_of_a_public_route_fails_as_missing(
    generated: dict, checked: dict
) -> None:
    """A checked artifact may only omit the three named operations.

    Hiding any other public route by deleting it from the checked file (an
    unapproved exclusion, not a #229-approved one) must surface as a missing
    operation, exactly like any other undeclared drift.
    """

    broken = copy.deepcopy(checked)
    target_path = "/api/v1/discovery/indicators"
    assert "get" in broken["paths"][target_path]
    del broken["paths"][target_path]["get"]
    if not broken["paths"][target_path]:
        del broken["paths"][target_path]

    failures = openapi_compat.structural_failures(generated, broken)
    assert (
        f"missing operation in checked artifact: GET {target_path}" in failures
    ), failures


def test_missing_public_route_fails_with_named_operation(
    generated: dict, checked: dict
) -> None:
    broken = copy.deepcopy(checked)
    del broken["paths"]["/api/v1/discovery/assets"]

    failures = openapi_compat.structural_failures(generated, broken)
    assert (
        "missing operation in checked artifact: GET /api/v1/discovery/assets" in failures
    )


def test_extra_unallowlisted_route_fails_with_named_operation(
    generated: dict, checked: dict
) -> None:
    broken = copy.deepcopy(checked)
    broken["paths"]["/api/v1/portfolio-export"] = {
        "get": {"responses": {"200": {"description": "bogus"}}}
    }

    failures = openapi_compat.structural_failures(generated, broken)
    assert (
        "unexpected operation in checked artifact: GET /api/v1/portfolio-export"
        in failures
    )


def test_method_drift_fails_with_named_operation(generated: dict, checked: dict) -> None:
    """Changing the HTTP method of a real route must fail on both sides."""

    broken = copy.deepcopy(checked)
    operation = broken["paths"]["/api/v1/discovery/assets"].pop("get")
    broken["paths"]["/api/v1/discovery/assets"]["put"] = operation

    failures = openapi_compat.structural_failures(generated, broken)
    assert (
        "missing operation in checked artifact: GET /api/v1/discovery/assets" in failures
    )
    assert (
        "unexpected operation in checked artifact: PUT /api/v1/discovery/assets"
        in failures
    )


def test_double_prefix_regression_fails_the_server_rule(
    generated: dict, checked: dict
) -> None:
    broken = copy.deepcopy(checked)
    broken["servers"] = [{"url": "/api/v1"}]

    failures = openapi_compat.structural_failures(generated, broken)
    assert any(
        "servers must be origin-relative" in failure for failure in failures
    ), failures


def test_required_parameter_drift_fails_with_named_difference(
    generated: dict, checked: dict
) -> None:
    broken = copy.deepcopy(checked)
    parameters = broken["paths"]["/api/v1/business/report-views"]["post"]["parameters"]
    for parameter in parameters:
        if parameter["name"] == "Idempotency-Key":
            parameter["required"] = False

    failures = openapi_compat.structural_failures(generated, broken)
    assert any(
        "POST /api/v1/business/report-views" in failure and "required" in failure
        for failure in failures
    ), failures


def test_required_field_drift_on_a_component_schema_fails_with_named_difference(
    generated: dict, checked: dict
) -> None:
    broken = copy.deepcopy(checked)
    schema = broken["components"]["schemas"]["AccountCapabilities"]
    assert "can_submit_feedback" in schema["required"]
    schema["required"] = [
        field for field in schema["required"] if field != "can_submit_feedback"
    ]

    failures = openapi_compat.structural_failures(generated, broken)
    assert any(
        "required" in failure and "can_submit_feedback" in failure for failure in failures
    ), failures


def test_enum_drift_fails_with_named_difference(generated: dict, checked: dict) -> None:
    schemas = checked.get("components", {}).get("schemas", {})
    enum_owner = None
    for name, schema in sorted(schemas.items()):
        for property_name, property_schema in sorted(
            schema.get("properties", {}).items()
        ):
            if isinstance(property_schema, dict) and property_schema.get("enum"):
                enum_owner = (name, property_name)
                break
        if enum_owner:
            break
    assert enum_owner is not None, "expected at least one enum in the checked artifact"

    broken = copy.deepcopy(checked)
    name, property_name = enum_owner
    broken["components"]["schemas"][name]["properties"][property_name]["enum"].append(
        "drifted_enum_value"
    )

    failures = openapi_compat.structural_failures(generated, broken)
    assert any("drifted_enum_value" in failure for failure in failures), failures


def test_response_schema_drift_fails_with_named_difference(
    generated: dict, checked: dict
) -> None:
    broken = copy.deepcopy(checked)
    operation = broken["paths"]["/api/v1/me"]["get"]
    operation["responses"]["200"]["content"]["application/json"]["schema"] = {
        "type": "string"
    }

    failures = openapi_compat.structural_failures(generated, broken)
    assert any(
        "GET /api/v1/me/responses/200" in failure for failure in failures
    ), failures


def test_openapi_contract_exposes_lazy_run_dossier_history(
    generated: dict,
) -> None:
    operation = generated["paths"][
        "/api/v1/conversations/{conversation_id}/run-dossiers"
    ]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PaginatedRunDossiers"
    }
    for status in ("400", "404"):
        assert operation["responses"][status]["content"]["application/json"][
            "schema"
        ] == {"$ref": "#/components/schemas/Error"}
    parameters = {parameter["name"]: parameter for parameter in operation["parameters"]}
    assert parameters["limit"]["schema"]["default"] == 20
    assert parameters["limit"]["schema"]["maximum"] == 100
    search_item = generated["components"]["schemas"]["SearchItem"]
    assert search_item["properties"]["dossier"]["anyOf"] == [
        {"$ref": "#/components/schemas/RunDossier"},
        {"type": "null"},
    ]
    assert {"dossier", "total_runs", "decided_runs"}.issubset(search_item["required"])
    assert "actions" not in search_item["properties"]


def test_openapi_exposes_conversation_activity_and_read_contract(
    generated: dict,
    checked: dict,
) -> None:
    path = "/api/v1/conversations/{conversation_id}/activity"
    for document in (generated, checked):
        schemas = document["components"]["schemas"]
        conversation = schemas["Conversation"]
        assert conversation["properties"]["activity"]["anyOf"] == [
            {"$ref": "#/components/schemas/ConversationActivity"},
            {"type": "null"},
        ]
        assert "activity" not in conversation["required"]

        operation = schemas["ConversationOperation"]
        assert operation["properties"]["status"]["enum"] == [
            "idle",
            "queued",
            "running",
            "checking",
        ]
        assert operation["properties"]["kind"]["anyOf"][0]["enum"] == [
            "chat_turn",
            "backtest_job",
        ]
        attention = schemas["ConversationAttention"]
        assert attention["properties"]["status"]["enum"] == [
            "none",
            "new_activity",
            "manual_unread",
            "needs_input",
            "needs_attention",
        ]

        history_item = schemas["HistoryItemWire"]
        assert history_item["properties"]["activity"] == {
            "$ref": "#/components/schemas/ConversationActivity"
        }
        assert "activity" not in history_item["required"]

        activity_path = document["paths"][path]
        assert activity_path["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ] == {"$ref": "#/components/schemas/ConversationActivity"}
        assert set(activity_path["get"]["responses"]) == {
            "200",
            "404",
            "422",
            "500",
            "503",
        }
        patch = activity_path["patch"]
        request = patch["requestBody"]["content"]["application/json"]["schema"]
        assert request["oneOf"] == [
            {"$ref": "#/components/schemas/ConversationActivityMarkUnread"},
            {"$ref": "#/components/schemas/ConversationActivityMarkRead"},
        ]
        assert request["discriminator"]["propertyName"] == "action"
        assert (
            schemas["ConversationActivityMarkRead"]["properties"][
                "through_attention_cursor"
            ]["anyOf"][0]["maxLength"]
            == 256
        )
        assert set(patch["responses"]) == {
            "200",
            "403",
            "404",
            "409",
            "422",
            "500",
            "503",
        }
        for method, statuses in (
            ("get", ("404",)),
            ("patch", ("403", "404", "409", "422")),
        ):
            for status in statuses:
                assert activity_path[method]["responses"][status]["content"][
                    "application/json"
                ]["schema"] == {"$ref": "#/components/schemas/Error"}


def test_regeneration_script_matches_checked_artifact() -> None:
    from scripts.generate_openapi_artifact import build_artifact_document

    checked_document = yaml.safe_load(ARTIFACT.read_text(encoding="utf-8"))
    failures = openapi_compat.structural_failures(
        build_artifact_document(), checked_document
    )
    assert failures == [], "\n".join(failures)


def test_account_deletion_lists_every_refusal(generated: dict, checked: dict) -> None:
    """Priya #801 note 7: starting and resuming a deletion are one POST, and
    its contract lists each refusal a client must handle."""
    for document in (generated, checked):
        responses = document["paths"]["/api/v1/account/delete"]["post"]["responses"]
        assert {"200", "202", "401", "403", "404", "429", "503"} <= set(responses)
        for status_code in ("401", "403", "404", "429", "503"):
            assert responses[status_code]["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/Error"
            }
        assert "account_deletion_incomplete" in responses["503"]["description"]
        assert "account_deletion_not_allowed" in responses["403"]["description"]
