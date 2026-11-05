# Cuadrao Business E0 Offline Fiscal Engine Implementation Plan

**Repository publication, October 7, 2026 (America/Chicago).** Lucas approved this design, the E0 implementation plan and task-by-task independent review. Counsel may publish and land this documentation-only PR when clean. Lucas will coordinate the existing Business agent for implementation. This publication dispatches no implementation and authorizes no hosted change. See the [decision record](argus-decision-log.md#october-7-2026-business-connected-flow-and-offline-e0-plan).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce reproducible synthetic unsigned invoice XML and honest local evidence, with bounded normalization and no fiscal, money or customer effect.

**Architecture:** Add a pure domain module to the existing Python backend. Separate draft normalization, profile calculation, XML generation, schema validation and immutable evidence. Signer and transport ports remain unavailable outside explicit test doubles.

**Tech Stack:** Repository Python `^3.10`, Pydantic v2, standard-library Decimal/hashlib/json, pytest and Poetry. Propose lxml for offline XML/XSD work; it is not declared or locked in the inspected checkout. Task 0 selects and records a compatible maintained release before any approved dependency change.

**Spec:** [Connected Business flow](cuadrao-business-connected-flow-spec.md), imported from Library `libfile_74ecaa0fb4348191828248df60a54cc4`, version 2. Read the spec with this plan. Lucas approved the plan and task-by-task independent review. Implementation remains with the existing Business agent, coordinated by Lucas.

## Global Constraints

- “No persistence integration, credentials, network calls, certificate handling, live fiscal-number allocation/use, cash effects, customer delivery or production issuance.”
- “Approved, signed and submitted artifacts remain immutable.”
- “Cuadrao must not silently change amounts, tax classification, customer identity, recipient identity, payment allocations or an approved invoice revision.”
- “A required field remains unresolved without source evidence.”
- “Cuadrao must not guess fiscally significant identifier digits or dates.”
- “E0 does not execute network recovery or autonomous AI correction.”
- “Advanced matching and operational recovery remain later milestones.”
- “An XSD pass is one validation result.”
- Preserve all original findings and attempts. Report resolved, proposed and blocked results separately.
- E0 profile proposal: Type 31 service invoice; DOP; positive tax-exclusive lines explicitly assigned 18%; no discounts, retentions, additional taxes or FX.
- Source acquisition in Task 0 is a separate development experiment. The engine, test suite and evidence runner never acquire sources at runtime.
- No API/UI, customer database, migrations, production permissions, WhatsApp integration, accountant export, cash ledger, signing credentials or deployment work.

## Review Focus

1. Ambiguous or malformed input must not become invented facts: Task 1 `test_ambiguous_customer_and_missing_rnc_remain_unresolved`.
2. Reused operation identity with changed input must conflict: Task 4 `test_duplicate_key_changed_input_conflicts`.
3. Missing signature must not become false XSD success: Task 3 `test_official_unsigned_result_preserves_all_findings`.
4. Money precision must not drift or overwrite supplied totals: Task 2 `test_total_conflict_preserves_supplied_and_calculated_values`.
5. XML input or schema imports must not escape offline boundaries: Task 3 `test_external_entities_and_unlisted_imports_are_denied`.

---

## Repository evidence and execution setup

Read-only baseline: `/Users/garces/.codex/worktrees/baaf/private-alpha-next` at `a7a45b1f115cdbccee50562fa69936fbe29c69d8`. Earlier cached integration inspection used `ee4acd50e85a19328a04161c005a6b0cd2b7f4c5`. Neither is a guaranteed future execution base. At execution, inspect active worktrees and coordinate a suitable base before using the worktree skill. Do not reset, switch or write into another agent's checkout.

Existing references:

- `src/argus/domain/ingestion/documents/models.py`: frozen Pydantic models and explicit draft fields.
- `src/argus/domain/recording/money_schemas.py`: amount strings, forbidden extra fields and explicit expected versions.
- `money_service.py`, `money_plan.py`, `money_storage.py`: canonical money orchestration, revision and idempotency patterns. E0 must not call their write paths.
- `src/argus/domain/recording/currency.py`: minor-unit parsing rejects excess precision without rounding. Do not use it to truncate four-decimal fiscal unit prices.
- `src/argus/domain/backtest_admission.py`: shared canonical JSON/hash convention. Its imports include backtesting and usage code; avoid importing that subsystem into E0 merely for hashing. E0 artifact hashing is a separate byte-integrity contract, not another cash or application-idempotency owner.
- `pyproject.toml`: Python, Poetry, pytest, Ruff and mypy conventions. `.github/workflows/ci.yml` uses Poetry pytest commands.
- `tests/conftest.py` imports API state through autouse fixtures. Keep pure E0 tests below `tests/fiscal`; use `--confcutdir=tests/fiscal` to exclude those parent fixtures. Do not modify the shared conftest.
- `src/argus/__init__.py` configures existing logging. Import tests must distinguish that baseline from newly introduced database, network or environment-dependent fiscal behavior.

Standard focused command, from the future approved worktree root:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 poetry run python -m pytest -o addopts='' --confcutdir=tests/fiscal tests/fiscal -q
```

Each task narrows the final path to its named test file. `-o addopts=''` avoids the repository-wide coverage output. These tests need no plugin, credentials or running service. No commands in this plan have been executed as implementation.

## File and type map

All paths below are proposed. No product files have been created.

| File under `src/argus/domain/fiscal/` | Responsibility |
|---|---|
| `__init__.py` | Minimal exports; no setup, environment reads or adapter selection. |
| `models.py` | Frozen input, issue, audit, calculation, artifact and result types. |
| `normalization.py` | Strict JSON input and documented meaning-preserving canonical representation. |
| `sources.py` | Verify source manifest, hashes and local dependency membership. |
| `profiles.py` | One explicitly supported profile, enabled only with verified P0 evidence. |
| `calculation.py` | Decimal arithmetic and independently traceable calculation steps. |
| `xml_artifacts.py` | Deterministic unsigned XML bytes; exact mapping comes from P0. |
| `validation.py` | Safe local XML parsing and unmodified-XSD results. |
| `guards.py` | Pure approval/revision decisions and in-memory operation simulations. |
| `ports.py` | Signer/transport protocols and unavailable implementations. |
| `evidence.py` | Stage-separated result assembly and reproducible evidence packet. |
| `__main__.py` | Synthetic local fixture runner; never a live issuer interface. |

Types are frozen Pydantic models with `extra='forbid'`, except Protocols and the test-only in-memory registry. Collections use tuples. Amounts enter as strings; calculations use Decimal; report JSON emits decimal strings. No model coerces a float into money.

| Public type | Required fields/meaning |
|---|---|
| `DraftInput` | `synthetic: Literal[True]`, `profile_id: str`, `record_id: str`, `revision: int`, `actor_id: str`, `space_id: str`, issuer/buyer snapshots, dates, currency, lines, optional supplied total, source references and optional candidate evidence. |
| `PartyInput` | `name: str | None`, `rnc: str | None`, `source_refs: tuple[str, ...]`. Missing facts remain explicit. |
| `LineInput` | `line_id: str`, `description: str | None`, `quantity: str | None`, `unit_price: str | None`, `tax_rate: str | None`, `source_refs: tuple[str, ...]`. |
| `SourceRef`, `Candidate` | `SourceRef(ref_id: str, source_digest: str, locator: str)`; `Candidate(candidate_id: str, source_refs: tuple[str, ...], explanation: str)`. Candidates are supplied evidence, not a matching engine. |
| `SuppliedField` | `path: str`, `value: str | None`, `source_refs: tuple[str, ...]`. Additional profile facts must match the explicit P0 allowlist; never inject arbitrary XML tags. |
| `Issue` | `code`, `path`, `message`, `source_refs`, `outcome: Literal['resolved','proposed','blocked']`, optional proposed value. Proposals never mutate input. |
| `AuditEvent` | Rule ID/version, original and resulting digests, changed paths, reason and evidence references. A format event changes no field values. |
| `NormalizedDraft` | Original bytes/hash, canonical input bytes/hash, `DraftInput | None`, audit tuple and complete issue tuple. |
| `SourceBundle`, `ProfileRules` | Verified manifest entries and profile support matrix, with exact source/rule digests. No source values are supplied by this plan. |
| `CalculationTrace` | Decimal line bases, taxes and totals; named intermediate steps/rules; supplied total retained separately; complete issues. |
| `UnsignedArtifact` | Immutable bytes, SHA-256, record/revision/input identity and profile/rules/renderer versions. |
| `StageReport` | Stage name, `status: Literal['not_run','passed','failed','unavailable']`, exact findings and source/artifact digests. |
| `EngineResult` | Normalization, calculation, artifact if eligible, stage reports, all findings and separate actionable findings. |
| `Approval`, `AccessDecision` | Explicit actor/space/action/revision/input/artifact identity; decision revision and allowed flag. These are simulation inputs, not production authorization. |
| `OperationRequest`, `OperationState`, `GuardResult` | Stable key, actor/space, logical record/revision/action, payload digest, state/evidence; result allows, replays or blocks. |
| `SignedArtifact`, `SignResult`, `TransportResult` | `SignedArtifact` retains bytes, hash, source unsigned digest, verification report and `mode: Literal['simulated','verified']`. `SignResult` contains this artifact or unavailable/failure. Transport retains separate outcome/evidence, including simulated pending/unknown/rejected/accepted/conditional states. E0 doubles create only simulated artifacts. |

`DraftInput` uses `issuer: PartyInput`, `buyer: PartyInput`, `issued_on: str | None`, `currency: str`, `lines: tuple[LineInput, ...]`, `supplied_total: str | None`, `sources: tuple[SourceRef, ...]`, `customer_candidates: tuple[Candidate, ...]` and `profile_fields: tuple[SuppliedField, ...]` alongside its identity fields. Task 0 fixes the Type 31 allowlist, mapping and requiredness before Tasks 2–3 use them. Unknown cases fail closed rather than inventing a field or rule.

## Task 0: Lock official sources and the precise profile

**Files:** Create `docs/evidence/cuadrao-fiscal-e0/source-lock.md`; `src/argus/domain/fiscal/sources.py`; `src/argus/domain/fiscal/sources/type31/manifest.json`, `type31.xsd` and the dependency files actually discovered; `tests/fiscal/fixtures/type31/support-matrix.json`; `tests/fiscal/test_source_lock.py`. Modify `pyproject.toml` and `poetry.lock` only if the approved execution includes the proposed lxml dependency.

**Interfaces:** `load_source_bundle(root: Path) -> SourceBundle` in `sources.py`. Manifest entries contain original URL, retrieval time, declared version, local relative path, byte length, SHA-256 and import relationships. The source-lock report records the exact supported subset, rounding stages, field precision, XML order and unsigned validation boundary with source sections.

Source acquisition and inspection can start independently. The loader's implementation/test steps consume the general `SourceBundle` model from Task 1. Thus the order is acquisition → Task 1 types → loader tests and P0 review, before any official profile implementation.

- [ ] Retrieve the Type 31 XSD from the official link in spec P0 using a supported browser/download or read-only HTTP route. Retain response status and original bytes. If access fails, record the concrete failure; do not bypass authentication or substitute a mirror as official.
- [ ] Inspect the real XSD and recursively enumerate imports/includes. Acquire the corresponding official dependencies; retain original bytes. Hash each file with SHA-256. Verify that each local path is within the bundle and each dependency is present. Do not invent dependency names or checksum values.
- [ ] Read the cited Format PDF and Technical Report for this restricted profile. Record required/conditional fields, exact line/tax/total rounding sequence, permitted scales and any signature requirement. No inference from a version label alone.
- [ ] Record a maintained lxml release compatible with the execution Python and platform, from official release/package metadata. Pin it through the repository's Poetry workflow after plan approval. Record lxml/libxml2 versions. No install happens during this planning task.
- [ ] Write `test_source_lock_rejects_changed_bytes_missing_import_or_escape` with three failing bundle cases. Implement `load_source_bundle`; run the focused command on `tests/fiscal/test_source_lock.py` until all three fail-closed assertions pass.
- [ ] With the unmodified schema, run a synthetic unsigned validation experiment. Retain every raw error. Classify expected unsigned-stage limitations separately from other failures. Do not add fake `Signature` data or remove requirements from the XSD.
- [ ] Add `test_source_lock_accepts_only_complete_verified_bundle`. Assert every file's real digest, complete import resolution and an explicit reviewed support matrix. A missing bundle is a failing gate, not a skipped/passing fiscal test.
- [ ] Reviewer checkpoint P0: approve actual sources, support matrix, exact rounding stages and unsigned-check boundary. Commit only reviewed source-lock/dependency/test changes in the future worktree.

**Blocked gate:** Until P0 passes, do not implement Type 31 field mapping, fiscal rules, renderer or official golden claims. Tasks 1 and 4 may proceed after plan approval; generic arithmetic/parser tests may use clearly labeled project fixtures. E0 cannot be declared complete while P0 is blocked.

## Task 1: Normalize safely and preserve all input evidence

**Files:** Create `models.py`, `normalization.py`, `tests/fiscal/conftest.py`, `tests/fiscal/test_normalization.py`, and synthetic fixtures under `tests/fiscal/fixtures/`.

**Interfaces:** `normalize_input(raw: bytes) -> NormalizedDraft`. It never guesses fields. Canonical JSON uses UTF-8, sorted object keys and insignificant layout whitespace removal; string values stay exact. `input_sha256` hashes canonical input; `original_sha256` hashes received bytes. Keep the original bytes in evidence. Engineering limits: 1 MiB input and 100 lines maximum; these are E0 resource limits, not DGII limits.

- [ ] Write `test_layout_normalization_preserves_facts_and_records_history`: two JSON layouts yield identical canonical fields/digest; original hashes differ; history identifies the format rule; identifiers and dates are unchanged.
- [ ] Write `test_ambiguous_customer_and_missing_rnc_remain_unresolved`: preserve two supplied synthetic candidates and missing RNC; output contains proposed/blocked issues; no customer selection or cash effect occurs.
- [ ] Write `test_duplicate_json_keys_floats_nonfinite_and_unknown_fields_are_rejected`: no last-key-wins interpretation, float coercion, NaN/Infinity or ignored extras. Test non-UTF-8 and resource-limit failures too.
- [ ] Run `tests/fiscal/test_normalization.py`; confirm failures are missing behavior, not missing environment services.
- [ ] Implement the interface and frozen types. Detect duplicate JSON keys before model validation. Keep parse failures as findings with original evidence. Reject numeric money tokens; never normalize identifier digits, dates, recipients or tax assignments.
- [ ] Re-run the focused file. Add `test_resolved_format_issue_does_not_hide_remaining_errors`: all findings remain in history; only unresolved/proposed items remain actionable.
- [ ] Reviewer checkpoint: compare original/normalized values and evidence. Commit this independently useful normalization/reporting unit.

## Task 2: Calculate exact values under the locked profile

**Files:** Create `profiles.py`, `calculation.py`, `tests/fiscal/test_calculation.py`; extend `models.py`; create `tests/fiscal/fixtures/type31/positive-service.json`, `expected-calculation.json`, `conflicting-total.json` and `missing-rnc.json` after P0.

**Interfaces:** `load_profile(bundle: SourceBundle, profile_id: str) -> ProfileRules`; `calculate(draft: DraftInput, rules: ProfileRules) -> CalculationTrace`; `round_positive(value: Decimal, places: int) -> Decimal`. The last helper uses `ROUND_HALF_UP` and rejects negative/nonfinite inputs. It does not select fiscal rounding stages.

- [ ] Write `test_positive_rounding_boundaries`: `1.004` at two places equals `1.00`; `1.005` equals `1.01`. A four-decimal unit price remains unrounded until the profile's designated operation. Generic rounding tests may precede P0.
- [ ] After P0, write the official-profile assertions from the independently calculated expected fixture. A simple base example is quantity `1`, unit price `100.00`, assigned tax `18%`, yielding base `100.00`, tax `18.00`, total `118.00`. Fractional multi-line expectations must follow P0's verified stages, not assumptions here.
- [ ] Write `test_total_conflict_preserves_supplied_and_calculated_values`: supplied `117.00` remains visible beside calculated `118.00`; outcome requires a decision; no silent replacement or render eligibility.
- [ ] Write `test_unsupported_tax_currency_discount_retention_and_precision_fail_closed`. Include missing explicit tax assignment, FX, nonpositive lines and profile-specific overflow/scale bounds from P0.
- [ ] Run `tests/fiscal/test_calculation.py` and confirm the expected failures.
- [ ] Implement calculation using local Decimal contexts and a versioned rule trace. Never call an LLM, balance totals artificially, or reuse minor-unit parsing to truncate source prices.
- [ ] Re-run the file; reviewer checks independent expected arithmetic, provenance and conflicting-total behavior. Commit.

## Task 3: Produce immutable XML and report actual schema results

**Files:** Create `xml_artifacts.py`, `validation.py`, `tests/fiscal/test_xml_artifacts.py`, `tests/fiscal/test_validation.py`; extend `sources.py`; add explicitly project-owned hostile XML/test schemas under `tests/fiscal/fixtures/security/`.

**Interfaces:** `render_unsigned(draft: DraftInput, calculation: CalculationTrace, rules: ProfileRules) -> UnsignedArtifact`; `validate_unsigned(artifact: UnsignedArtifact, bundle: SourceBundle) -> tuple[StageReport, ...]`. The renderer requires P0 and an eligible calculation. It never adds a digital signature or invented signing timestamp.

- [ ] Write `test_unsigned_xml_is_byte_deterministic_and_escaped`: repeat output is byte-identical; changing a confirmed field/revision changes the digest; Unicode and XML-special characters remain correct; output has no fabricated signature.
- [ ] Write `test_official_unsigned_result_preserves_all_findings` after P0: compare the raw validator result to the observed unmodified-schema experiment. Retain missing-signature and all other errors. Never convert that result into a full signed-document pass.
- [ ] Write `test_external_entities_and_unlisted_imports_are_denied`: test HTTP/file entities, DTDs, entity expansion, external schema references, path traversal and symlink escapes. Assert no resolver fetch/file read outside the verified bundle and no network attempt. Project test schemas never carry an official label.
- [ ] Run both named test files; confirm failures.
- [ ] Implement stable serialization and a fresh hardened parser. Explicitly disable entities, DTD loading/validation, default attributes, network resolution, recovery and huge-tree mode. Reject DOCTYPE; never execute XInclude/XSLT. The resolver allows only manifest-listed local bytes after hash checks; it must raise rather than fall through for every other URI.
- [ ] Keep `unsigned_preparation`, `official_schema`, `signed_envelope` and `fiscal_acceptance` results separate. The latter two stay `not_run`. Unexpected schema errors block readiness. Any expected unsigned limitation remains a visible actual schema failure, with P0's explicit explanation.
- [ ] Run focused tests; reviewer checks serialization against actual P0 order and all negative parser cases. Commit.

## Task 4: Prove revision guards and unavailable external boundaries

**Files:** Create `guards.py`, `ports.py`, `tests/fiscal/test_guards.py`, `tests/fiscal/test_ports.py`; extend `models.py`. No production job runner, database or retry scheduler.

**Interfaces:** `check_approval(artifact: UnsignedArtifact, approval: Approval, access: AccessDecision, action: str) -> GuardResult`; `admit_operation(request: OperationRequest, state: tuple[OperationState, ...]) -> GuardResult`. State is supplied explicitly and retained only in a test harness. `Signer.sign(artifact: UnsignedArtifact, approval: Approval) -> SignResult`; `FiscalTransport.submit(artifact: SignedArtifact, operation: OperationRequest) -> TransportResult`; `FiscalTransport.reconcile(operation: OperationRequest) -> TransportResult`. Default implementations are unavailable. E0 doubles use explicitly simulated signed-artifact evidence, never a fake XML Signature represented as valid. A future live adapter must reject simulated or unverified artifacts; implementing it is outside E0.

- [ ] Write `test_changed_revision_digest_action_or_permission_blocks`: cover changed approval actor/space/revision/input/artifact/action and denied access. A changed draft cannot inherit an old approval.
- [ ] Write `test_duplicate_key_changed_input_conflicts` and `test_identical_retry_replays_same_evidence`: stable identity replays; changed payload conflicts; no extra effect occurs.
- [ ] Write `test_unknown_outcome_blocks_new_key_for_same_logical_document`: unknown state blocks blind resubmit under both old and replacement keys. A status poll or timeout cannot produce an unissued conclusion.
- [ ] Write `test_unavailable_ports_never_report_signed_or_accepted`: default ports return unavailable without I/O. Explicit doubles cover pending, unknown, rejected, accepted and conditionally accepted as simulated results only.
- [ ] Run `tests/fiscal/test_guards.py` and `tests/fiscal/test_ports.py`; confirm failures.
- [ ] Implement pure guards and unavailable ports. Retain independent states, evidence and immutable artifacts. Model bounded retry permission in test policy, but execute no retries or network recovery. Recheck approval and access inputs after a change.
- [ ] Re-run tests; reviewer confirms this is an in-memory boundary proof, not delivered Business isolation, authentication or durable idempotency. Commit.

## Task 5: Assemble reproducible evidence and a synthetic runner

**Files:** Create `evidence.py`, `__main__.py`, `tests/fiscal/test_evidence.py`, `tests/fiscal/test_offline_boundary.py`, `tests/fiscal/README.md`.

**Interfaces:** `prepare(raw: bytes, bundle: SourceBundle) -> EngineResult`; `write_evidence(result: EngineResult, destination: Path) -> tuple[Path, ...]`. The runner accepts `--fixture`, `--sources`, `--output` and mandatory `--synthetic`; it has no live mode, URL fetching, certificate or credential option. Destination must be a new local directory; never silently overwrite evidence.

- [ ] Write `test_evidence_retains_original_all_findings_and_source_hashes`: originals, normalization audit, calculation trace, XML/hash, manifest, versions and complete findings are present. The actionable view excludes only resolved items, not unresolved errors.
- [ ] Write `test_packet_is_reproducible_except_separate_run_envelope`: fixed input/source/tool versions produce identical semantic files; timestamps and environment evidence stay in the separate run envelope.
- [ ] Write `test_fiscal_import_and_runner_have_no_external_effects`: run without credentials and with network denied; forbid API/DB/provider client construction, money writes, dotenv loading and adapter selection from environment. Deny socket creation/connect/DNS in the Python harness. Pair this with Task 3 resolver tests; Python socket mocking alone does not cover native XML I/O.
- [ ] Run the named test files and confirm failures.
- [ ] Implement packet assembly and runner. Exit `0` means only the documented unsigned-preparation milestone passed; output must explicitly show actual schema status, `signed_envelope=not_run` and `fiscal_acceptance=not_run`. Exit `2` means blocked/invalid input/source. Unexpected internal errors remain errors, never synthetic success.
- [ ] Run the complete focused command. Then run `poetry run ruff check src/argus/domain/fiscal tests/fiscal` and `poetry run mypy src/argus/domain/fiscal`. Resolve failures in scope.
- [ ] Run the CLI twice to different directories with the same pinned positive fixture. Run the conflicting-total and missing-RNC fixtures separately. Compare artifacts/hashes and inspect the actionable view alongside complete history.

Example after P0 and implementation:

```sh
poetry run python -m argus.domain.fiscal --synthetic --fixture tests/fiscal/fixtures/type31/positive-service.json --sources src/argus/domain/fiscal/sources/type31 --output /tmp/cuadrao-e0-proof-a
```

- [ ] Obtain one process-level egress-denied run in the approved execution environment. On a Linux host that permits user/network namespaces, use `unshare -Urn` before the same focused pytest command and CLI. If unavailable, use an approved network-denied runner; report the proof blocked rather than skipping it or claiming full isolation from mocks.
- [ ] Reviewer checkpoint: inspect the actual packet, not only test counts. Commit completed E0 work; do not merge, deploy or enable any feature as part of this plan.

## Dependency order and completion gate

After plan approval, Task 0 source acquisition and Task 1 can advance separately. Task 0 loader tests and Task 4 consume Task 1's shared types. Generic Task 2 arithmetic and Task 3 parser tests may use project-owned fixtures. Type 31 rules, renderer, official assertions and final evidence require P0. Task 5 requires the earlier interfaces and P0; blocked source acquisition cannot be hidden behind passing generic tests.

Each implementation task follows red test → observed failure → minimal implementation → green test → review → scoped commit. Commit only named files after inspecting the diff. Lucas approved this plan and task-by-task independent review. Implementation starts only through his coordination with the existing Business agent.

Final packet: exact commit, commands, interpreter/dependency versions, network-denied execution evidence, source manifest and genuine hashes, supported-profile matrix, original/canonical synthetic inputs, normalization audit, independent expected arithmetic, calculation trace, immutable unsigned XML/hash, actual validation findings, simulated guard/port results and concise limitations. It must state **synthetic / unsigned / not submitted / no fiscal acceptance**.

Self-review: all E0 spec criteria map to Tasks 0–5; all five failure modes have owning tests. Identity, evidence, arithmetic and stages stay distinct. P0 remains explicit. Broader Business/Consumer/marketing milestones are dependencies only. No runtime network, certificate, cash, persistence, UI or issuance work entered scope. File creation and commands remain proposed.

## Source references and open gates

The spec's complete DGII and Mobbin register remains authoritative context. P0 uses the exact official Type 31 XSD and PDF links in that register; no checksum or schema import has yet been acquired. The profile's exact rounding sequence remains unverified until P0. The proposed lxml adapter follows its official [validation](https://lxml.de/validation.html) and [resolver](https://lxml.de/resolvers.html) interfaces; dependency version selection remains Task 0 evidence.

Approved execution approach: task-by-task independent implementation/review, because P0, arithmetic and schema reporting need distinct checks. Lucas will coordinate the existing Business agent. This documentation publication does not spawn implementation agents or start execution.
