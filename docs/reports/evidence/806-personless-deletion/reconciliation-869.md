# PR 847 reconciliation with profile initialization, October 5, 2026

Original integration base remains `875de09ac2115acec42e09060b92878aa5f18eff`.
This pass starts from published head `6df7d10957f6de135d4343104c42386039e6c7a5`
and normally merges integration `927740efd7911847bc6deca1c0586905b170ff7d`,
the landed PR 869 whose parent is `5861a8f1b11cfa053e99e2280ddfcfa264abfd66`.
Reconciliation merge and verified behavioral source is
`880dff2d618afad981c162b43a6131842114de82`.
No conflict, rebase, reset, clean or stash occurred. A second pre-publication
fetch confirmed the same integration SHA.

PR 869 adds the default-off Apple name route, one internal profile eligibility
marker, its migration and its API/data/OpenAPI declarations. API and data docs
merged cleanly with the analytics paragraphs. No shared deletion or analytics
runtime source changed. PR 862's admission, identity and credential locks,
recovery and atomic Apple receipt remain intact.

The initializer holds the Auth parent FOR SHARE; deletion admission takes the
same parent's conflicting FOR UPDATE lock. A name command waiting behind an
admitted deletion reads the committed run and refuses to write. The landed
[four transaction cases](../apple-name-backend-20261005/reconciliation-862.md)
prove both orderings and interruption/rollback through the actual deletion
claim. The initializer, router, migration, OpenAPI and those tests are identical
to landed PR 869. No new automatic name writer was introduced.

The earlier [89-case PostgreSQL proof](reconciliation-862.md) is retained:
its deletion/analytics runtime and test sources are unchanged, and the profile
marker migration was already applied on that isolated database during the run.
It therefore already exercised scoped cleanup against the expanded profile
schema. The new marker adds no restrictive foreign key or alternative deletion
owner. The name/deletion race evidence is retained from PR 869. No source change
invalidates either proof, so this pass takes no PostgreSQL lease and makes no
database or provider call. The earlier 155 HTTP checks are also retained and
rerun as part of the expanded cohort below.

Using a stripped `APP_ENV=test` environment, `PYTHONPATH=web:src:.`,
`/private/tmp/cuadrao-scipy-env-20261005/bin/python` and
`--override-ini addopts=''`:

- 197 HTTP/profile/deletion/OpenAPI tests passed in 5.22 seconds, zero failures,
  skips or pytest warnings. This is the prior 155-test selection plus
  `tests/test_apple_name_api.py` and `tests/test_openapi_compatibility.py`.
- 272 tests from the ten-file Mocked Run passed in 9.14 seconds, zero failures,
  skips or pytest warnings.
- Runtime-versus-checked OpenAPI structural parity passed. The checked artifact
  is identical to landed PR 869; no schema regeneration or rewrite was needed.
- Combined-tree modularity has zero violations. Focused Ruff and whitespace pass.

Sanitized output is in [reconciliation-869-verification.txt](reconciliation-869-verification.txt).
The follow-up commit adds only this evidence and does not alter verified code.
Both deletion flags remain false. Actual PostHog completion/readback, project
parity, credentials/scopes, alpha availability, request approval and activation
remain external gates. No hosted, device, paid, provider or real-user action ran.
Independent context review, exact-head CI and guarded merge remain root-owned.
