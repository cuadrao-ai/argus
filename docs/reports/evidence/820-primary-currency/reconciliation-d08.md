# Integration reconciliation, October 5

PR #853 retains the same currency transport and sparse profile PATCH behavior.
This report covers the merge and local checks. Independent review and terminal
CI remain with the release coordinator.

Original integration base is `875de09ac2115acec42e09060b92878aa5f18eff`.
Previous published head is `82a5f39c017a8ee1ecb2f4f89a90f9f11f7ca3eb`.
Fetched integration is `d08a133a4e81082ffb3f2738dae92f544cba055a`.
The normal reconciliation merge is `33d9123d504c38ee2b202e94324727afd7650fee`.
No rebase or source repair was needed.

## Semantic overlap

Compared with the previous integration `26c0692d634953bd542a6cca6504138e6e420e6c`,
PR #858 changes Apple credential capture and binds credentials to Auth identities.
Its API and data contract changes concern that capture path. Its migration adds
nullable credential metadata. It does not change the profile table, `/me`
projection, sparse profile updates, or session verification dependencies.
PR #857 changes native provider and sign-in appearance. It does not change the
currency controls or session model. PR #863 repairs the synthetic canary HTTP
server's connection lifecycle. It changes no production auth or canary code.
None adds a profile environment setting.

The merge leaves the published profile route, Supabase gateway, real profile
regression, API dependencies, native ProfileAuthModel, ConnectedCuadraoProfile,
and complete ArgusSession package byte-identical to the previous head.
The existing real profile proof and 23 native session tests remain applicable.
The two saved/restored currency simulator journeys retain evidence for the
unchanged currency controls and transport. They are not new screenshots of the
merged sign-in appearance. PR #857 owns appearance acceptance. No simulator,
Mac build, provider call, or PostgreSQL run was performed for this reconciliation.

## Local checks

Checks ran on the reconciliation merge with the healthy Python 3.11.15 environment.
Python imports used `PYTHONPATH=web:src:.`. The canary test used Bun 1.3.14.

| Check | Result |
| --- | --- |
| Home-country and Supabase API selection, `-k 'not chat and (profile or currency or country)'` | 41 passed, 100 deselected |
| Supabase API `-k patch_me` | 4 passed, 104 deselected |
| Complete `tests/test_private_alpha_canary_split.py` | 23 passed, no skips |
| All ten mocked evaluation files listed in `tests/evals/README.md` | 272 passed, no skips |
| `scripts/check_modularity_budget.py` on the merged tree | No violations |
| `git diff --check` | Passed |

The first canary attempt could not bind loopback sockets inside the sandbox.
It reported 11 failures and 12 passes before the local-server cases could run.
The approved rerun used an empty environment with explicit HOME, PATH, and
PYTHONPATH. All 23 cases passed, including immediate and delayed connection close.
The fixture closed its own servers and test subprocesses exited.

The earlier broad PostgreSQL result remains 625 passed, 3 failed, and 49 warnings.
Two Unicode failures reproduced on unchanged integration and are tracked in #859
and #852. The global-count failure passed alone on unchanged integration.
Concurrent shared-database interference remains an inference, not a proved
runtime baseline defect. This report does not call that suite green.

The evidence-only follow-up commit does not change the checked source tree.
The coordinator records the final published head, fresh independent review,
and terminal CI verdict before any READY claim.
