# Trust landing reconciliation

Paired transfers retain each account's actual amount and currency. This
reconciliation adds no behavior or activation. The original integration base
remains `875de09ac2115acec42e09060b92878aa5f18eff`. Previous worker head is
`2338deab87c0dc6bbd606544197f5a58ce8307c4`, based on integration
`fc4057c8789d3e3504fcb0e980344d6bf51e66c0`.

Freshly fetched integration is `70b0cd3891937f026900aceb96ce5f556c76b0b3`.
It contains #862 Apple deletion admission, #849 app privacy reasons, #869
Apple name initialization and #847 personless analytics deletion. The normal
integration merge completed without conflicts at
`7770f1c1955711c70ef856eb60be1ac876c1bcc9`. This is the measured executable
head. The later evidence commit changes only this folder. Pending-merge
inspection and cancellation readback confirmed no auto-merge or queue request.

## Owner and contract overlap

The financial posting, Planning and Household runtime trees and all affected
financial fixtures are byte-identical to the previous worker head. The shared
profile PATCH router, Supabase profile gateway and Household deletion helper
are also unchanged. Paired transactions use their explicit account currencies
and amounts. Profile primary currency is not an exchange rate or another amount.
Prior financial PostgreSQL evidence therefore remains applicable.

Incoming deletion changes validate Apple admission, credential revocation and
provider cleanup states. They preserve the existing Household deletion helper
and do not change the paired recording transaction, immutable financial posting
or denomination checks. Incoming Apple name initialization adds a name-only
monotonic marker and triggers to `public.profiles`; it does not alter financial
columns, account currency or posting ownership. Their own changed identity,
name and deletion fixtures belong to the landed slices. This worker did not
rerun those slices' PostgreSQL acceptance or claim their proof as financial proof.

The shared API and data documentation and OpenAPI artifact merge cleanly.
Running `scripts/generate_openapi_artifact.py` on the merged runtime produces
exactly the merged `docs/api/openapi.yaml`, with no diff. The artifact retains
the new name and deletion APIs together with `destination_amount`.

`.github/argus-env.sh`, `.github/private-alpha-release-profile.json` and
`render.yaml` are byte-identical to the previous head. `.env.example` adds only
separate analytics deletion keys, including its default-off switch. The paired
transfer flag remains false in its existing owner and deployment template.
No exchange rate, forgiveness, debt interpretation or settlement event is added.

PR #865 still shares the environment shell and release profile owner. This PR
derives API membership; #865 derives web membership. Root must serialize their
landings, compare that shared owner and rerun configuration checks on the combined
result even if there is no textual conflict.

## Verification

[Focused combined checks](reconcile-trust-contract.txt) pass 211 tests with
29 expected no-database skips, zero failures and zero pytest warnings. They cover
release and environment configuration, canonical OpenAPI, Apple name API,
account deletion API, the mocked analytics adapter and pure paired-transfer
behavior. Three explicit PostgreSQL paired cases and 26 database cases in the
paired module skip because no disposable DSN was supplied. Skips are not database
proof. No live Apple, PostHog or other provider request is made.

[Canonical mocked evals](reconcile-trust-mocked.txt) pass all 272 tests with
zero failures or skips. [Combined-tree modularity](reconcile-trust-modularity.txt)
has zero violations. Shell syntax and full PR whitespace checks pass.

Tests use Python 3.11.15 with an empty inherited environment, blank provider keys,
synthetic market data and `PYTHONPATH=web:src:.`. Commands are
`python -m pytest --no-cov -q --tb=short`, with exact module names in each log.
The mocked modules are the canonical command in `tests/evals/README.md`.
OpenAPI uses `python scripts/generate_openapi_artifact.py`; modularity uses
`python scripts/check_modularity_budget.py`; shell syntax uses
`bash -n .github/argus-env.sh`.

The prior 232-test affected PostgreSQL run with zero skips and 57 pool warnings,
plus the explicit three-case PostgreSQL run with zero skips, are retained because
the financial owners, fixtures and paired runtime configuration are unchanged.
[Earlier reconciliation](reconciliation-primary-currency.md) records the exact
retention comparison and prior profile, canary and observer context checks.
This run uses no PostgreSQL lease, simulator, Mac setting, root environment file,
hosted configuration, customer record or paid provider call.

Independent final context review, exact-head CI and guarded integration merge
remain with root. Native paired entry, phone acceptance and hosted activation
remain open. The worker's test processes exited. No persistent service was
started. Branch writes stop after the evidence commit, push and PR body update.
