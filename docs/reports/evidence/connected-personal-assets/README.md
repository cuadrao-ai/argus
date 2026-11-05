# Connected personal assets local demonstration

Property, vehicle and other assets connect to the existing Accounts, Home and
Search screens through real local Auth, API and Postgres. Whole estimates,
personal ownership, dated basis, correction history and existing debt records
remain explicit. This is local simulator delivery; physical-iPhone use over the
internet remains pending.

[PR #759](https://github.com/lagarcess/argus/pull/759) targets
`codex/private-alpha-next`. Original and current integration are
`9d6ed94491be9d904da881901a6d7a2dc8cf635b`; no reconciliation merge or semantic
overlap exists. The source/evidence/review SHAs are in [verification.json](verification.json).
The PR terminal audit records the final publication SHA and CI/review state.

## Click through

[Open the retained native simulator](http://localhost:59213). Select **Argus
Foundation Compact** if needed. The separate `local.argus.assets-demo` app is
signed in to its synthetic native owner and uses direct API59300.

1. Open **Search**, enter `Updated home 5F291`, choose **Accounts**, and open
   that property. Its latest whole estimate is DOP 9,000,000, its ownership is
   25%, and its personal contribution is DOP 2,250,000. Date and basis remain
   visible; the asset is not spendable cash.
2. **Open related debt** opens the original DOP 1,000,000 loan. Return to the
   property, then close its detail to return to the same Search query, filter
   and position. Linking does not add a liability.
3. **Estimate history** retains the original DOP 8,000,000 estimate, its
   correction to DOP 8,100,000, and the later DOP 9,000,000 estimate. Correcting
   the older entry does not replace the later estimate.
4. **Update estimate** previews the whole value and personal contribution.
   **Ownership and related debt** edits the share or existing debt reference.
   **Edit details**, **Archive account** and **Restore account** reuse the
   existing lifecycle. Archiving preserves financial totals and history.
5. In Accounts, **Add account → Other assets** creates property, vehicle or
   other asset. Leave value blank for unknown, or enter `0` for known zero.
   Choose all, half or a custom share. Close/reopen to inspect the saved state.

Synthetic native proof records accumulate intentionally; Home includes all of
that owner's retained records. The isolated API owner has a separate named scene:
DOP net worth 4,201,000, cash 1,000 and debt 900,000; USD known subtotal 500 with
an unknown loan. API proof independently checks these expected amounts and
unchanged budget, savings and selected-cash forecast values.

[60-second recording](asset-journey.mp4) shows recovery of an accepted create
response after reopening, the one recovered vehicle, and its original estimate
controls. [Native proof](native-proof.json) links successful lifecycle, Search,
Spanish/relaunch and recovery captures. [Independent review](independent-review.md)
records the fresh full review and only affected fixes afterward.

## Retained environment and restart

Demo checkout:
`/Users/garces/.codex/worktrees/connected-personal-assets-demo/private-alpha-next`.
Delivery branch: `codex/connected-personal-assets` in
`/Users/garces/.codex/worktrees/connected-personal-assets/private-alpha-next`.
The demo checkout is detached at the delivered source; preserve its private
configuration and journals. The PR records its final SHA.

Retained local Supabase/Auth59201 and Postgres59202 back both separate synthetic
asset owners. Existing debt API59200, bridge59205 and bundle remain available.
Assets use API59300, CAPTCHA59305, reused mirror59213, simulator
`1A90F684-345F-465C-AA50-6A5298F34156` and bundle `local.argus.assets-demo`.
The single reusable asset cache is `/private/tmp/argus-personal-assets-build`.
Cuadrao, physical-phone services and ports 58700–58749 remain untouched.

Skip any running service. If local Supabase is stopped, start its existing
allocation from the retained debt checkout; never configure, seed, reset or erase
it. Run long-lived commands in separate terminals.

```sh
cd /Users/garces/.codex/worktrees/connected-debt-plans/private-alpha-next
python3 ios/scripts/auth/local_stack.py start --accounts --port-base 59200
```

```sh
cd /Users/garces/.codex/worktrees/connected-personal-assets-demo/private-alpha-next
python3 ios/scripts/assets-local-runtime.py api
```

```sh
cd /Users/garces/.codex/worktrees/connected-personal-assets-demo/private-alpha-next
python3 ios/scripts/auth/bridge.py --accounts --port-base 59300
```

Boot only the retained financial simulator if shut down, then launch its installed
app. No signing or phone installation is involved.

```sh
xcrun simctl bootstatus 1A90F684-345F-465C-AA50-6A5298F34156 -b
xcrun simctl launch 1A90F684-345F-465C-AA50-6A5298F34156 local.argus.assets-demo \
  -AppleLanguages '(en)' -AppleLocale en_US -appearancePreference dark
```

To rebuild, preserve ignored `ios/Config/Local.xcconfig`, pointing directly to
API59300, Auth59201, CAPTCHA59305 and this bundle. Never install into another
bundle or simulator.

```sh
cd /Users/garces/.codex/worktrees/connected-personal-assets-demo/private-alpha-next
xcodebuild build -project ios/ArgusFoundation.xcodeproj -scheme ArgusFoundation \
  -destination 'platform=iOS Simulator,id=1A90F684-345F-465C-AA50-6A5298F34156' \
  -derivedDataPath ios/.build/DerivedData-59200 CODE_SIGNING_REQUIRED=NO
xcrun simctl install 1A90F684-345F-465C-AA50-6A5298F34156 \
  ios/.build/DerivedData-59200/Build/Products/Debug-iphonesimulator/ArgusFoundation.app
```

The mirror is already running. If absent, use its existing restart instructions
in the [debt guide](../connected-debt-plans/README.md#retained-environment-and-restart)
for this same simulator; do not create another mirror/device.
Private synthetic credentials and command journals remain in ignored
`ios/.build/accounts-local-59200/`. Never publish them. `prepare` is setup-only;
restart requires neither new users nor new records.

## API readback and interrupted writes

```sh
cd /Users/garces/.codex/worktrees/connected-personal-assets-demo/private-alpha-next
python3 ios/scripts/assets-journey.py readback
```

After deliberate human edits, use `observe` to save a separately labelled current
observation. `run` recovers an interrupted fixture using its journal's exact
request bytes/key. Never delete that journal or overwrite accepted proof.

The opt-in response-loss helper forwards a successful local mutation, then loses
only its response. Native reopening restores the pending exact command; retry
returns the saved asset once. Ordinary demonstration uses direct API59300 and
needs no proxy. For a deliberate acceptance rerun, start the owned helper on
59312 forwarding to59300, temporarily route only this demo's ignored build
configuration through59312, and use `run-ui.py --response-loss-proxy`. Restore
59300 and rebuild/install this bundle afterward. Never alter hosted settings.

## Verification and limits

- Two assembled native cases passed against real local Auth/API/Postgres:
  partial ownership, original-debt/back, older correction, share/title edit,
  archive/restore, Home, Search/query/filter return, Spanish and reopening;
  unknown/zero plus a saved create response lost before relaunch/exact retry.
- 394 financial/API/OpenAPI/real-Postgres and recovery-runner checks passed with
  no skips. This includes currencies, rounding, CAS, ownership, duplicate
  retries, canonical debt changes and focused budget/savings/debt regressions.
- Native package: 64 passed, four inherited opt-in live-auth tests skipped.
  The actual native journeys independently exercised real registered auth.
- Fresh independent review is clean through `0aabfb1605336d695fa59b636061e53995b65282`.
  One confirmed GitHub finding was fixed at the shared type-history guard;
  unknown assets retain accepted details and return `422 type_locked` instead
  of hiding history or leaking a database error. First valuation remains valid.
- Ruff, changed-document links, whitespace and would-be merged-tree modularity
  pass. Exact-head CI and the scoped follow-up review are recorded on #759.

Manual estimates are not market valuations. Initial basis may be unspecified and
is shown honestly. Share uses the existing 1–10,000 basis-point contract. A known
estimate cannot be withdrawn by omission; sale/disposal and zero-percent
ownership are outside this assigned contract. Archiving is organizational.
No automated valuation, currency conversion, sharing permission, deployment or
physical-phone delivery was added. The full MVEE remains tracked in the existing
execution manifest.
