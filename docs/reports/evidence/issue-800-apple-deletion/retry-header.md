# Pending deletion retry header

This bounded follow-up addresses the P3 contract note in
[PR #862's independent review](https://github.com/lagarcess/argus/pull/862#pullrequestreview-5419528930).
When a known pending caller's deletion service returns `None` or its constructor
raises, the route already returns `503 account_deletion_incomplete`. It now also
returns the documented `Retry-After: 5` header. One module constant supplies this
hint and the existing incomplete-response hint.

## Scope and lineage

- Fix-round base: `48ef7fca8752362b54144d800e3a13c53d1a0bc9`.
- Original lane integration base: `f5c83cd88a0af56dc8154a89c6ea4f75d9c518ce`.
- Fetched integration: `7018e0edebbc370b999005a857230bf3c3a1ad8b`, already an
  ancestor through reconciliation merge `bfbe3b0292c97176f3510c69cbfbf53c9cf49001`.
- Runtime changes are confined to `src/argus/api/routers/account.py`. Auth,
  admission, provider calls, durable state, migrations and native code are unchanged.
- Not-started service failures remain `503 account_deletion_unavailable` without
  this retry hint. Unknown admission stays `503 account_deletion_incomplete` with
  its existing hint. Neither response asserts acceptance or completion.

## Regression evidence

Tests use FastAPI's `TestClient`, synthetic requests and mocked service construction.
The existing unavailability test now covers both service construction outcomes
and both known pending and not-started callers. Existing unknown-admission cases
also assert their retained retry header and denial effects.

Before changing production code, the focused regression ran against the base
runtime using Python 3.11.15 and pytest 8.4.2:

```text
PYTHONPATH=web:src:. python -m pytest tests/test_account_deletion_api.py \
  -k 'service_unavailability_preserves_deletion_state or unreadable_admission_state' \
  --no-cov -q

FAILED test_service_unavailability_preserves_deletion_state[True-None]
FAILED test_service_unavailability_preserves_deletion_state[True-construction_error1]
E AssertionError: assert None == '5'
2 failed, 4 passed, 26 deselected, 0 skipped
```

After the fix:

```text
PYTHONPATH=web:src:. python -m pytest tests/test_account_deletion_api.py \
  tests/test_account_deletion_auth.py tests/test_openapi_compatibility.py --no-cov -q
66 passed, 0 failed, 0 skipped

Mocked harness command from tests/evals/README.md, with --no-cov:
272 passed, 0 failed, 0 skipped

Changed-file Ruff check and format check: passed
git diff --check: passed
Merged-tree modularity budget: no violations
```

The first adjacent-suite invocation used an incorrect OpenAPI test filename and
collected no tests. The corrected command above provides the evidence.

## Evidence retained and review handoff

The fetched integration has not moved from the already reconciled base. Its
previous native-button change has no overlap with this response-header delta.
The prior PostgreSQL admission, locking and atomic-receipt evidence remains
applicable because those owners and tests are unchanged. No PostgreSQL, provider,
hosted, phone or paid evaluation was repeated for this header change.

Deslop inspection found no unrelated machinery. The independent no-comments pass
found no scoped comment changes or findings, recommended zero deletions, and made
no edits. Its agent was stopped. No owned process remains running.

The parent release captain will review the final committed delta and report
terminal CI and unresolved review threads. This evidence is not a terminal audit
or a release-readiness claim.
