from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ops.canary_capture_replay import replay_capture

ROOT = Path(__file__).resolve().parents[1]
RENDER_RUNNER = ".github/canary-render.sh"
BROWSER_RUNNER = ".github/canary-browser.sh"
BROWSER_SPEC = "web/e2e/private-alpha-release-canary.spec.ts"
IMPORT_MARKER = (
    'python3 - "$BROWSER_CHECKS_HANDOFF" "$BROWSER_CHECK_EVIDENCE" '
    "\"$BROWSER_RAW_IDS\" <<'PY'"
)
# Besides the release profile's checks, a failure may name a release guard the
# canary keeps or the canary harness itself.
KEPT_RELEASE_GUARDS = {"release_config", "disabled_signup_denial", "welcome_email"}
HARNESS_FAILURE = "canary_harness"


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _shell_function(source: str, name: str) -> str:
    return source.split(f"{name}() {{", 1)[1].split("\n}", 1)[0]


def _function_heredoc(source: str, name: str, marker: str = "python3 - <<'PY'") -> str:
    return source.split(f"{name}() {{", 1)[1].split(marker, 1)[1].split("\nPY", 1)[0]


def _shell_assignment(source: str, name: str) -> str:
    match = re.search(rf'^{name}="([a-z_]+)"$', source, re.MULTILINE)
    assert match, f"{name} is not assigned a check name"
    return match.group(1)


def _required_checks() -> list[str]:
    profile = json.loads(_source(".github/private-alpha-release-profile.json"))
    return list(profile["canary"]["required_steps"])


def _browser_checks() -> list[str]:
    same_commit = _shell_assignment(_source(RENDER_RUNNER), "SAME_COMMIT_CHECK")
    return [check for check in _required_checks() if check != same_commit]


def _approval_validator_source(container: str, response_file: str) -> str:
    marker = f"python3 - \"${response_file}\" <<'PY'"
    return container.split(marker, 1)[1].split("\nPY", 1)[0]


def _approval_validator_result(
    validator_source: str, response_path: Path, payload: object
) -> subprocess.CompletedProcess[str]:
    response_path.write_text(json.dumps(payload), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-c", validator_source, str(response_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_canary_defaults_to_private_launch_urls() -> None:
    source = _source(RENDER_RUNNER)
    env_source = _source(".github/argus-env.sh")

    assert 'APP_URL="${ARGUS_CANARY_APP_URL:-$ARGUS_PRIVATE_LAUNCH_APP_URL}"' in source
    assert 'API_URL="${ARGUS_CANARY_API_URL:-$ARGUS_PRIVATE_LAUNCH_API_URL}"' in source
    assert 'ARGUS_PRIVATE_LAUNCH_APP_URL="https://arguschat.ai"' in env_source
    assert 'ARGUS_PRIVATE_LAUNCH_API_URL="https://api.arguschat.ai"' in env_source


def test_canary_requires_surface_specific_inputs_without_echoing_secrets() -> None:
    source = _source(RENDER_RUNNER)

    assert 'EMAIL="${ARGUS_CANARY_EMAIL:-${MOCK_USER_EMAIL:-}}"' in source
    assert 'PASSWORD="${ARGUS_CANARY_PASSWORD:-${MOCK_USER_PASSWORD:-}}"' in source
    assert 'SIGNUP_RUN_ID="${GITHUB_RUN_ID:-}"' in source
    assert 'SIGNUP_RUN_ATTEMPT="${GITHUB_RUN_ATTEMPT:-}"' in source
    assert 'SIGNUP_LOCAL_NONCE="${ARGUS_CANARY_LOCAL_RUN_NONCE:-}"' in source
    assert "resolve_signup_identity" in source
    assert "ARGUS_CANARY_SUPABASE_SERVICE_ROLE_KEY" in source
    assert 'fail_canary "canary_harness" "missing_canary_email"' in source
    assert 'SURFACE="${ARGUS_CANARY_SURFACE:-}"' in source
    assert 'BROWSER_STORAGE_STATE="$(mktemp)"' in source
    assert 'BROWSER_SESSION_HANDOFF="$(mktemp)"' in source
    assert (
        'fail_canary "canary_harness" "missing_supabase_verifier_credentials"' in source
    )
    assert "set -x" not in source
    assert 'echo "$EMAIL"' not in source
    assert 'echo "$PASSWORD"' not in source


def test_canary_keeps_browser_and_service_role_secrets_out_of_curl_argv() -> None:
    source = _source(RENDER_RUNNER)

    assert 'BROWSER_AUTH_CURL_CONFIG="$(mktemp)"' in source
    assert 'SERVICE_ROLE_CURL_CONFIG="$(mktemp)"' in source
    assert 'chmod 600 "$BROWSER_AUTH_CURL_CONFIG" "$SERVICE_ROLE_CURL_CONFIG"' in source
    assert 'rm -f "$BROWSER_AUTH_CURL_CONFIG"' in source
    assert '"$SERVICE_ROLE_CURL_CONFIG"' in source
    assert '--config "$BROWSER_AUTH_CURL_CONFIG"' in source
    assert '--config "$SERVICE_ROLE_CURL_CONFIG"' in source
    assert "Authorization: Bearer ${BROWSER_ACCESS_TOKEN}" not in source
    assert "apikey: ${SUPABASE_SERVICE_ROLE_KEY}" not in source
    assert "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}" not in source
    assert '-H "Authorization: Bearer ${BROWSER_ACCESS_TOKEN}"' not in source
    assert '-H "apikey: ${SUPABASE_SERVICE_ROLE_KEY}"' not in source
    assert '-H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}"' not in source


def test_every_canary_failure_names_a_check_a_kept_guard_or_the_harness() -> None:
    source = _source(RENDER_RUNNER)
    shell_checks = {
        name: _shell_assignment(source, name)
        for name in ("SAME_COMMIT_CHECK", "SIGN_IN_CHECK")
    }
    allowed = set(_required_checks()) | KEPT_RELEASE_GUARDS | {HARNESS_FAILURE}
    names = re.findall(r'fail_canary "([^"]+)"', source)

    assert names
    for name in names:
        if name == "$BROWSER_FAILED_CHECK":
            # import_browser_check_results only returns the profile's checks.
            continue
        resolved = shell_checks.get(name.removeprefix("$"), name)
        assert resolved in allowed, name
    for check in shell_checks.values():
        assert check in _required_checks()
    harness_contract = _shell_function(source, "validate_canary_harness_contract")
    assert 'for check in "$SAME_COMMIT_CHECK" "$SIGN_IN_CHECK"; do' in harness_contract
    assert (
        'fail_canary "canary_harness" "check_not_in_release_profile"' in harness_contract
    )


def test_same_commit_check_requires_exact_deploys_and_warmup_matches_profile() -> None:
    source = _source(RENDER_RUNNER)
    same_commit = _shell_function(source, "run_same_commit_check")
    guard = _shell_function(source, "run_release_config_guard")

    assert (
        'EXPECT_MODE="${ARGUS_CANARY_EXPECT_MODE:-${ARGUS_WARMUP_EXPECT_MODE:-real-workflow}}"'
        in source
    )
    assert 'CANDIDATE_SHA="${ARGUS_CANARY_SHA:-${GITHUB_SHA:-}}"' in source
    assert 'CHECKED_OUT_SHA="$(git rev-parse HEAD 2>/dev/null || true)"' in source
    for status in ("api-deploy-status", "web-deploy-status", "workflow-version-status"):
        assert f'"$SCRIPT_DIR/render-env-sync.sh" {status}' in same_commit
    for reason in (
        "api_deploy_sha_mismatch",
        "web_deploy_sha_missing",
        "workflow_version_commit_mismatch",
        "workflow_version_id_missing",
    ):
        assert f'fail_canary "$SAME_COMMIT_CHECK" "{reason}"' in same_commit
    assert "workflow_commit_matches_candidate" in same_commit
    assert same_commit.rstrip().endswith('record_check "$SAME_COMMIT_CHECK" "passed"')
    assert (
        'WARMUP_OUTPUT="$(.github/warmup-render.sh --expect-mode "$EXPECT_MODE")"'
        in guard
    )
    assert 'fail_canary "release_config" "release_profile_hash_mismatch"' in guard
    for key in (
        "env_fingerprint",
        "workflow_env_fingerprint",
        "workflow_runtime_provider_mode",
        "workflow_runtime_proof",
    ):
        assert f"extract_warmup_value {key}" in guard
    assert "canary_expected_sha=$CANDIDATE_SHA" in source
    assert "canary_checked_out_sha=$CHECKED_OUT_SHA" in source
    assert "cron-deploy-status" not in source
    assert "canary_cron_deploy" not in source


def test_canary_language_and_check_names_are_profile_owned() -> None:
    source = _source(RENDER_RUNNER)
    runner_source = _source(BROWSER_RUNNER)

    assert 'LANGUAGE="${ARGUS_CANARY_LANGUAGE:-es-419}"' in source
    assert (
        'REQUIRED_CHECKS="$(python3 "$RELEASE_PROFILE_TOOL" canary-checks 2>/dev/null || true)"'
        in source
    )
    assert 'fail_canary "canary_harness" "canary_language_mismatch"' in source
    assert (
        'browser_checks="$(grep -vFx -- "$SAME_COMMIT_CHECK" <<< "$REQUIRED_CHECKS" || true)"'
        in source
    )
    assert 'ARGUS_CANARY_BROWSER_CHECKS="$browser_checks"' in source
    assert 'ARGUS_CANARY_BROWSER_CHAT_PROMPT="$CANARY_CHAT_PROMPT"' in runner_source
    assert (
        'ARGUS_CANARY_BROWSER_RESEARCH_PROMPT="$CANARY_RESEARCH_PROMPT"' in runner_source
    )


def test_render_runner_carries_no_feature_postconditions() -> None:
    source = _source(RENDER_RUNNER)
    runner_source = _source(BROWSER_RUNNER)

    for feature in (
        "verify_api_postconditions",
        "verify_canonical_postconditions",
        "decision_notes",
        "evidence_artifacts",
        "idea_versions",
        "route_receipts",
        "/api/v1/search",
        "FOCUSED_SYMBOL_PATH",
        "result_summary",
        "llm_explain_stage",
        "DECISION_STATE",
        "SEARCH_QUERY",
    ):
        assert feature not in source, feature
    for feature in ("DECISION", "SEARCH_QUERY"):
        assert feature not in runner_source, feature


def test_browser_spec_runs_the_profile_checks_and_no_feature_checks() -> None:
    spec = _source(BROWSER_SPEC)
    registry = spec.split("const CHECKS = new Map", 1)[1].split("]);", 1)[0]

    assert re.findall(r'\["([a-z_]+)",', registry) == _browser_checks()
    assert "process.env.ARGUS_CANARY_BROWSER_CHECKS" in spec
    assert "Browser canary checks do not match the release profile" in spec
    for feature in (
        'label("chat.result_card',
        'label("common.search")',
        "/api/v1/search",
        "page.reload(",
        "page.route(",
        "route.fulfill",
        'page.on("console"',
        "blockingOverlay",
        "chat.simulation_complete",
        "decision",
        "Omnisearch",
        "evidence_artifact",
    ):
        assert feature not in spec, feature


def test_browser_checks_read_product_owned_signals() -> None:
    spec = _source(BROWSER_SPEC)

    assert 'isApiResponse(response, "/me", "GET")' in spec
    assert 'payload?.account_kind !== "registered"' in spec
    assert 'isApiResponse(response, "/conversations", "POST")' in spec
    assert '"/api/v1/chat/stream"' in spec
    assert "backtest" not in spec.lower()
    assert 'page.getByTestId("research-sources-open")' in spec
    assert 'page.getByTestId("user-turn-recovery")' in spec
    assert '"[data-message-id]"' in spec
    # Answer checks judge the persisted turn through the chat's projection, then
    # the message the reopened chat renders by what it announces.
    compact = "".join(spec.split())
    assert "persistedAnswerFailure(page,conversationId,ordinaryAnswerFailure," in compact
    assert "persistedAnswerFailure(page,conversationId,researchAnswerFailure," in compact
    assert "rendered.locator(ANNOUNCEMENT_SELECTOR)" in spec
    support = _source("web/e2e/support/private-alpha-canary-answers.ts")
    # Acceptance derives from the transcript projection, never from saved fields.
    assert "hydrateMessagesFromApi" in support
    assert "metadata" not in support
    assert 'ANNOUNCEMENT_ROLES = ["status", "alert"] as const;' in support


def test_sign_in_retries_once_and_records_the_attempt_count() -> None:
    spec = _source(BROWSER_SPEC)
    source = _source(RENDER_RUNNER)

    assert "const SIGN_IN_ATTEMPTS = 2;" in spec
    assert "result.sign_in_attempts = await openSignedInChat(page);" in spec
    assert "status === 401 || status === 429 || status >= 500" in spec
    assert '"profile_http"' in spec
    assert "class SignInFailure extends CheckFailure" in spec
    assert "if (signInFailed) break;" in spec
    assert '"check_threw"' in spec
    assert "sign_in_attempts" in _function_heredoc(
        source, "import_browser_check_results", IMPORT_MARKER
    )
    browser_surface = _shell_function(source, "run_authenticated_browser_surface")
    assert (
        'fail_canary "$SIGN_IN_CHECK" "authenticated_session_mint_failed"'
        in browser_surface
    )


def test_browser_writes_a_private_check_handoff_the_shell_deletes() -> None:
    source = _source(RENDER_RUNNER)
    runner_source = _source(BROWSER_RUNNER)
    spec = _source(BROWSER_SPEC)
    workflow = _source(".github/workflows/private-alpha-canary.yml")

    assert 'BROWSER_CHECKS_HANDOFF="$(mktemp)"' in source
    assert (
        'chmod 600 "$BROWSER_CHECKS_HANDOFF" "$BROWSER_CHECK_EVIDENCE" "$BROWSER_RAW_IDS"'
        in source
    )
    assert (
        'rm -f "$BROWSER_CHECKS_HANDOFF" "$BROWSER_CHECK_EVIDENCE" "$BROWSER_RAW_IDS"'
        in source
    )
    assert 'ARGUS_CANARY_BROWSER_CHECKS_HANDOFF="$BROWSER_CHECKS_HANDOFF"' in source
    assert "ARGUS_CANARY_BROWSER_CHECKS_HANDOFF" in runner_source
    assert "mode: 0o600" in spec
    # The browser and the importer read one handoff contract file.
    assert 'import handoff from "./support/private-alpha-canary-handoff.json";' in spec
    assert "schema_version: handoff.schema_version," in spec
    assert (
        'CANARY_HANDOFF_CONTRACT="$ROOT_DIR/web/e2e/support/private-alpha-canary-handoff.json"'
        in source
    )
    assert "access_token" not in spec
    assert "BROWSER_CHECKS_HANDOFF" not in workflow


def test_release_coherence_prepares_and_cleans_a_unique_signup_identity() -> None:
    shell_source = _source(RENDER_RUNNER)
    runner_source = _source(BROWSER_RUNNER)

    assert 'SIGNUP_RUN_ID="${GITHUB_RUN_ID:-}"' in shell_source
    assert 'SIGNUP_RUN_ATTEMPT="${GITHUB_RUN_ATTEMPT:-}"' in shell_source
    assert 'SIGNUP_LOCAL_NONCE="${ARGUS_CANARY_LOCAL_RUN_NONCE:-}"' in shell_source
    assert "resolve_signup_identity" in shell_source
    assert 'CANARY_REQUESTED_SIGNUP_DENIAL_EMAIL="$SIGNUP_EMAIL"' in shell_source
    assert "SIGNUP_EMAIL" not in runner_source
    assert "signup_identity_is_safe" in shell_source
    assert "prepare_signup_identity" in shell_source
    assert "delete_signup_auth_identity" in shell_source
    assert "insert_disabled_signup_allowlist" in shell_source
    assert "cleanup_signup_identity" in shell_source
    assert "trap cleanup EXIT" in shell_source

    prepare_body = _shell_function(shell_source, "prepare_signup_identity")
    assert prepare_body.index("delete_signup_auth_identity") < prepare_body.index(
        "insert_disabled_signup_allowlist"
    )

    cleanup_body = _shell_function(shell_source, "cleanup")
    assert "cleanup_signup_identity" in cleanup_body
    assert cleanup_body.index("cleanup_signup_identity") < cleanup_body.index(
        'rm -f "$BROWSER_AUTH_CURL_CONFIG"'
    )

    delete_body = _shell_function(shell_source, "delete_signup_auth_identity")
    assert delete_body.count("collect_signup_auth_user_ids") == 2
    assert '[ ! -s "$SIGNUP_AUTH_USER_IDS" ]' in delete_body

    release_body = _shell_function(shell_source, "run_release_coherence_surface")
    assert release_body.index("signup_identity_is_safe") < release_body.index(
        "prepare_signup_identity"
    )
    assert release_body.index("prepare_signup_identity") < release_body.index(
        "run_disabled_signup_denial_canary"
    )


def test_release_coherence_denies_disabled_signup_before_welcome_approval() -> None:
    shell_source = _source(RENDER_RUNNER)
    runner_source = _source(BROWSER_RUNNER)
    release_body = _shell_function(shell_source, "run_release_coherence_surface")
    staging_body = _shell_function(shell_source, "stage_requested_signup_allowlist")
    approval_body = _shell_function(shell_source, "approve_requested_signup_allowlist")

    assert '"role": "user"' in shell_source
    assert '"disabled_at":' in shell_source
    assert "run_disabled_signup_denial_canary" in shell_source
    assert "verify_no_signup_auth_identity" in shell_source
    assert "stage_requested_signup_allowlist" in shell_source
    assert "approve_requested_signup_allowlist" in shell_source
    assert "enable_disabled_signup_allowlist" not in shell_source
    assert "-d '{\"disabled_at\":null}'" not in shell_source
    assert 'OPS_CURL_CONFIG="$(mktemp)"' in shell_source
    assert 'SIGNUP_APPROVAL_REQUEST="$(mktemp)"' in shell_source
    assert 'chmod 600 "$OPS_CURL_CONFIG"' in shell_source
    assert 'chmod 600 "$SIGNUP_APPROVAL_REQUEST"' in shell_source
    assert 'rm -f "$OPS_CURL_CONFIG"' in shell_source
    assert 'rm -f "$SIGNUP_APPROVAL_REQUEST"' in shell_source
    assert 'fail_canary "canary_harness" "missing_ops_token"' in shell_source
    assert 'header = "Authorization: Bearer %s"' in shell_source
    assert '"$OPS_TOKEN"' in shell_source
    approval_curl_line = next(
        line.strip() for line in approval_body.splitlines() if "curl " in line
    )
    assert approval_curl_line.startswith("curl -q ")
    assert '--config "$OPS_CURL_CONFIG"' in approval_body
    assert '"${API_URL}${approve_path}"' in approval_body
    assert "/internal/access-requests/approve" not in shell_source
    resolver_body = _shell_function(shell_source, "resolve_approve_path")
    assert "from argus.api.ops_contract import ACCESS_REQUEST_APPROVE_PATH" in (
        resolver_body
    )
    assert 'approve_path="$(resolve_approve_path)"' in approval_body
    assert 'CANARY_SIGNUP_EMAIL="$SIGNUP_EMAIL"' in approval_body
    assert ".strip().casefold()" in approval_body
    assert '--data-binary "@$SIGNUP_APPROVAL_REQUEST"' in approval_body
    assert 'set(payload) != {"approved"}' in approval_body
    assert 'payload["approved"] is not True' in approval_body
    assert "service_role_curl" not in approval_body
    assert "-X PATCH" not in approval_body
    assert '-d \'{"role":"requested","disabled_at":null}\'' in staging_body
    assert "role=eq.user" in staging_body
    assert "disabled_at=not.is.null" in staging_body
    assert "Authorization: Bearer ${CUADRAO_OPS_TOKEN}" not in shell_source

    assert (
        release_body.index("prepare_signup_identity")
        < release_body.index("run_disabled_signup_denial_canary")
        < release_body.index("verify_no_signup_auth_identity")
        < release_body.index("stage_requested_signup_allowlist")
        < release_body.index("approve_requested_signup_allowlist")
        < release_body.index("verify_welcome_delivery_recorded")
    )
    assert (
        'fail_canary "disabled_signup_denial" "disabled_signup_was_not_denied"'
        in release_body
    )
    assert "run_browser_checks" not in release_body

    assert "ARGUS_CANARY_BROWSER_STORAGE_STATE" in runner_source
    assert "-u SUPABASE_SERVICE_ROLE_KEY" in runner_source
    assert "-u ARGUS_CANARY_SUPABASE_SERVICE_ROLE_KEY" in runner_source
    assert 'ARGUS_CANARY_SUPABASE_SERVICE_ROLE_KEY="' not in runner_source
    assert "if ! env -u CUADRAO_OPS_TOKEN" in shell_source
    assert "-u SUPABASE_SERVICE_ROLE_KEY" in shell_source
    assert "-u ARGUS_CANARY_SUPABASE_SERVICE_ROLE_KEY" in shell_source


def test_release_coherence_reads_the_delivery_back_and_cleans_artifacts() -> None:
    shell_source = _source(RENDER_RUNNER)
    release_body = _shell_function(shell_source, "run_release_coherence_surface")
    readback_body = _shell_function(shell_source, "verify_welcome_delivery_recorded")
    artifacts_body = _shell_function(shell_source, "cleanup_welcome_artifacts")
    cleanup_body = _shell_function(shell_source, "cleanup_signup_identity")
    prepare_body = _shell_function(shell_source, "prepare_signup_identity")

    # The HTTP 200 alone cannot distinguish a real send from a no-send
    # replay; the canary must read the delivery row written by this run.
    assert 'fail_canary "welcome_email" "welcome_delivery_not_recorded"' in release_body
    assert "private_alpha_access_welcome_deliveries" in readback_body
    assert "provider_receipt" in readback_body
    assert "sent_at" in readback_body
    assert "CANARY_RUN_STARTED_AT" in readback_body
    assert "sent < started" in readback_body
    assert 'CANARY_RUN_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"' in shell_source

    # Every row the canary writes must be deletable by the canary itself.
    assert "delete_private_alpha_access_welcome_artifacts" in artifacts_body
    assert "service_role_curl" in artifacts_body
    assert "welcome artifact cleanup was refused" in artifacts_body
    assert cleanup_body.index("delete_signup_allowlist") < cleanup_body.index(
        "cleanup_welcome_artifacts"
    )
    assert prepare_body.index("delete_signup_allowlist") < prepare_body.index(
        "cleanup_welcome_artifacts"
    )


def test_approval_response_validators_require_exact_boolean_shape(
    tmp_path: Path,
) -> None:
    shell_source = _source(RENDER_RUNNER)
    approval_body = _shell_function(shell_source, "approve_requested_signup_allowlist")
    runbook = _source("docs/PRIVATE_LAUNCH_RUNBOOK.md")
    promotion_section = runbook.split("### Requested Access Promotion", 1)[1]
    validators = (
        _approval_validator_source(
            approval_body,
            "SIGNUP_ALLOWLIST_RESPONSE",
        ),
        _approval_validator_source(promotion_section, "APPROVAL_RESPONSE"),
    )
    response_path = tmp_path / "approval-response.json"

    for validator_source in validators:
        assert (
            _approval_validator_result(
                validator_source,
                response_path,
                {"approved": True},
            ).returncode
            == 0
        )
        for invalid_payload in (
            {"approved": 1},
            {"approved": 1.0},
            {"approved": True, "unexpected": "field"},
            {"approved": False},
            {},
        ):
            assert (
                _approval_validator_result(
                    validator_source,
                    response_path,
                    invalid_payload,
                ).returncode
                != 0
            )


def test_runbook_promotion_recipe_is_fail_fast_and_subshell_scoped() -> None:
    runbook = _source("docs/PRIVATE_LAUNCH_RUNBOOK.md")
    promotion_section = runbook.split("### Requested Access Promotion", 1)[1]
    recipe = promotion_section.split("```bash", 1)[1].split("```", 1)[0].strip()
    curl_line = next(line.strip() for line in recipe.splitlines() if "curl " in line)

    assert recipe.startswith("(\nset -euo pipefail\n")
    assert recipe.endswith("\n)")
    assert curl_line.startswith("curl -q ")
    assert (
        'trap \'rm -f "$OPS_CURL_CONFIG" "$APPROVAL_REQUEST" '
        '"$APPROVAL_RESPONSE"\' EXIT'
    ) in recipe
    assert 'set(payload) != {"approved"}' in recipe
    assert 'payload["approved"] is not True' in recipe


def test_runbook_generates_a_fresh_local_canary_nonce() -> None:
    runbook = _source("docs/PRIVATE_LAUNCH_RUNBOOK.md")
    command = runbook.split("mkdir -p temp/release-evidence", 1)[1].split("```", 1)[0]

    assert 'ARGUS_CANARY_LOCAL_RUN_NONCE="$(poetry run python -c' in command
    assert "secrets.token_hex" in command


def test_disabled_signup_denial_probes_policy_instead_of_signup() -> None:
    shell_source = _source(RENDER_RUNNER)
    denial_body = _shell_function(shell_source, "run_disabled_signup_denial_canary")

    assert "canary-requested-signup-denial.py" in denial_body
    assert 'CANARY_REQUESTED_SIGNUP_DENIAL_API_URL="$API_URL"' in denial_body
    assert 'CANARY_REQUESTED_SIGNUP_DENIAL_EMAIL="$SIGNUP_EMAIL"' in denial_body
    assert 'CANARY_REQUESTED_SIGNUP_DENIAL_OPS_TOKEN="$OPS_TOKEN"' in denial_body
    assert "env -u CUADRAO_OPS_TOKEN" in denial_body
    assert "-u SUPABASE_SERVICE_ROLE_KEY" in denial_body
    assert "-u ARGUS_CANARY_SUPABASE_SERVICE_ROLE_KEY" in denial_body
    assert "run_browser_checks" not in denial_body
    assert "access-denial" not in shell_source
    assert "/api/v1/auth/signup" not in _source(
        ".github/canary-requested-signup-denial.py"
    )


@pytest.mark.parametrize(
    ("run_id", "run_attempt", "local_nonce", "expected"),
    [
        ("123456", "2", "", "delivered+argus-123456-2@resend.dev"),
        ("١٢٣", "2", "", None),
        ("123", "٢", "", None),
        ("", "", "review-abc123", "delivered+argus-local-review-abc123@resend.dev"),
        ("", "", "a", None),
        ("", "", "a" * 43, None),
    ],
)
def test_canary_resolves_ci_and_local_signup_identities(
    run_id: str, run_attempt: str, local_nonce: str, expected: str | None
) -> None:
    shell_source = _source(RENDER_RUNNER)
    function_body = _shell_function(shell_source, "resolve_signup_identity")
    python_source = function_body.split("python3 - <<'PY'", 1)[1].split("\nPY", 1)[0]
    result = subprocess.run(
        [sys.executable, "-c", python_source],
        cwd=ROOT,
        env={
            **os.environ,
            "CANARY_SIGNUP_RUN_ID": run_id,
            "CANARY_SIGNUP_RUN_ATTEMPT": run_attempt,
            "CANARY_SIGNUP_LOCAL_NONCE": local_nonce,
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == (0 if expected else 1)
    assert result.stdout.strip() == (expected or "")


@pytest.mark.parametrize(
    ("run_id", "run_attempt", "local_nonce", "signup_email", "expected"),
    [
        ("123456", "2", "", "delivered+argus-123456-2@resend.dev", 0),
        ("١٢٣", "2", "", "delivered+argus-١٢٣-2@resend.dev", 1),
        ("123", "٢", "", "delivered+argus-123-٢@resend.dev", 1),
        ("", "", "review-abc123", "delivered+argus-local-review-abc123@resend.dev", 0),
        ("", "", "", "", 1),
        ("123456", "", "", "", 1),
        ("", "2", "", "", 1),
        ("123456", "2", "review-abc123", "", 1),
        ("", "", "Review", "", 1),
        ("", "", "review_1", "", 1),
        ("", "", "-review", "", 1),
        ("", "", "review-", "", 1),
        ("", "", "a", "delivered+argus-local-a@resend.dev", 1),
        ("", "", "review-1", "arbitrary@example.com", 1),
    ],
)
def test_canary_rejects_unsafe_signup_identity_modes_before_destructive_setup(
    run_id: str,
    run_attempt: str,
    local_nonce: str,
    signup_email: str,
    expected: int,
) -> None:
    shell_source = _source(RENDER_RUNNER)
    function_body = _shell_function(shell_source, "signup_identity_is_safe")
    python_source = function_body.split("python3 - <<'PY'", 1)[1].split("\nPY", 1)[0]

    def run_safety_check(
        *,
        login_email: str,
        signup_email: str,
        local_nonce: str,
    ) -> int:
        env = os.environ.copy()
        env.update(
            {
                "CANARY_LOGIN_EMAIL": login_email,
                "CANARY_SIGNUP_EMAIL": signup_email,
                "CANARY_SIGNUP_RUN_ID": run_id,
                "CANARY_SIGNUP_RUN_ATTEMPT": run_attempt,
                "CANARY_SIGNUP_LOCAL_NONCE": local_nonce,
            }
        )
        return subprocess.run(
            [sys.executable, "-c", python_source],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        ).returncode

    assert (
        run_safety_check(
            login_email="confirmed@example.com",
            signup_email=signup_email,
            local_nonce=local_nonce,
        )
        == expected
    )
    if expected == 0:
        assert (
            run_safety_check(
                login_email=signup_email,
                signup_email=signup_email,
                local_nonce=local_nonce,
            )
            == 1
        )
        assert (
            run_safety_check(
                login_email="",
                signup_email=signup_email,
                local_nonce=local_nonce,
            )
            == 0
        )
    assert (
        run_safety_check(
            login_email="confirmed@example.com",
            signup_email="arbitrary@example.com",
            local_nonce=local_nonce,
        )
        != 0
    )

    release_body = _shell_function(shell_source, "run_release_coherence_surface")
    safety_gate = release_body.index("signup_identity_is_safe")
    prepare = release_body.index("prepare_signup_identity")
    assert safety_gate < prepare
    assert "delete_signup_auth_identity" not in release_body[:safety_gate]


def test_canary_writes_only_privacy_safe_human_evidence() -> None:
    source = _source(RENDER_RUNNER)
    builder = source.split("build_release_evidence_json() {", 1)[1].split(
        "\nwrite_json_artifact() {", 1
    )[0]
    importer = _function_heredoc(source, "import_browser_check_results", IMPORT_MARKER)

    assert 'EVIDENCE_PATH="${ARGUS_CANARY_EVIDENCE_PATH:-}"' in source
    assert 'CAPTURE_PATH="${ARGUS_CANARY_CAPTURE_PATH:-}"' in source
    assert '"privacy": "no_raw_ids; labels are sha256 prefixes"' in builder
    assert "CANARY_USER_ID" not in builder
    assert "hashlib.sha256" in importer
    assert 'CANARY_RAW_IDS_FILE="$BROWSER_RAW_IDS"' in source
    assert "privacy-safe canary artifact contained a raw private identifier" in source
    assert "path.chmod(0o600)" in source


def test_canary_capture_remains_sanitized_and_replay_compatible() -> None:
    source = _source(RENDER_RUNNER)
    capture_body = source.split("write_canary_capture() {", 1)[1].split(
        "\nprepare_capture_destination() {", 1
    )[0]

    assert "scripts.ops.canary_capture_sanitizer" in capture_body
    assert "assert_sanitized_capture" in capture_body
    assert 'CANARY_MESSAGES_FILE="$API_MESSAGES_RESPONSE"' in capture_body
    assert 'CANARY_JOB_RESPONSE_FILE="$API_JOB_RESPONSE"' in capture_body
    assert '"launch_payload": {' in capture_body
    assert (
        '"final_response_payload": message_artifacts.get("final_response_payload")'
        in capture_body
    )
    assert "route_receipt" not in capture_body


def test_canary_capture_builder_produces_a_replayable_artifact(tmp_path: Path) -> None:
    source = _source(RENDER_RUNNER)
    capture_body = source.split("write_canary_capture() {", 1)[1].split(
        "\nprepare_capture_destination() {", 1
    )[0]
    python_source = capture_body.split("python3 - <<'PY' || exit_code=$?", 1)[1].split(
        "\nPY", 1
    )[0]
    failed_check = _browser_checks()[1]
    capture_path = tmp_path / "capture.json"
    messages_path = tmp_path / "messages.json"
    job_path = tmp_path / "job.json"
    messages_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "role": "assistant",
                        "metadata": {
                            "final_response_payload": {
                                "result": {
                                    "total_return": 0.1284,
                                    "benchmark_return": 0.2614,
                                },
                                "explanation_context": {"benchmark_symbol": "SPY"},
                            },
                            "result_card": {
                                "title": "AAPL + MSFT",
                                "benchmark_symbol": "SPY",
                            },
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    job_path.write_text("{}", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "CANARY_CAPTURE_PATH": str(capture_path),
            "CANARY_STATUS": "failed",
            "CANARY_FAILED": failed_check,
            "CANARY_FAILURE_REASON": "backtest_job_failed_market_data_unavailable",
            "CANARY_RELEASE_EVIDENCE_JSON": json.dumps({"language": "es-419"}),
            "CANARY_MESSAGES_FILE": str(messages_path),
            "CANARY_JOB_RESPONSE_FILE": str(job_path),
        }
    )

    result = subprocess.run(
        [sys.executable, "-c", python_source],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    assert capture["failure"] == {
        "failed": failed_check,
        "reason": "backtest_job_failed_market_data_unavailable",
        "status": "failed",
    }
    assert capture["final_response_payload"]["result"]["total_return"] == 0.1284
    assert replay_capture(capture)["quick_take"]
    assert stat.S_IMODE(capture_path.stat().st_mode) == 0o600


def test_browser_failure_collects_capture_inputs_before_naming_the_failed_check() -> None:
    source = _source(RENDER_RUNNER)
    browser_surface = _shell_function(source, "run_authenticated_browser_surface")
    failure = browser_surface.split("if ! run_browser_checks; then", 1)[1].split(
        "\n  fi\n", 1
    )[0]
    recovery = _shell_function(source, "recover_browser_failure_capture_inputs")

    assert 'fail_canary "canary_harness" "browser_artifact_probe_${ARTIFACT_PROBE}"' in (
        failure
    )
    assert (
        failure.index("import_browser_check_results")
        < failure.index("recover_browser_failure_capture_inputs")
        < failure.index('fail_canary "$BROWSER_FAILED_CHECK" "$BROWSER_FAILURE_REASON"')
    )
    assert 'fail_canary "canary_harness" "browser_checks_exited_red"' in failure
    assert "${API_URL}/api/v1/conversations/${FAILED_CONVERSATION_ID}/messages" in (
        recovery
    )
    assert "${API_URL}/api/v1/backtest-jobs/${FAILED_BACKTEST_JOB_ID}" in recovery
    assert '--config "$BROWSER_AUTH_CURL_CONFIG"' in recovery
    assert "service_role_curl" not in recovery


def test_browser_surface_requires_every_browser_check_to_pass() -> None:
    source = _source(RENDER_RUNNER)
    browser_surface = _shell_function(source, "run_authenticated_browser_surface")
    success = browser_surface.split("if ! run_browser_checks; then", 1)[1].split(
        "\n  fi\n", 1
    )[1]

    assert (
        success.index("import_browser_check_results")
        < success.index('if [ -n "$BROWSER_FAILED_CHECK" ]; then')
        < success.index("run_same_commit_check")
        < success.index("revoke_browser_session_once")
        < success.index('CANARY_STATUS="passed"')
    )
    assert 'fail_canary "canary_harness" "browser_check_handoff_invalid"' in success


def test_browser_failure_is_not_classified_as_a_captcha_failure() -> None:
    source = _source(RENDER_RUNNER)
    browser_surface = _shell_function(source, "run_authenticated_browser_surface")

    assert "browser_auth_challenge_timed_out" not in source
    assert "captcha_challenge_timeout" not in source
    assert browser_surface.index("mint_browser_session_state") < browser_surface.index(
        "run_browser_checks"
    )


def test_cleanup_redacts_browser_artifacts_before_the_job_uploads_them() -> None:
    source = _source(RENDER_RUNNER)
    cleanup_body = _shell_function(source, "cleanup")

    assert "redact_browser_artifacts || true" in cleanup_body
    assert cleanup_body.index("redact_browser_artifacts") < cleanup_body.index(
        'rm -f "$BROWSER_CHECKS_HANDOFF"'
    )


def test_browser_artifact_redaction_masks_canary_credentials(tmp_path: Path) -> None:
    source = _source(RENDER_RUNNER)
    function_body = _shell_function(source, "redact_browser_artifacts")
    python_source = function_body.split("python3 - <<'PY'", 1)[1].split("\nPY", 1)[0]
    results = tmp_path / "playwright-results" / "case"
    results.mkdir(parents=True)
    context_path = results / "error-context.md"
    context_path.write_text(
        '- textbox "Contrasena": canary-password-value\n'
        '- textbox "Correo": operator@example.test\n'
        '- textbox "Correo": delivered@resend.dev\n',
        encoding="utf-8",
    )
    screenshot_path = results / "test-failed-1.png"
    screenshot_path.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\x00")

    env = os.environ.copy()
    env.update(
        {
            "CANARY_REDACT_DIR": str(tmp_path / "playwright-results"),
            "CANARY_REDACT_PASSWORD": "canary-password-value",
            "CANARY_REDACT_EMAIL": "operator@example.test",
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", python_source],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    redacted = context_path.read_text(encoding="utf-8")
    assert "canary-password-value" not in redacted
    assert "operator@example.test" not in redacted
    assert redacted.count("<redacted>") == 2
    # The Resend test recipient is non-secret and stays readable for triage.
    assert "delivered@resend.dev" in redacted
    assert not screenshot_path.exists()
    assert stat.S_IMODE(context_path.stat().st_mode) == 0o600
    assert (tmp_path / "playwright-results" / ".redacted").is_file()


def test_browser_artifact_redaction_leaves_no_marker_without_a_results_dir(
    tmp_path: Path,
) -> None:
    source = _source(RENDER_RUNNER)
    function_body = _shell_function(source, "redact_browser_artifacts")
    python_source = function_body.split("python3 - <<'PY'", 1)[1].split("\nPY", 1)[0]
    results_dir = tmp_path / "playwright-results"
    results_dir.mkdir()

    env = os.environ.copy()
    env.update(
        {
            "CANARY_REDACT_DIR": str(results_dir),
            "CANARY_REDACT_PASSWORD": "",
            "CANARY_REDACT_EMAIL": "",
        }
    )
    subprocess.run(
        [sys.executable, "-c", python_source],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert 'local results_dir="web/temp/playwright-results"' in function_body
    assert '[ -d "$results_dir" ] || return 0' in function_body
    assert (results_dir / ".redacted").is_file()


def test_failed_browser_run_is_reported_as_failed_not_not_run() -> None:
    source = _source(RENDER_RUNNER)
    runner_body = _shell_function(source, "run_browser_checks")

    assert 'BROWSER_STATUS="failed"' in runner_body


def test_canary_writes_privacy_safe_failure_evidence() -> None:
    source = _source(RENDER_RUNNER)
    fail_body = _shell_function(source, "fail_canary")

    assert 'CANARY_STATUS="running"' in source
    assert 'CANARY_STATUS="failed"' in fail_body
    assert 'CANARY_FAILED="$1"' in fail_body
    assert 'CANARY_FAILURE_REASON="$2"' in fail_body
    assert 'record_check "$CANARY_FAILED" "failed"' in fail_body
    assert (
        'echo "ERROR: canary failed at ${CANARY_FAILED}: ${CANARY_FAILURE_REASON}"'
        in fail_body
    )
    assert "write_canary_evidence" in fail_body
    assert "write_canary_capture" in fail_body
    assert '"failed": optional(os.environ["CANARY_FAILED"])' in source
    assert '"checks": checks' in source


def test_canary_requires_writable_capture_destination_before_browser_spend() -> None:
    source = _source(RENDER_RUNNER)
    preflight_body = _shell_function(source, "prepare_capture_destination")
    browser_body = _shell_function(source, "run_authenticated_browser_surface")
    release_body = _shell_function(source, "run_release_coherence_surface")

    assert 'fail_canary "canary_harness" "missing_capture_destination"' in preflight_body
    assert (
        'fail_canary "canary_harness" "capture_destination_not_writable"'
        in preflight_body
    )
    assert ': > "$CAPTURE_PATH"' in preflight_body
    assert 'rm -f "$CAPTURE_PATH"' in preflight_body
    assert release_body.index("prepare_capture_destination") < release_body.index(
        "validate_canary_harness_contract"
    )
    assert browser_body.index("prepare_capture_destination") < browser_body.index(
        "run_browser_checks"
    )


def test_capture_write_failure_is_explicit_in_human_safe_evidence() -> None:
    source = _source(RENDER_RUNNER)
    fail_body = _shell_function(source, "fail_canary")

    assert 'CANARY_CAPTURE_WRITE_STATUS="failed"' in fail_body
    assert 'CANARY_CAPTURE_WRITE_FAILURE_REASON="capture_write_failed"' in fail_body
    assert "canary_capture_write_status=" in fail_body
    assert fail_body.index("write_canary_capture") < fail_body.index(
        "write_canary_evidence"
    )
    assert '"capture_write_status":' in source
    assert '"capture_write_failure_reason":' in source


def test_canary_sanitizes_warmup_output_before_logging() -> None:
    source = _source(RENDER_RUNNER)

    assert "print_sanitized_warmup_output" in source
    assert 'printf "%s\\n" "$WARMUP_OUTPUT"' not in source
    assert "stale_job_scan_status=" in source
    assert "unresolved_jobs" in source
    assert "user_id" in source
    assert "task_run_id" in source
    assert "<redacted>" in source


def test_workflow_runs_browser_checks_and_uploads_only_sanitized_artifacts() -> None:
    workflow = _source(".github/workflows/private-alpha-canary.yml")
    browser_job = workflow.split("  authenticated-browser-journey:\n", 1)[1]

    frontend_dependencies = browser_job.index("Install frontend dependencies")
    chromium = browser_job.index("Install Chromium for the authenticated browser canary")
    browser_checks = browser_job.index("Run authenticated browser checks")

    assert frontend_dependencies < chromium < browser_checks
    assert "spanish-ui-smoke" not in workflow
    assert ".github/local-smoke.sh" not in browser_job
    assert (
        "ARGUS_CANARY_EVIDENCE_PATH=temp/canary-evidence/authenticated-browser.json"
        in browser_job
    )
    assert (
        "ARGUS_CANARY_CAPTURE_PATH=temp/canary-evidence/authenticated-browser-capture.json"
        in browser_job
    )
    assert "temp/canary-evidence/*" not in workflow
    assert "temp/canary-evidence/authenticated-browser.json" in browser_job
    assert "temp/canary-evidence/authenticated-browser.exit" in browser_job
    assert "Upload failed authenticated-browser capture" in browser_job
    failed_capture_upload = browser_job.split(
        "Upload failed authenticated-browser capture", 1
    )[1]
    assert "if: failure()" in failed_capture_upload
    assert (
        "temp/canary-evidence/authenticated-browser-capture.json" in failed_capture_upload
    )
    assert "BROWSER_CHECKS_HANDOFF" not in workflow


def test_successful_canary_does_not_write_replay_capture() -> None:
    source = _source(RENDER_RUNNER)
    success_body = source.split('CANARY_STATUS="passed"', 1)[1]

    assert "write_canary_evidence" in success_body
    assert "write_canary_capture" not in success_body.split("\n}", 1)[0]


def test_browser_runner_is_profile_driven_and_executable() -> None:
    runner_source = _source(BROWSER_RUNNER)
    mode = (ROOT / BROWSER_RUNNER).stat().st_mode

    assert "private-alpha-release-profile.py" in runner_source
    assert "static-key-values" in runner_source
    for field in ("chat_prompt", "research_prompt"):
        assert f"canary-value {field}" in runner_source
    assert "private-alpha-release-canary.spec.ts" in runner_source
    assert "ARGUS_CANARY_BROWSER_CHECKS_HANDOFF" in runner_source
    assert 'ARGUS_CANARY_BROWSER_CHECKS="$BROWSER_CHECKS"' in runner_source
    assert "PLAYWRIGHT_BASE_URL" in runner_source
    assert mode & stat.S_IXUSR


def test_render_canary_runner_is_executable() -> None:
    mode = (ROOT / RENDER_RUNNER).stat().st_mode

    assert mode & stat.S_IXUSR
