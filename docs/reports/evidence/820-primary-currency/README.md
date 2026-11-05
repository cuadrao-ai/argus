# Primary currency transport and selection

Original integration base is `875de09ac`. This slice owns the existing profile currency setting and native transport. Home ordering, charts, onboarding and paired transfers remain separate #820 work.

The canonical persisted preference is `profiles.currency_override`. The API's `User.currency` resolves it or the declared country currency. Native transports both fields through the existing session owner. A missing legacy field stays unknown; the UI asks the person to choose. It does not infer a country or default currency.

Two designs were considered. A separate native preference/cache would duplicate server truth and require synchronization. The chosen design uses the existing profile PATCH, reads back `/me`, and restores the same server truth on relaunch. No schema, API shape or financial conversion changed.

The connected Profile lets a registered person choose their primary currency. English and Spanish explain that selection does not convert or combine balances. The write contains only `currency_override`. An unavailable or refused write leaves the existing profile visible with the existing bounded error handling.

## Concurrent preference safety

Issue #848 tracks the reproduced partial-profile race. The baseline route reads a profile then writes the whole stale row. A concurrent display-name edit can be lost. The fix validates against the current complete profile but writes only explicit validated fields and the update timestamp. The gateway updates an existing row and returns the authoritative persisted row. Existing identity/profile creation still owns inserts.

A real local Auth/API/PostgREST/Postgres regression inserts a display-name edit between read and write. It fails on unchanged baseline source and passes on this slice. It also proves declared DOP resolution, USD selection, independent readback, invalid-code refusal, and unauthenticated refusal with no profile changes. Synthetic users are deleted after the test.

## Verification

- Focused profile and currency tests passed 31 tests, with 2 chat cases deselected and no skips.
- Real local Auth/API/PostgREST/Postgres passed 1 test with no skips.
- Native session tests passed 23 tests with no failures or skips. They cover exact PATCH payload, server resolution, relaunch, refusal, legacy missing fields, and signed-out requests without dispatch.
- Native simulator build-for-testing succeeded. The final-source connected Profile journey passed 1 English test and 1 Spanish test, with no failures or skips. Both save USD, terminate, restore the server value, and sign out. Captures in this folder show saved and restored values on the run-owned iPhone17Pro simulator, iOS27.0.
- Four directly affected legacy profile tests currently error during setup in the existing SciPy environment. All four setup errors reproduce on the unchanged baseline; issue #852 covers them. Their mocks now model sparse updates and disable memory fallback.
- Full home-country suite is not green. It passed 31 tests and failed 2 chat tests. Both failures reproduce on unchanged integration because the existing arm64 Python3.10 SciPy `_spropack` binary cannot load. Issue #852 owns environment follow-up. No chat or shared runtime repair belongs in this slice.
- The first connected simulator attempt failed at login because the isolated API inherited unsuitable mock/access settings. The local configuration was corrected before the next attempt. No hosted setting changed. The initial Spanish test also failed before login because its existing paste helper recognized only English. The helper now accepts the supported English and Spanish system labels; both final-source journeys pass.

## Remaining gates

Physical iPhone acceptance and hosted API/profile availability remain open. No hosted data, credentials, migrations, flags or provider calls were changed. This slice does not claim all #820 scope is implemented or verified.

## CI fixture repair, October 5

The first profile PATCH failed in CI because this test bound the Supabase gateway
but omitted the database URL used by real session verification. The focused
repair and its separate passing and failing checks are recorded in
[ci-profile-fixture.md](ci-profile-fixture.md). Final Linux CI and independent
review remain with the release coordinator.
