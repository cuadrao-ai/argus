# Issue 687: private operational log content

## Scope and source trace

Integration base: `ab9143c18740c28f582646d405445c01c4c8aff4`.
This is provider-free development evidence, not deployed verification.

| Source | Reachable sink | Retained diagnostic |
| --- | --- | --- |
| OpenRouter provider exception or Pydantic input values | `log_openrouter_failure`, rendered warning and extras | task, configured model, token limit, exception class, Argus source location |
| User horizon evidence on the typed draft | research routing and scenario compensation INFO | typed route/kind, reason code, asset count |
| Question and unsupported numerical prose | `record_unsourced_figures` INFO | figure count, reason code |
| Model-owned calculation names, references, currencies and fields | shared calculation `_note` INFO | existing reason code |
| Market-data provider exception | both latest-close helpers | exception class |
| Research provider failure detail | `grounded_result` warning | internal reason, HTTP status, transient flag, configured shape |
| Malformed research response, including invalid bracketed URL | parser exception-chain warning | exception class, Argus source location |

Research failure reasons originate in Argus transport/parser code; response detail
is separate and is omitted. Intent, act and question kind are validated enums.
The shared source-location helper reads only code filenames and line numbers,
not exception messages, validation locations, frame locals or exception chains.
No text hashing/truncation or replacement content store was introduced.

## Reproduction and verification

`tests/agent_runtime/test_private_log_content.py` attaches a real serialized
Loguru sink. It checks both rendered text and structured extras using synthetic
private markers. A validation mapping key is included because even validation
field locations can contain user data. The OpenRouter cases exercise a failed
provider/schema attempt followed by successful fallback; the parser case passes
a malformed provider document through the real parser and verifies its unchanged
failure and usage retention. Horizon routing retains evidence in the typed draft;
unsupported-figure reporting preserves its count and reason codes.

All 13 privacy cases fail against the original integration source, extracted with
`git archive` into a temporary directory. All 13 pass with the fix. The focused
OpenRouter, calculation, routing and research suites pass: **1,068 tests**.
Full verification and hosted CI/review results are recorded on the PR after they
complete; this document is not a terminal readiness audit.

Local execution uses Python 3.10 and the existing installed test dependencies,
with `PYTHONPATH=/private/tmp/687-python-deps:src:web`. The shared SciPy macOS 14
wheel failed to load `_spropack`; the official locked 1.15.3 macOS 12 arm64 wheel
was installed in the task-only temporary dependency directory and `scipy.linalg`
was verified. No shared environment was modified.

## Overlap and boundaries

PR #634 remains open/draft and changes calculation/research behavior in the same
files. This patch changes only logging and its tests; none of that PR's model
text, routing or calculation work is imported. Issues #684 (research admission),
#689 (cache identity) and #656 (calculation labels) are unchanged. The API document
change corrects only its description of operational log contents; request,
response, persistence and user-visible contracts are unchanged.

The directly reachable parser warning extends the initial four-file list by one
logging statement. Its source-location helper is moved unchanged from OpenRouter
to the existing logging module so both diagnostics have one owner. This does not
change provider requests, parsing, exception propagation, retries or accounting.
No production conversations/logs, paid evals, browser turns, deploys or shared
configuration changes were used.
