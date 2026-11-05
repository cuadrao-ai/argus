# Connected personal savings goals demonstration

The [execution manifest](../../../specs/argus-execution-board.md#connected-personal-savings-goals-lane)
owns the assignment, approved allocation policy and delivery status. This guide
preserves the isolated local demonstration and its restart steps. It does not
claim physical-phone delivery or deployment.

## Preserve the environment

Use `/Users/garces/.codex/worktrees/connected-savings-goals/private-alpha-next`
on `codex/connected-savings-goals`. Its dedicated simulator is **Argus Connected
Savings Goals**, iPhone 17e with iOS 27, `A466756C-1478-4FA9-8604-3D9FEE15A601`.
The app bundle is `local.argus.foundation`.

This lane owns API 59100, Supabase 59101, Postgres 59102, synthetic CAPTCHA 59105,
response-loss proxy 59112 and simulator mirror 59113. Ordinary builds use the
direct API. The proxy is used only during explicit recovery verification.
Everything binds to loopback. Existing demonstrations and the phone environment
on ports 58700–58749 remain separate.

The ignored `ios/.build/accounts-local-59100/client.json` retains the two synthetic
users. Keep it and the ignored write journals private. Restart does not require
new users, tokens, configuration or database resets.

## Restart without losing records

Skip a service that is already running. Keep each long-running service in its own
terminal. Never run `configure`, `seed`, a database reset or volume deletion on
this retained scene.

```sh
cd /Users/garces/.codex/worktrees/connected-savings-goals/private-alpha-next
python3 ios/scripts/auth/local_stack.py start --accounts --port-base 59100
python3 ios/scripts/auth/local_stack.py api --accounts --port-base 59100 \
  --accounts-enabled on \
  --python /Users/garces/.codex/worktrees/5a42/private-alpha-next/.venv/bin/python
```

```sh
cd /Users/garces/.codex/worktrees/connected-savings-goals/private-alpha-next
python3 ios/scripts/auth/bridge.py --accounts --port-base 59100
```

Boot only this simulator if it is shut down, then launch its installed app.

```sh
xcrun simctl boot A466756C-1478-4FA9-8604-3D9FEE15A601
xcrun simctl launch A466756C-1478-4FA9-8604-3D9FEE15A601 local.argus.foundation \
  -AppleLanguages '(en)' -AppleLocale en_US -appearancePreference dark
```

If the mirror is absent, start it in another terminal. Cleanup targets only this
lane's simulator.

```sh
cd /Users/garces/.codex/worktrees/connected-savings-goals/private-alpha-next
GOALS_SIM=A466756C-1478-4FA9-8604-3D9FEE15A601
cleanup_goals_mirror() {
  npx --yes serve-sim@0.1.47 --kill "$GOALS_SIM" >/dev/null 2>&1 || true
}
trap cleanup_goals_mirror EXIT INT TERM HUP
cleanup_goals_mirror
npx --yes serve-sim@0.1.47 --port 59113 --host 127.0.0.1 \
  --codec mjpeg --fit "$GOALS_SIM"
```

[Open the local native simulator](http://localhost:59113). Verify the selected
device is **Argus Connected Savings Goals** and a real app frame is visible.
A loaded mirror page does not prove a connected financial journey.

## Click through the connected journey

Open **Plan → Goals → Savings goal a 4fab425f**. Its recorded support is
**DOP 400 of 1,000**, with 100 planned separately and a conditional projection
of 500 by the displayed projection date. Goal B holds 10 in the same savings
account. The shared backing is 410, with no spare allocation. Home and Search
open the same detail.

Use **Assign existing savings** to inspect each account, currency and shared
claims. Allocation changes intentions only. Open an original contribution to
inspect or correct its canonical transfer, then return to the goal. Edit the
target/date or planned transfer through **Edit goal**. Archive and restore retain
identity and claims; **Stop counting** explicitly releases attribution.

Search **Savings goal a 4fab425f**, choose **Goals**, open detail and return. The
query, filter and surviving result position remain. Close and reopen the app;
registered identity, detail and financial data persist.

The **Emergency 82C9D** fixture retains the complete native manual journey.
Existing savings 600, a transfer 200, then correction to 150 produce 750.
Release and relink retain 750 without a second transfer. Its edited target is
2,500. Other native fixtures are retained, so whole-owner Home cash differs from
the initial API scene; each goal's account pool remains explicit.

## Verification and durable evidence

[API proof](goal-api-proof.json) uses independent literal amounts through real
local Auth/API/Postgres. It covers included credit 600, corrections 550/650,
new linked contribution 750 then 730, shared shortage 600, explicit resolution,
archive/withdraw/restore shortage 20 and the retained 400/10 allocation. It also
proves currencies, unknown balances, stale writes, owner isolation, exact retries,
linked recurrence and no new spending or combined-cash movement. [SQL proof](goal-database-proof.json)
scopes uniqueness to the retained two goals, four canonical transfers, two claims
and one receipt for the response-lost create, allowing unrelated native fixtures.

[Native proof](native-proof.json) records simulator tests and matching source
heads. The complete native create/allocation/record/correct/link/edit/lifecycle,
Search/back/relaunch and Spanish journey passed. Separate recovery tests lose an
accepted goal-create or transfer response, relaunch and retry the exact command.
The contribution's source 800, destination 1,200 and one contribution confirm no
duplicate transfer. [Short recording](goal-journey.mp4) shows that real accepted
transfer response-loss/relaunch/retry journey. Authentication frames are omitted;
the clip is edited for duration, not a continuous timing benchmark.

Financial screenshots preserve [existing allocation](goal-existing-allocation-backed.png),
[one contribution](goal-recorded-contribution-once.png), [original correction](goal-original-correction-propagated.png),
[release/relink](goal-released-original-relinked-once.png), [target/date edit](goal-target-date-edited.png),
[reopened detail](goal-detail-restored-after-relaunch.png), [Search return](goal-search-origin-restored.png),
[Spanish detail](goal-spanish-detail.png), [exact create recovery](goal-exact-command-recovered-once.png)
and [one recovered transfer](goal-transfer-recovered-once-after-relaunch.png).
The [native shared-shortfall proof](native-shortfall-proof.json) and
[Needs review screenshot](goal-shared-shortfall.png) show 20 unavailable backing
without invented priority; restoring the original corrected withdrawal restores
400/10 support. [Home entry](goal-home-recorded-progress.png) opens the same
actual 400/planned 100 detail.

310 assembled financial/API/OpenAPI/Postgres checks passed with zero skips,
plus 14 independent journal/launcher checks and the inherited 19 fault-proxy checks.
The Swift package passed 55 tests with 4 inherited opt-in live-auth skips.
[Independent review](review-proof.json) records one full fresh-context review and
only affected fixes. Its confirmed null-lifecycle defect is fixed and regression
covered. [PR #755](https://github.com/lagarcess/argus/pull/755) owns final checks/head,
the terminal readiness audit and evidence retention. It remains open for
founder merge approval.

To verify the retained API scene without changing money:

```sh
cd /Users/garces/.codex/worktrees/connected-savings-goals/private-alpha-next
python3 ios/scripts/goals-journey.py readback
```

After intentional interactive edits use `readback --observe`, which labels the
changed scene rather than asserting the original amounts. `run --response-loss`
resumes the private exact-write journal; a completed run performs only readback.
Raw UI logs, credentials, journals, videos with auth frames and `.xcresult`
diagnostics stay ignored and private.

## Concrete limitations

Delivery here is a personal native simulator journey against synthetic local
registered users. Physical-iPhone installation, existing founder identity over
the internet, signing and deployment remain with their separate authorized lane.
This feature does not complete the full MVEE.

Backing uses cash/checking/savings accounts and whole eligible same-currency
transfers. Direct income can be assigned as existing money. Contributions cannot
be split among goals. Linked contribution release does not reopen a fulfilled
planned movement. Corrections of source/destination/currency require explicit
review; Argus does not silently retarget allocations. No conversion, investment
valuation, household permissions or global transaction deletion is added.

The inherited full-owner financial snapshot remains the scaling limit. Search
and original-entry navigation retain surviving anchors; removed rows cannot
retain a nonexistent position. A transient Xcode invalid-frame diagnostic
occurred during the full native
journey; no visible failure occurred in the inspected goal frames. The existing
manifest retains that visual-polish observation. No new ledger, saved counter or
hidden allocation priority exists. Financial hosted exposure remains default-off.
