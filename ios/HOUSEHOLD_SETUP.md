# Connected Household

The Connected Cuadrao shell mounts Household Home, account details and Search
beside Personal. `CUADRAO_HOUSEHOLDS_ENABLED` stays server-default-off. The native
client uses the canonical `/api/v1/households` and `/household-invitations` API;
it has no membership store or money calculation. Accounts remain on Home.
Household controls appear only after server discovery succeeds. The typed
`households_unavailable` response hides the surface and dismisses its sheets,
while preserving actor-scoped selection and exact pending recovery bytes.
Foreground/authentication re-probes can restore the surface; writes resume only
through explicit Retry. Network discovery failures expose a scoped retry on
Personal; genuine membership loss clears selection.

Create/open and recipient preview/defer/accept are separate from People and
explicit account consent. Acceptance grants membership only. Owners choose
current members and view-only access; activity editing is an explicit switch.
People also exposes invite revocation, member removal, transfer and close/leave.
The landed account-sharing demonstration retains its supported-scope notice.
The shared-planning worker adds connected Plan below; Household Argus remains
outside this assignment.

The existing device-only write journal is partitioned by actor and Household
namespace. It stores exact command bytes and the original membership/version.
Retry survives relaunch and uses the same key. Invitation creation replay has
metadata but no recovered capability; revoke and replace that invitation.
Selection and authorization changes invalidate protected reads and editor state.
Departure returns to Personal without deleting legitimate financial records.

## Shared planning worker: separate retained demonstration

Run from the assigned worker
`/Users/garces/.codex/worktrees/shared-household-planning/private-alpha-next`.
Its new disposable allocation is `ios-accounts-59750`: API59750, Auth59751,
Postgres on port 59752 and CAPTCHA59755. Its three synthetic users, prepared Household
and seven personal accounts are retained in ignored 0600 files under
`ios/.build/accounts-local-59750`. The other Household/financial demos and the
phone stack are separate. Never run configure, seed, reset or migrations against
those environments. This lane's schema was applied only to its NEW database.

If this assigned stack is stopped, restart its retained data:

```bash
python3 ios/scripts/auth/local_stack.py start --accounts --port-base 59750
```

In separate terminals, start the following only if their assigned ports are
free. If a port is occupied, verify its process and working directory first;
do not kill another environment or start a second listener.

```bash
python3 ios/scripts/auth/local_stack.py api --accounts --port-base 59750 \
  --accounts-enabled on --households-enabled on \
  --python /Users/garces/.codex/worktrees/5a42/private-alpha-next/.venv/bin/python
python3 ios/scripts/auth/bridge.py --accounts --port-base 59750
```

The assigned simulator is `C93072E7-D29A-4B0A-BE76-E6418E4E9F88`. Shared Plan
uses only bundle `local.argus.shared-household-planning-demo` and cache
`/private/tmp/argus-shared-household-planning-native-build`; its older
`local.argus.household-current-demo` installation/cache remain preserved.
Do not select the booted design simulator by default. Its UUID `8AFB6084…`
and `/private/tmp/cuadrao-native-design-build` are protected.

For manual use, launch only the assigned installation:

```bash
xcrun simctl launch C93072E7-D29A-4B0A-BE76-E6418E4E9F88 \
  local.argus.shared-household-planning-demo
```

The installed demo retains user A. Use **Household**, choose **Shared plans 0e957ed2**, then **Plan**. Open **Native household budget C6E10C**, bill, goal or debt. The budget shows 40 actual against 100 limit and 70/30 intentions; the bill shows 60 agreed/20 paid, goal 20 backed and debt 20 paid. Switch to Home or Search, inspect your original entry, correct it, and return with refreshed progress. To check view-only behavior, sign out and use retained member B from the private fixture.

Use the saved registered user, choose **Household**, then **Plan**. Create a
shared plan with the plus control; People shows the explicit rights and unequal
responsibilities. Record or link a contribution, then open its original entry
to inspect or correct it. Home and Household Search use those same records.
The two retained member logins and unauthorized third synthetic identity are
in the ignored 0600 `client.json`; do not publish or copy that file into evidence.

Do not rerun `shared-plans-journey.py prepare` after contributions change the
balances. Preparation intentionally rejects changed data rather than resetting
it. Keep the retained journal, accounts, activity and prior native plans. An
active budget with identical accounts/categories/currency/month is a real
duplicate-scope conflict; edit it or choose another scope instead of creating a
second copy. Archive preserves its activity and history.

The reproducible native runner selects the safe retained fixture and refuses
other devices, ports or bundles:

```bash
python3 ios/scripts/auth/run-ui.py C93072E7-D29A-4B0A-BE76-E6418E4E9F88 \
  --accounts --port-base 59750 --shared-plan-scene \
  --only ArgusFoundationUITests/FinancialLoopUITests/testSharedPlanningFourKindsPrivateContributionsCorrectionsAndReopen
```

The retained C6E10C journey already passed. That case creates new synthetic plans and records real local activity; an identical active budget scope correctly conflicts. For a repeat, first archive the existing budget through its own UI/API, preserving activity, or use another scope. Do not blindly rerun it or reset data. Keep
its records; never reset the demo to make a retry appear green. The separate
three-identity case checks current Auth identity, personal-account isolation,
Household selection and Spanish relaunch. The opted-in response-loss case uses
only a temporary helper59762 forwarding to59750, then restores the app's direct
API configuration; it verifies an upstream commit, relaunch and explicit exact
retry. Temporary credential-bearing xctestrun files are removed by the runner.
No fixture credentials, invitation capabilities or full result bundles belong
in committed evidence. The execution manifest owns the actual acceptance status.

For manual use, open the new shared-planning app, choose the prepared Household,
then Plan. Create or open a budget, bill, goal or debt commitment. People shows
named view/edit rights and unequal planned amounts; Record/Link discloses only
the contribution amount, currency, date, person and status. Original opens only
your authorized activity. A view-only participant may correct their own
contribution without editing the plan or another person's activity. Goal planned
contributions stay separate from supported actual savings. Scheduled edits show
their server-provided apply-from date and preserve existing recorded payments.
Departure explains that the owner's shared plans become archived/read-only,
retain previously shared history and stop future projections. Personal funding
accounts remain private unless separately shared.

## Assigned local runtime

Run from `/Users/garces/.codex/worktrees/connected-household-native/private-alpha-next`.
Reuse the existing `ios-accounts-59500` allocation and its ignored client fixture;
do not configure, start, seed or reset another stack. The runtime owner starts
this API after releasing only its own existing 59520 process:

```bash
python3 ios/scripts/auth/local_stack.py api --accounts --port-base 59500 \
  --api-port 59520 --accounts-enabled on --households-enabled on \
  --python /Users/garces/.codex/worktrees/5a42/private-alpha-next/.venv/bin/python
```

The helper verifies Auth `http://127.0.0.1:59501` and PostgreSQL 59502 from the
allocation before launching API 59520 on loopback. The optional API port changes
neither stack identity nor Auth/database ports. Household exposure defaults off
and requires the isolated accounts allocation plus accounts exposure. It rejects
ports outside 58400–59900, the phone range 58700–58749, and this stack's reserved
ports. Root `.env` refusal and provider credential sanitization remain enforced.

Reuse the existing CAPTCHA bridge at
`http://127.0.0.1:59505/captcha.html`. Its reproducible command, when the runtime
owner needs to start that assigned bridge, is:

```bash
python3 ios/scripts/auth/bridge.py --accounts --port-base 59500
```

`ios/Config/Local.xcconfig` and the 0600 ignored
`ios/.build/accounts-local-59500/client.json` must already point to API 59520 and
Auth 59501. The CAPTCHA URL stays 59505. Config contains only public endpoints and
public client configuration; the secure runner reads synthetic credentials from
the ignored fixture. Preserve the frozen API 59500 installation.

## Pinned native runner

The assigned native profile is `argus-household-current`: simulator
`C93072E7-D29A-4B0A-BE76-E6418E4E9F88`, bundle
`local.argus.household-current-demo`, and cache
`/private/tmp/argus-household-current-build`. This recipe uses the existing runner
with two bounded in-memory overrides. It changes no tracked runner or project
file, keeps the derived `.uitests` bundle distinct, and leaves credential
injection/cleanup in the existing runner:

```bash
python3 - <<'PY_RUN'
from pathlib import Path
import sys

script = Path("ios/scripts/auth/run-ui.py").resolve()
sys.path.insert(0, str(script.parent))
sys.argv = [
    str(script), "C93072E7-D29A-4B0A-BE76-E6418E4E9F88",
    "--accounts", "--port-base", "59500", "--api-port", "59520",
    "--only", "ArgusFoundationUITests/FinancialLoopUITests/"
    "testHouseholdTwoUsersConsentEditingRevocationAndSpanishRelaunch",
]
source = script.read_text()
overrides = {
    "DERIVED = DERIVED.with_name(DERIVED.name + allocation.suffix)":
        'DERIVED = Path("/private/tmp/argus-household-current-build")',
    '"CODE_SIGNING_REQUIRED=NO",':
        '"CODE_SIGNING_REQUIRED=NO", '
        '"ARGUS_LOCAL_BUNDLE_IDENTIFIER=local.argus.household-current-demo",',
}
for original, replacement in overrides.items():
    assert source.count(original) == 1, "Runner changed; review the override"
    source = source.replace(original, replacement)
exec(compile(source, str(script), "exec"),
     {"__name__": "__main__", "__file__": str(script)})
PY_RUN
```

For the separately opted-in recovery case, the runtime owner temporarily sets
only this bundle's API URL to 59532, runs the assigned 59532→59520 response-loss
proxy, chooses the recovery test below, and adds `--response-loss-proxy` to
`sys.argv`. Keep `--api-port 59520` so the runner derives the fault control URL
59532 and validates the direct fixture. Restore this bundle's API URL 59520
afterward. The runner deletes its temporary 0600 credential-bearing xctestrun
file and CAPTCHA mode override in `finally`; ordinary results stay ignored.

## Verification entry points

- `ios/FinancialModelTests/run_household.py`: actual presentation model with
  controlled transport delay, scope change, sign-out, asset decoding and retry.
  Set `ARGUS_HOUSEHOLD_MODEL_SCRATCH_PATH` to the assigned isolated cache.
- `FinancialLoopUITests/testHouseholdDefaultOffKeepsPersonalHomeAccountsAndSearchAfterReopen`:
  opt-in normal sign-in and English/Spanish reopen against the runtime owner's
  verified off API. Assert Personal Home/accounts/Search remain reachable and
  Household selector/add/People/editors/access-ended notice remain absent.
- `FinancialLoopUITests/testHouseholdTwoUsersConsentEditingRevocationAndSpanishRelaunch`:
  create, defer/accept, explicit view access, relaunch, edit permission, expense
  25 then correction20 (1000→975→980), actual Search hit/back context, Spanish
  relaunch, owner withdrawal and recipient absence. It creates its own fixture.
- `FinancialLoopUITests/testHouseholdConfirmedResponseLossCreateAndAcceptRecoverAfterRelaunch`:
  opt-in confirmed upstream success followed by response loss, saved journal,
  relaunch, exact retry and one original Household/membership outcome.
- `FinancialLoopUITests/testHouseholdResumeEditingSearchAndWithdrawalOnPreservedFixture`:
  optional continuation on the same actual fixture, using public fixture UUIDs.

Use the existing secure `ios/scripts/auth/run-ui.py` credential injection. Never
put credentials or invitation capabilities in committed files or screenshots.
The current lane uses API59520, Auth59501 and PostgreSQL59502. Recovery alone
uses the assigned proxy59532 with
`ARGUS_TEST_RESPONSE_LOSS_PROXY=true` and
`ARGUS_TEST_FAULT_URL=http://127.0.0.1:59532/__fault`; direct API configuration
is restored afterward by the runtime owner. `--port-base 59500 --api-port 59520`
selects those endpoints in the runner.
The new bundle and cache are owned by the execution manifest; the old demo
remains separate. Tests use existing ConnectedChrome helpers and no auth bypass.

Continuation accepts `ARGUS_TEST_HOUSEHOLD_RESUME_STAMP`,
`ARGUS_TEST_HOUSEHOLD_RESUME_ID`, `ARGUS_TEST_HOUSEHOLD_RESUME_SHARED_ID`, and
`ARGUS_TEST_HOUSEHOLD_RESUME_PRIVATE_ID` through the secure runner's in-memory
xctestrun environment. It requires the assigned local fault URL as an allocation
guard; no fault needs arming for that continuation.

Stable selectors include `household.add` (opens the Spaces sheet), `spaces.choice.household`,
`household.start`, `household.intro.create/join`,
`household.selector`, `household.people`, `household.share.account.<UUID>`,
`household.share.member.<membershipUUID>`, `household.share.edit.<membershipUUID>`,
`household.account.<UUID>`, `household.correct.<activityUUID>`,
`household.search.<activityUUID>` and `household.pending.retry`. Account and
activity controls are scoped to the active `screen.home` or `screen.search`.
UI test screenshots cover safe consent/detail states and never the invitation.

Backend regression coverage lives in `tests/household/` and
`tests/financial_accounts/test_household_projection.py`. PostgreSQL cases create
and clean only their own UUID users. They cover canonical consent incarnation,
receipt races/rejoin, hidden legs/history/refund dependencies, account attribution,
unknown currency totals and original-owner RLS. The migration disposition and
exact wire are in `docs/DATA_MODEL.md` and `docs/API_CONTRACT.md`.

For default-off UI acceptance, the runtime owner uses the same allocation with
an additional API at 59620 and `--households-enabled off`, and verifies
`GET /api/v1/households` returns the typed 404. Temporarily point only the current
bundle's API URL at 59620. Select the off test above and inject
`ARGUS_TEST_HOUSEHOLD_SURFACE_OFF=true` through the secure runner's in-memory
xctestrun environment; the runner's in-memory fixture API URL may be overridden
to 59620 without changing the credential fixture. Keep Auth59501, PG59502,
CAPTCHA59505 and the assigned simulator/bundle/cache. Restore API59520 afterward.
This test performs no financial writes and requires no client capability flag.

The accepted shared-planning recording and exact-source proof are in [the durable evidence packet](../docs/reports/evidence/shared-household-planning/native-provenance.json) and [short recording](../docs/reports/evidence/shared-household-planning/shared-plan-demo.mp4). The existing execution manifest remains the sole progress/remaining-work map.
