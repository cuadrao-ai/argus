from __future__ import annotations

import ast
from pathlib import Path

import yaml
from argus.api.ops_contract import (
    ACCESS_REQUEST_APPROVE_PATH,
    REQUESTED_SIGNUP_DENIAL_PATH,
)

ROOT = Path(__file__).resolve().parents[1]


def _markdown_section(text: str, anchor: str, next_anchor: str) -> str:
    start = text.index(f'<a id="{anchor}"></a>')
    end = text.index(f'<a id="{next_anchor}"></a>', start)
    return text[start:end]


def test_reliability_contract_locks_admission_and_run_reconciliation() -> None:
    contract = (ROOT / "docs" / "API_CONTRACT.md").read_text(encoding="utf-8")

    admission = _markdown_section(
        contract,
        "contract-idempotency-admission",
        "contract-request-boundaries",
    )
    admission_rules = " ".join(admission.split())
    for exact_rule in (
        "`(user_id, operation_scope, Idempotency-Key)`",
        "`chat.run_backtest`",
        "`backtests.run`",
        "`launch_payload_hash` is the full persisted `payload_hash`",
        "`sha256:` followed by 64 lowercase hexadecimal characters",
        "List order is preserved",
        "Per-user exhaustion is evaluated before global exhaustion",
        "never creates a `queued` job",
        "`409 idempotency_conflict`",
        "`429` | `backtest_capacity_exceeded` | `15` seconds",
        "`503` | `backtest_capacity_exceeded` | `15` seconds",
        "`409 idempotency_in_progress`",
        "`Retry-After: 1`",
    ):
        assert exact_rule in admission_rules

    reconciliation = _markdown_section(
        contract,
        "contract-run-action-reconciliation",
        "contract-chat-turn-lifecycle",
    )
    reconciliation_rules = " ".join(reconciliation.split())
    for exact_rule in (
        "`confirmation_id` is the Run action identity",
        "`Idempotency-Key` must equal `confirmation_id`",
        "`GET /api/v1/backtest-jobs/by-action/{confirmation_id}`",
        "`confirmation_id` alone is not comparison input",
        "`404 not_found` means the owner-scoped reservation does not exist",
        "`500 internal_error`",
        "must not replay",
        "`queued` or `running`",
        "`failed`, `canceled`, or `expired`",
    ):
        assert exact_rule in reconciliation_rules

    direct_start = contract.index("## `POST /backtests/run`")
    direct_end = contract.index(
        "## `GET /backtest-jobs/by-action/{confirmation_id}`",
        direct_start,
    )
    direct_endpoint = " ".join(contract[direct_start:direct_end].split())
    assert "a conforming direct job starts in `running`" in direct_endpoint
    assert "queued/running job" not in direct_endpoint

    contract_rules = " ".join(contract.split())
    assert "A runnable confirmation card must include `confirmation_id`" in contract_rules
    assert (
        "`run_backtest` actions must include `payload.confirmation_id`" in contract_rules
    )
    assert (
        "`run_backtest` actions may include `payload.confirmation_id`"
        not in contract_rules
    )


def test_api_contract_documents_backend_owned_retest_period_truth() -> None:
    contract = (ROOT / "docs" / "API_CONTRACT.md").read_text(encoding="utf-8")
    message_start = contract.index("\n## Message\n")
    message_end = contract.index("\n## Legacy Strategy Record\n", message_start)
    message_contract = " ".join(contract[message_start:message_end].split())

    for exact_rule in (
        "`retest_period`: optional backend-owned typed sidecar",
        "`original_date_range`",
        "`requested_date_range`",
        "`effective_date_range`",
        "`duration_days`",
        "`duration = { unit, count, approximate }`",
        "Same-period Retest never reaches confirmation",
        "pre-click availability gate",
        "Run action always keeps its normal localized label",
        "There is no second action, modal, toast, or client-owned execution state",
    ):
        assert exact_rule in message_contract


def test_api_contract_documents_retest_provider_coverage_admission() -> None:
    contract = (ROOT / "docs" / "API_CONTRACT.md").read_text(encoding="utf-8")
    action_start = contract.index("\n### Structured Action Semantics\n")
    action_end = contract.index(
        "\n### Conversation Artifact Continuity Contract\n",
        action_start,
    )
    action_contract = " ".join(contract[action_start:action_end].split())

    for exact_rule in (
        "makes no LLM, research, or discovery call",
        "provider-backed coverage preflight",
        "`503 market_data_unavailable`",
        "`422 no_common_data_window`",
        "`422 insufficient_common_data`",
        "never executes a backtest",
    ):
        assert exact_rule in action_contract


def test_reliability_contract_locks_stale_direct_job_reconciliation() -> None:
    contract = (ROOT / "docs" / "API_CONTRACT.md").read_text(encoding="utf-8")
    data_model = (ROOT / "docs" / "DATA_MODEL.md").read_text(encoding="utf-8")

    admission = _markdown_section(
        contract,
        "contract-idempotency-admission",
        "contract-request-boundaries",
    )
    admission_rules = " ".join(admission.split())
    for exact_rule in (
        "`started_at + interval '15 minutes'`",
        "`20` stale direct jobs",
        "`started_at ASC, id ASC`",
        "fully finalized Run/evidence tuple first",
        "`direct_execution_abandoned`",
        "`execution_interrupted`",
        "same locked job row",
        "returns `503` Problem Details",
        "a new execution requires a new `Idempotency-Key`",
        "release their running-capacity slot in the same transaction",
        "must not create, attach, expose, or return a Run",
    ):
        assert exact_rule in admission_rules

    data_model_rules = " ".join(data_model.split())
    for exact_rule in (
        "`status = failed`",
        "`failure_code = direct_execution_abandoned`",
        "`failure_detail = execution_interrupted`",
        "`retryable = true`",
        "fully finalized Run/evidence tuple",
        "finalizer and stale reconciler serialize on the same locked job row",
    ):
        assert exact_rule in data_model_rules


def test_reliability_contract_locks_chat_request_boundaries() -> None:
    contract = (ROOT / "docs" / "API_CONTRACT.md").read_text(encoding="utf-8")
    bounds = _markdown_section(
        contract,
        "contract-request-boundaries",
        "contract-openapi-authority",
    )

    for exact_rule in (
        "| Entire request body | `65,536` UTF-8 bytes |",
        "| `conversation_id` | `128` Unicode code points |",
        "| `message` | `16,000` Unicode code points |",
        "| `mentions` | `10` items |",
        "| `mention.id` | `128` Unicode code points |",
        "| `mention.label` | `120` Unicode code points |",
        "| `mention.symbol` | `32` Unicode code points |",
        "| `mention.description` | `256` Unicode code points |",
        "| `mention.insert_text` | `64` Unicode code points |",
        "| `mention.provider` | `64` Unicode code points |",
        "| `action.label` | `120` Unicode code points |",
        "| `action.labelKey` | `160` Unicode code points |",
        "| `action.payload` serialized size | `16,384` UTF-8 bytes |",
        "| `action.payload` container depth | `6` |",
        "| Any `action.payload` object | `50` keys |",
        "| Any `action.payload` array | `50` items |",
        "| Any `action.payload` string | `4,096` Unicode code points |",
        "`413 request_body_too_large`",
        "`422 validation_error`",
    ):
        assert exact_rule in bounds


def test_reliability_contract_locks_openapi_authority_and_exclusions() -> None:
    contract = (ROOT / "docs" / "API_CONTRACT.md").read_text(encoding="utf-8")
    authority = _markdown_section(
        contract,
        "contract-openapi-authority",
        "contract-run-action-reconciliation",
    )

    for exact_rule in (
        "FastAPI `app.openapi()` is the canonical machine-readable source",
        "`docs/api/openapi.yaml` is the checked compatibility artifact",
        "`GET /health`",
        "`GET /internal/readiness`",
        f"`POST {ACCESS_REQUEST_APPROVE_PATH}`",
        f"`POST {REQUESTED_SIGNUP_DENIAL_PATH}`",
        "`POST /api/v1/dev/reset`",
        "`POST /api/v1/chat/stream` 200 `text/event-stream` response body",
        "`/api/v1` appears exactly once",
    ):
        assert exact_rule in authority

    excluded_operations = {
        line.removeprefix("- ").strip()
        for line in authority.splitlines()
        if line.startswith("- `")
    }
    assert excluded_operations == {
        "`GET /health`",
        "`GET /internal/readiness`",
        f"`POST {ACCESS_REQUEST_APPROVE_PATH}`",
        f"`POST {REQUESTED_SIGNUP_DENIAL_PATH}`",
        "`POST /api/v1/dev/reset`",
    }


def test_reliability_contract_locks_durable_turn_lifecycle() -> None:
    contract = (ROOT / "docs" / "API_CONTRACT.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    data_model = (ROOT / "docs" / "DATA_MODEL.md").read_text(encoding="utf-8")

    lifecycle_start = contract.index('<a id="contract-chat-turn-lifecycle"></a>')
    lifecycle_end = contract.index("\n## Admin Bypass", lifecycle_start)
    lifecycle = contract[lifecycle_start:lifecycle_end]
    lifecycle_rules = " ".join(lifecycle.split())
    for state in (
        "`accepted`",
        "`running`",
        "`completed`",
        "`recoverable_failed`",
        "`abandoned`",
        "`reconciled`",
    ):
        assert state in lifecycle_rules
    for exact_rule in (
        "`15 minutes`",
        "`20` stale rows",
        "`completed | recoverable_failed`",
        "`chat.run_backtest` is excluded",
        "`stale_since = COALESCE(running_at, accepted_at)`",
        "`stale_since ASC, turn_id ASC`",
        "`metadata.agent_runtime_turn.turn_id = turn_id`",
        "`created_at ASC, outcome_precedence ASC, id ASC`",
        "`accepted -> running`",
        "`accepted|running -> completed`",
        "`accepted|running -> recoverable_failed`",
        "`accepted|running -> abandoned`",
        "`accepted|running -> reconciled`",
        "Chat request boundary transaction",
        "Runtime worker before the first graph operation",
        "Terminal message persistence/finalizer",
        "Terminal failure guard/message store",
        "Server reconciler",
        "`turn_abandoned`",
    ):
        assert exact_rule in lifecycle_rules
    assert "`completed | recoverable_failed | abandoned`" not in lifecycle_rules

    assert (
        "Supabase owns the current durable lifecycle of every accepted non-backtest chat turn"
        in " ".join(architecture.split())
    )
    assert "## 8.1 chat_turn_lifecycles" in data_model
    assert "`UNIQUE(user_id, operation_scope, idempotency_key)`" in data_model
    for exact_rule in (
        "`authenticated` receives `SELECT` only",
        "`INSERT`, `UPDATE`, and `DELETE` are revoked from `anon` and `authenticated`",
        "`confirmation_message_id` is required for `chat.run_backtest`",
        "`metadata.agent_runtime_turn.turn_id`",
    ):
        assert exact_rule in " ".join(data_model.split())


def test_reliability_contract_locks_abandoned_turn_projection() -> None:
    contract = (ROOT / "docs" / "API_CONTRACT.md").read_text(encoding="utf-8")
    data_model = (ROOT / "docs" / "DATA_MODEL.md").read_text(encoding="utf-8")

    lifecycle_start = contract.index('<a id="contract-chat-turn-lifecycle"></a>')
    lifecycle_end = contract.index("\n## Admin Bypass", lifecycle_start)
    lifecycle_rules = " ".join(contract[lifecycle_start:lifecycle_end].split())
    for exact_rule in (
        "the accepted user message whose `id = turn_id` owns the read projection",
        '"status": "abandoned"',
        '"failure_code": "turn_abandoned"',
        '"code": "turn_abandoned"',
        '"request_message_id": "<turn_id>"',
        "exact persisted user-message content",
        "immediately after its owning user message and before the next persisted message",
        "No synthetic assistant message is inserted into the API response",
        "no placeholder assistant message is persisted",
    ):
        assert exact_rule in lifecycle_rules

    data_model_rules = " ".join(data_model.split())
    for exact_rule in (
        "`abandoned` requires `assistant_message_id = null`",
        "read-time projection belongs to the accepted user message",
        "does not create or persist an assistant message",
    ):
        assert exact_rule in data_model_rules


def test_active_openapi_uses_alpha_contract_names() -> None:
    openapi = ROOT / "docs" / "api" / "openapi.yaml"

    text = openapi.read_text(encoding="utf-8")

    for path in (
        "/api/v1/me",
        "/api/v1/conversations",
        "/api/v1/history",
    ):
        assert path in text
    assert "/api/v1/collections" not in text
    assert "/api/v1/strategies" not in text
    assert "backtest_runs" in text
    assert "portfolios" not in text.lower()
    assert "simulations" not in text.lower()
    contract = yaml.safe_load(text)
    assert all(
        "summary" not in (schema.get("properties") or {})
        for schema in contract["components"]["schemas"].values()
        if isinstance(schema, dict)
    )


def test_guest_identity_policy_contract_is_active_across_canon_and_openapi() -> None:
    product = (ROOT / "docs" / "PRODUCT.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    api_contract = (ROOT / "docs" / "API_CONTRACT.md").read_text(encoding="utf-8")
    data_model = (ROOT / "docs" / "DATA_MODEL.md").read_text(encoding="utf-8")
    design = (ROOT / ".agent" / "designs" / "argus" / "DESIGN.md").read_text(
        encoding="utf-8"
    )
    openapi = yaml.safe_load(
        (ROOT / "docs" / "api" / "openapi.yaml").read_text(encoding="utf-8")
    )

    assert "Guest Entry (Default-On Kill Switch)" in product
    assert "`CUADRAO_GUEST_ACCESS_ENABLED=true`" in product
    # The flag's value belongs to the release profile, asserted against every
    # standing doc by test_private_alpha_release_docs.py. Pinning it here too
    # is what let PRODUCT.md keep claiming `false` after production opened.
    assert "CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED" in product
    assert "CUADRAO_GUEST_ACCESS_ENABLED" in architecture
    assert "CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED" in architecture
    assert "`POST /api/v1/auth/guest`" in api_contract
    assert "`POST /api/v1/auth/guest/signup`" in api_contract
    assert "`POST /api/v1/auth/guest/handoffs`" in api_contract
    assert "`POST /api/v1/auth/guest/handoffs/{handoff_id}/claim`" in api_contract
    assert "`guest_session`" in api_contract
    assert "cost_ledger_entries" in api_contract
    assert "profiles.email" in data_model
    assert "verified anonymous Auth user" in data_model
    assert "fixed seven-day" in data_model
    assert "centered auth modal" in design
    assert "/api/v1/auth/guest" in openapi["paths"]
    assert "/api/v1/auth/guest/signup" in openapi["paths"]
    assert "/api/v1/auth/guest/link" not in openapi["paths"]
    guest_bootstrap = openapi["paths"]["/api/v1/auth/guest"]["post"]
    assert guest_bootstrap["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/GuestBootstrapRequest"
    }
    captcha = openapi["components"]["schemas"]["GuestBootstrapRequest"]["properties"][
        "captcha_token"
    ]
    assert captcha == {"type": "string", "minLength": 1, "maxLength": 4096}
    assert "GuestAccountSummary" in openapi["components"]["schemas"]
    assert "AccountCapabilities" in openapi["components"]["schemas"]
    user_response = openapi["components"]["schemas"]["UserResponse"]
    assert set(user_response["required"]) == {
        "user",
        "account_kind",
        "guest",
        "capabilities",
        "public_account_access_enabled",
    }
    assert user_response["properties"]["public_account_access_enabled"] == {
        "type": "boolean",
        "description": (
            "Server-authoritative permission to expose ordinary account creation."
        ),
    }
    assert user_response["properties"]["user"] == {
        "anyOf": [
            {"$ref": "#/components/schemas/User"},
            {"$ref": "#/components/schemas/GuestUser"},
        ]
    }
    assert openapi["components"]["schemas"]["User"]["properties"]["email"] == {
        "anyOf": [{"type": "string"}, {"type": "null"}]
    }
    assert "avatar_theme" in openapi["components"]["schemas"]["User"]["properties"]
    assert (
        "avatar_theme" not in openapi["components"]["schemas"]["GuestUser"]["properties"]
    )


def test_logout_openapi_declares_browser_origin_rejection() -> None:
    openapi = ROOT / "docs" / "api" / "openapi.yaml"

    document = yaml.safe_load(openapi.read_text(encoding="utf-8"))
    responses = document["paths"]["/api/v1/auth/logout"]["post"]["responses"]

    assert "untrusted browser origin" in responses["403"]["description"].lower()


def test_password_auth_openapi_requires_bounded_captcha_tokens() -> None:
    openapi = yaml.safe_load(
        (ROOT / "docs" / "api" / "openapi.yaml").read_text(encoding="utf-8")
    )

    for schema_name in ("SignupRequest", "LoginRequest"):
        schema = openapi["components"]["schemas"][schema_name]
        assert "captcha_token" in schema["required"]
        assert schema["properties"]["captcha_token"] == {
            "type": "string",
            "minLength": 1,
            "maxLength": 4096,
        }


def test_signup_openapi_keeps_private_alpha_denial_generic() -> None:
    openapi = yaml.safe_load(
        (ROOT / "docs" / "api" / "openapi.yaml").read_text(encoding="utf-8")
    )

    responses = openapi["paths"]["/api/v1/auth/signup"]["post"]["responses"]
    assert "403" not in responses


def test_authenticated_openapi_declares_session_verification_unavailable() -> None:
    openapi = ROOT / "docs" / "api" / "openapi.yaml"

    text = openapi.read_text(encoding="utf-8")
    assert "AuthSessionVerificationUnavailable" in text
    assert "auth_session_verification_unavailable" in text
    contract = yaml.safe_load(text)
    unauthenticated_paths = {
        "/api/v1/auth/signup",
        "/api/v1/auth/login",
        "/api/v1/auth/access-requests",
        "/api/v1/auth/guest",
        "/api/v1/auth/logout",
    }
    for path, path_contract in contract["paths"].items():
        if path in unauthenticated_paths:
            continue
        for method in ("get", "post", "patch", "put", "delete"):
            operation = path_contract.get(method)
            if operation is None:
                continue
            if path == "/api/v1/me":
                response = operation["responses"]["503"]
                assert "auth_session_verification_unavailable" in response["description"]
                assert "apple_identity_unavailable" in response["description"]
                assert response["content"]["application/json"]["schema"] == {
                    "$ref": "#/components/schemas/Error"
                }
                continue
            if path == "/api/v1/account/delete":
                # Lane 6: the deletion POST adds its own 503s (note 7).
                response = operation["responses"]["503"]
                assert "auth_session_verification_unavailable" in response["description"]
                assert "account_deletion_incomplete" in response["description"]
                assert "account_deletion_unavailable" in response["description"]
                assert response["content"]["application/json"]["schema"] == {
                    "$ref": "#/components/schemas/Error"
                }
                continue
            if path == "/api/v1/search":
                response = operation["responses"]["503"]
                assert "exact bounded recall" in response["description"]
                assert "authentication-session verification" in response["description"]
                assert response["content"]["application/json"]["schema"] == {
                    "$ref": "#/components/schemas/Error"
                }
                continue
            assert operation["responses"]["503"] == {
                "$ref": "#/components/responses/AuthSessionVerificationUnavailable"
            }


def test_api_contract_documents_recovery_transport_rejections() -> None:
    contract = (ROOT / "docs" / "API_CONTRACT.md").read_text(encoding="utf-8")
    start = contract.index("**Account recovery:**")
    end = contract.index("**Password and session controls:**")
    recovery_contract = contract[start:end]

    assert "`413 Payload Too Large`" in recovery_contract
    assert "4,096 bytes" in recovery_contract
    assert "`415 Unsupported Media Type`" in recovery_contract
    assert "`application/json`" in recovery_contract


def test_supabase_migration_matches_alpha_data_model() -> None:
    migration = ROOT / "supabase" / "migrations" / "20260424000001_alpha_core.sql"

    text = migration.read_text(encoding="utf-8").lower()

    for table in (
        "profiles",
        "conversations",
        "messages",
        "strategies",
        "collections",
        "collection_strategies",
        "backtest_runs",
        "feedback",
        "usage_counters",
    ):
        assert f"create table if not exists public.{table}" in text
        assert f"alter table public.{table} enable row level security" in text

    assert "using gin(symbols)" in text
    assert "unique(user_id, resource, period, period_start)" in text
    assert "simulations" not in text
    assert "portfolios" not in text


def test_p1_evidence_spine_migration_freezes_immutable_fields_only() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
    )

    assert (
        "create or replace function public.prevent_idea_version_immutable_update" in text
    )
    assert "create trigger prevent_idea_versions_immutable_update" in text
    assert "before update on public.idea_versions" in text
    assert (
        "create or replace function public.prevent_evidence_artifact_immutable_update"
        in text
    )
    assert "create trigger prevent_evidence_artifacts_immutable_update" in text
    assert "before update on public.evidence_artifacts" in text

    for column in (
        "id",
        "user_id",
        "idea_id",
        "source_conversation_id",
        "source_run_id",
        "version_number",
        "canonical_spec",
        "strategy_snapshot",
        "title",
        "summary",
        "created_at",
    ):
        assert f"new.{column} is distinct from old.{column}" in text

    for column in (
        "id",
        "user_id",
        "idea_id",
        "idea_version_id",
        "source_conversation_id",
        "source_run_id",
        "artifact_type",
        "title",
        "digest",
        "payload",
        "created_at",
    ):
        assert f"new.{column} is distinct from old.{column}" in text

    assert "new.lifecycle is distinct from old.lifecycle" not in text
    assert "new.updated_at is distinct from old.updated_at" not in text


def test_usage_counter_resource_constraint_covers_quota_callers() -> None:
    migration_sql = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
    )
    constraint_index = migration_sql.rfind("usage_counters_resource_check")
    assert constraint_index >= 0
    constraint_sql = migration_sql[constraint_index : constraint_index + 500]

    resources = _usage_counter_resources_from_api_code()
    resources.add("backtest_jobs")

    for resource in resources:
        assert f"'{resource}'" in constraint_sql


def _usage_counter_resources_from_api_code() -> set[str]:
    resources: set[str] = set()
    for path in (ROOT / "src" / "argus" / "api").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not _is_check_and_increment_usage_call(node):
                continue
            for keyword in node.keywords:
                if (
                    keyword.arg == "resource"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    resources.add(keyword.value.value)
    assert resources
    return resources


def _is_check_and_increment_usage_call(node: ast.Call) -> bool:
    names = {"check_and_increment_usage", "check_and_increment_usage_limits"}
    if isinstance(node.func, ast.Attribute):
        return node.func.attr in names
    return isinstance(node.func, ast.Name) and node.func.id in names
