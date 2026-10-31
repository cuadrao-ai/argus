"""Structural OpenAPI compatibility projection and gate primitives (#234).

FastAPI ``app.openapi()`` is the canonical machine-readable API source;
``docs/api/openapi.yaml`` is the checked compatibility artifact, never a second
authority. This module owns three things:

1. ``customize_openapi_document`` — corrects generated declarations so they
   describe real runtime behavior (required Idempotency-Key, RFC 9457 error
   bodies, the SSE success media type). Declaration-only; no behavior changes.
2. ``structural_projection`` — reduces either document to comparable structure:
   documentation-only fields removed, component references resolved, list
   ordering canonicalized, and the single approved streaming normalization
   applied.
3. ``structural_failures`` — the #234 gate: named, exact differences between
   the generated and checked artifacts, plus the prefix/server/exclusion rules
   from the approved #229 OpenAPI-authority contract.

The comparison is structural, never textual, and the only excluded operations
are the individually named non-product operations from the contract.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from argus.api.ops_contract import (
    ACCESS_REQUEST_APPROVE_PATH,
    REQUESTED_SIGNUP_DENIAL_PATH,
)

API_PREFIX = "/api/v1"

# The approved exclusion list. No public /api/v1 product route may hide
# behind a prefix or wildcard allowlist.
EXCLUDED_OPERATIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("get", "/health"),
        ("get", "/internal/readiness"),
        ("post", ACCESS_REQUEST_APPROVE_PATH),
        ("post", REQUESTED_SIGNUP_DENIAL_PATH),
        ("post", "/api/v1/dev/reset"),
    }
)


# Routes that authenticate the caller themselves (or bootstrap a session) and
# therefore never fall behind the shared bounded-session-verification
# dependency. Every other public operation goes through that dependency and
# can return 503 auth_session_verification_unavailable.
_UNAUTHENTICATED_PATHS = frozenset(
    {
        "/api/v1/auth/signup",
        "/api/v1/auth/login",
        "/api/v1/auth/access-requests",
        "/api/v1/auth/guest",
        "/api/v1/auth/logout",
    }
)

_AUTH_SESSION_UNAVAILABLE_RESPONSE_REF = {
    "$ref": "#/components/responses/AuthSessionVerificationUnavailable"
}

_AUTH_SESSION_UNAVAILABLE_COMPONENT = {
    "description": (
        "Bounded Supabase session verification is temporarily unavailable; "
        "retry without redirecting to login."
    ),
    "content": {
        "application/json": {
            "schema": {"$ref": "#/components/schemas/Error"},
            "example": {
                "type": (
                    "https://api.argus.app/problems/"
                    "auth-session-verification-unavailable"
                ),
                "title": "Session Verification Unavailable",
                "status": 503,
                "detail": "Argus could not verify this session. Please try again.",
                "code": "auth_session_verification_unavailable",
                "request_id": "req_123",
            },
        }
    },
}

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "trace")

# Annotation-only keys; the #229 contract keeps them out of the structural
# comparison. ``title`` is JSON Schema annotation noise FastAPI stamps on every
# generated schema.
_DOC_ONLY_KEYS = frozenset(
    {
        "description",
        "summary",
        "operationId",
        "tags",
        "examples",
        "example",
        "externalDocs",
        "title",
    }
)

ERROR_COMPONENT = {
    "type": "object",
    "description": "RFC 9457 Problem Details with code and request_id.",
    "required": ["type", "title", "status", "detail", "code", "request_id"],
    "properties": {
        "type": {"type": "string"},
        "title": {"type": "string"},
        "status": {"type": "integer"},
        "detail": {"type": "string"},
        "code": {"type": "string"},
        "request_id": {"type": "string"},
        "context": {"type": "object"},
    },
}

_ERROR_REF = {"$ref": "#/components/schemas/Error"}


def _error_response(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": copy.deepcopy(_ERROR_REF)}},
    }


# Request documentation only; this body never reaches an interpretation model.
_CREATE_ACCOUNT_AMOUNT = (
    "Starting balance as typed, dot-decimal; a liability is the positive amount "
    "owed. Omitted or blank on a Personal cash, checking, savings, investment, "
    "credit card or other debt account records an opening of 0 at as_of. "
    "Property, vehicle and other asset values, and Business accounts, stay "
    "unknown when omitted. as_of defaults to now."
)


def customize_openapi_document(document: dict[str, Any]) -> dict[str, Any]:
    """Correct generated declarations to match real runtime behavior."""

    spec = copy.deepcopy(document)
    schemas = spec.setdefault("components", {}).setdefault("schemas", {})
    amount = (
        schemas.get("CreateFinancialAccountRequest", {})
        .get("properties", {})
        .get("amount")
    )
    if amount is not None:
        amount["description"] = _CREATE_ACCOUNT_AMOUNT
    schemas["Error"] = copy.deepcopy(ERROR_COMPONENT)
    responses_components = spec["components"].setdefault("responses", {})
    responses_components["AuthSessionVerificationUnavailable"] = copy.deepcopy(
        _AUTH_SESSION_UNAVAILABLE_COMPONENT
    )

    _rewrite_validation_errors(spec)

    logout_op = spec.get("paths", {}).get("/api/v1/auth/logout", {}).get("post")
    if logout_op is not None:
        logout_op.setdefault("responses", {})["403"] = {
            "description": "Untrusted browser origin rejected."
        }

    guest_bootstrap_op = spec.get("paths", {}).get("/api/v1/auth/guest", {}).get("post")
    if guest_bootstrap_op is not None:
        responses = guest_bootstrap_op.setdefault("responses", {})
        responses["403"] = _error_response(
            "Guest access is disabled, or the browser origin is untrusted."
        )
        responses["409"] = _error_response(
            "This browser already has a permanent account session."
        )
        responses["429"] = _error_response(
            "Too many guest session attempts. Please wait before trying again."
        )
        responses["500"] = _error_response(
            "Supabase persistence is required for guest authentication."
        )
        responses["503"] = _error_response(
            "Argus could not start a guest session. Please try again."
        )

    access_request_op = (
        spec.get("paths", {}).get("/api/v1/auth/access-requests", {}).get("post")
    )
    if access_request_op is not None:
        responses = access_request_op.setdefault("responses", {})
        responses["403"] = _error_response("Untrusted browser origin rejected.")
        responses["429"] = _error_response(
            "Too many access request attempts. Please wait before trying again."
        )
        responses["503"] = _error_response(
            "Argus could not record this access request. Please try again."
        )

    for path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict) or path in _UNAUTHENTICATED_PATHS:
            continue
        for method, operation in path_item.items():
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            responses = operation.setdefault("responses", {})
            responses["503"] = copy.deepcopy(_AUTH_SESSION_UNAVAILABLE_RESPONSE_REF)
            responses["500"] = _error_response("An unexpected server error occurred.")

    profile_op = spec.get("paths", {}).get(f"{API_PREFIX}/me", {}).get("get")
    if profile_op is not None:
        profile_op.setdefault("responses", {})["503"] = _error_response(
            "`apple_identity_unavailable`: current linked identity could not be verified. "
            "`auth_session_verification_unavailable`: the session could not be verified."
        )

    profile_patch = spec.get("paths", {}).get(f"{API_PREFIX}/me", {}).get("patch")
    if profile_patch is not None:
        profile_patch.setdefault("responses", {})["503"] = _error_response(
            "`apple_identity_unavailable`: current linked identity could not be verified; "
            "no profile update is applied. "
            "`auth_session_verification_unavailable`: the session could not be verified."
        )

    deletion_op = (
        spec.get("paths", {}).get(f"{API_PREFIX}/account/delete", {}).get("post")
    )
    if deletion_op is not None:
        # Starting and resuming a deletion are the same POST (Lane 6).
        deletion_op.setdefault("responses", {})["503"] = _error_response(
            "`account_deletion_incomplete`: the run may be open or its admission "
            "state could not be established; retry this route (Retry-After: 5). "
            "`account_deletion_unavailable`: no deletion has started and its "
            "identity, credential, or deletion service is unavailable. "
            "`auth_session_verification_unavailable`: the session "
            "could not be verified; retry."
        )

    search_op = spec.get("paths", {}).get(f"{API_PREFIX}/search", {}).get("get")
    if search_op is not None:
        search_op.setdefault("responses", {})["503"] = _error_response(
            "Search temporarily unavailable because exact bounded recall could "
            "not be completed, or authentication-session verification is "
            "temporarily unavailable."
        )

    return spec


def _rewrite_validation_errors(spec: dict[str, Any]) -> None:
    """The runtime returns RFC 9457 bodies for 422s, not HTTPValidationError."""

    for operations in spec.get("paths", {}).values():
        for method, operation in operations.items():
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            validation = operation.get("responses", {}).get("422")
            if not isinstance(validation, dict):
                continue
            content = validation.get("content", {}).get("application/json")
            if isinstance(content, dict):
                content["schema"] = copy.deepcopy(_ERROR_REF)
    schemas = spec.get("components", {}).get("schemas", {})
    schemas.pop("HTTPValidationError", None)
    schemas.pop("ValidationError", None)


def public_operations(document: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    operations: dict[tuple[str, str], dict[str, Any]] = {}
    for path, path_item in sorted(document.get("paths", {}).items()):
        if not isinstance(path_item, dict):
            continue
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if operation is None:
                continue
            if (method, path) in EXCLUDED_OPERATIONS:
                continue
            operations[(method, path)] = operation
    return operations


def _resolve_schema_map(
    mapping: dict[str, Any], components: dict[str, Any], stack: tuple[str, ...]
) -> dict[str, Any]:
    """Resolve a ``properties``-style mapping without treating field names as
    documentation-only annotation keys (a field can legitimately be named
    ``title``, ``description``, ``summary``, etc.)."""

    return {
        field_name: _resolve(field_schema, components, stack)
        for field_name, field_schema in mapping.items()
    }


def _resolve(node: Any, components: dict[str, Any], stack: tuple[str, ...]) -> Any:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            name = ref.rsplit("/", 1)[-1]
            if name in stack:
                return {"$circular": name}
            target = components.get(name)
            if target is None:
                return {"$unresolved": name}
            return _resolve(target, components, stack + (name,))
        resolved: dict[str, Any] = {}
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                resolved[key] = _resolve_schema_map(value, components, stack)
                continue
            if key in _DOC_ONLY_KEYS:
                continue
            resolved[key] = _resolve(value, components, stack)
        for list_key in ("required", "enum"):
            if list_key in resolved and isinstance(resolved[list_key], list):
                resolved[list_key] = sorted(
                    resolved[list_key], key=lambda item: json.dumps(item, sort_keys=True)
                )
        for combinator in ("anyOf", "oneOf", "allOf"):
            if combinator in resolved and isinstance(resolved[combinator], list):
                resolved[combinator] = sorted(
                    resolved[combinator],
                    key=lambda item: json.dumps(item, sort_keys=True),
                )
        return resolved
    if isinstance(node, list):
        return [_resolve(item, components, stack) for item in node]
    return node


def _resolve_response(
    response: Any,
    schemas: dict[str, Any],
    response_components: dict[str, Any],
    stack: tuple[str, ...],
) -> dict[str, Any]:
    """Resolve a response object, following a response-level ``$ref`` (used by
    shared components such as ``AuthSessionVerificationUnavailable``) before
    projecting its content schemas."""

    if not isinstance(response, dict):
        return {}
    ref = response.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/responses/"):
        name = ref.rsplit("/", 1)[-1]
        if name in stack:
            return {"$circular": name}
        target = response_components.get(name)
        if target is None:
            return {"$unresolved": name}
        return _resolve_response(target, schemas, response_components, stack + (name,))

    media_map: dict[str, Any] = {}
    for media, media_item in sorted(response.get("content", {}).items()):
        media_map[media] = _resolve(media_item.get("schema", {}), schemas, ())
    return media_map


def structural_projection(document: dict[str, Any]) -> dict[str, Any]:
    """Reduce a document to the approved comparable structure."""

    schemas = document.get("components", {}).get("schemas", {})
    response_components = document.get("components", {}).get("responses", {})
    projection: dict[str, Any] = {}
    for (method, path), operation in public_operations(document).items():
        parameters = []
        for parameter in operation.get("parameters", []):
            parameters.append(
                {
                    "name": parameter.get("name"),
                    "in": parameter.get("in"),
                    "required": bool(parameter.get("required", False)),
                    "schema": _resolve(parameter.get("schema", {}), schemas, ()),
                }
            )
        parameters.sort(key=lambda item: (str(item["in"]), str(item["name"])))

        request_body: dict[str, Any] = {"required": False, "content": {}}
        body = operation.get("requestBody")
        if isinstance(body, dict):
            request_body["required"] = bool(body.get("required", False))
            for media, media_item in sorted(body.get("content", {}).items()):
                request_body["content"][media] = _resolve(
                    media_item.get("schema", {}), schemas, ()
                )

        responses: dict[str, Any] = {}
        for status, response in sorted(operation.get("responses", {}).items()):
            responses[str(status)] = _resolve_response(
                response, schemas, response_components, ()
            )

        projection[f"{method.upper()} {path}"] = {
            "parameters": parameters,
            "request": request_body,
            "responses": responses,
        }
    return projection


def _diff(pointer: str, generated: Any, checked: Any, failures: list[str]) -> None:
    if isinstance(generated, dict) and isinstance(checked, dict):
        for key in sorted(set(generated) | set(checked)):
            child = f"{pointer}/{key}"
            if key not in generated:
                failures.append(f"{child}: present only in checked artifact")
            elif key not in checked:
                failures.append(f"{child}: present only in generated document")
            else:
                _diff(child, generated[key], checked[key], failures)
        return
    if isinstance(generated, list) and isinstance(checked, list):
        if generated != checked:
            failures.append(
                f"{pointer}: generated={json.dumps(generated, sort_keys=True)} "
                f"checked={json.dumps(checked, sort_keys=True)}"
            )
        return
    if generated != checked:
        failures.append(
            f"{pointer}: generated={json.dumps(generated, sort_keys=True)} "
            f"checked={json.dumps(checked, sort_keys=True)}"
        )


def _server_rule_failures(document: dict[str, Any], label: str) -> list[str]:
    failures: list[str] = []
    servers = document.get("servers")
    if servers not in (None, []):
        urls = [server.get("url") for server in servers if isinstance(server, dict)]
        if urls not in (["/"], [""]):
            failures.append(
                f"{label} servers must be origin-relative; found {urls!r} "
                f"(the {API_PREFIX} prefix must appear exactly once, in paths)"
            )
    return failures


def _prefix_rule_failures(document: dict[str, Any], label: str) -> list[str]:
    failures: list[str] = []
    for method, path in public_operations(document):
        if not path.startswith(f"{API_PREFIX}/"):
            failures.append(
                f"{label} operation {method.upper()} {path} is outside {API_PREFIX} "
                "and is not an approved named exclusion"
            )
        elif path.count(API_PREFIX) != 1:
            failures.append(
                f"{label} operation {method.upper()} {path} repeats the "
                f"{API_PREFIX} prefix"
            )
    return failures


def structural_failures(generated: dict[str, Any], checked: dict[str, Any]) -> list[str]:
    """The #234 gate. Empty list means the artifacts are compatible."""

    failures: list[str] = []
    failures.extend(_server_rule_failures(generated, "generated"))
    failures.extend(_server_rule_failures(checked, "checked"))
    failures.extend(_prefix_rule_failures(generated, "generated"))
    failures.extend(_prefix_rule_failures(checked, "checked"))

    for method, path in sorted(EXCLUDED_OPERATIONS):
        if checked.get("paths", {}).get(path, {}).get(method) is not None:
            failures.append(
                f"excluded non-product operation {method.upper()} {path} must not "
                "appear in the checked artifact"
            )

    generated_projection = structural_projection(generated)
    checked_projection = structural_projection(checked)

    for operation in sorted(set(generated_projection) | set(checked_projection)):
        if operation not in checked_projection:
            failures.append(f"missing operation in checked artifact: {operation}")
        elif operation not in generated_projection:
            failures.append(f"unexpected operation in checked artifact: {operation}")
        else:
            _diff(
                operation,
                generated_projection[operation],
                checked_projection[operation],
                failures,
            )
    return sorted(failures)
