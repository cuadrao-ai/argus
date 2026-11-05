# Connect the approved Cuadrao interface

**October 5 correction:** the completion statement below covered the narrow money
slice. The founder rejected it as full interface restoration after reviewing Check
3431. The subsequent full recovery is tracked in [full-recovery](full-recovery/README.md).
Keep this earlier evidence as the record of what was actually checked at that time.

Cuadrao's connected money flow now uses the approved Preview presentation for
Home, account details, movement details, and Plan. Preview and live data read the
same view bodies. AccountsModel, FinancialLoopModel, and FinancialPlanModel still
own live records, commands, and recovery.

This completes the assigned UI connection in source and local verification.
Physical-phone acceptance remains pending. Neither installed phone app changed.
This record does not close the wider connected-screens issue #824 or claim that
Chat, Profile, Search, Household, or the App Store release is complete.

## Source and reconciliation

| Checkpoint | Revision |
| --- | --- |
| Original integration base | `875de09ac2115acec42e09060b92878aa5f18eff` |
| Current integration at final reconciliation | `f5c83cd88a0af56dc8154a89c6ea4f75d9c518ce` |
| One-way integration merges | `ae78b7d02`, `195c4839a`, `550202da9` |
| Last application-source change | `eddb7da97f3c38135bf855cc1c73930154fb0713` |
| Published branch | `codex/cuadrao-connected-preview` |

The first merge brought in CI and native sign-in configuration changes. The
second brought in deletion-recovery tests and documentation. The third brought
in Apple's linked-identity capture fix and migration. None changed the financial
UI, financial read/write contracts, recurring commands, or their persistence.
The lane adds no API contract or migration of its own. The shared modularity
budget passes on the reconciled tree.

The last change adapts the balance header to accessibility text sizes. Its
standard-size layout, currency selection, and expand action were checked on the
running app. The affected Preview captures were repeated. Earlier financial
journeys remain applicable because that change touches presentation only.

## Approved appearance

The [baseline manifest](baseline/manifest.json) identifies the untouched app and
screens captured before implementation. Original images were not replaced.
[Initial comparison](preview-parity.json) records six byte-identical captures.
Plan light changed 31 pixels by at most one color level at the glass edge. A
replay using the original app binary matched the candidate byte for byte.

The [final Home comparison](final-preview/manifest.json) covers the selector
extraction and accessibility fix. All three final Home captures are byte-identical to the original baselines. Account, activity, and Plan presentation
source did not change after its accepted comparison.

Run `python3 compare-preview.py` from this directory with Pillow and NumPy
available to recompute image differences. This reports differences without
rewriting either baseline or candidate images.

[Connected screenshots](connected/manifest.json) identify the source and method
for each image. They cover actual local accounts, balance breakdown, Upcoming,
recurrence review, payment recovery, gestures, Spanish copy, and large text.
The before images for the two presentation fixes remain in the same directory.

The API provides current balances but no balance-history series. Home uses the
approved empty-history artwork and retains the real cash, asset, and debt
breakdown. Plan's future points are never presented as past balances.

## Local verification

[Verification results](verification.json) retain the result-bundle counts and
source revisions. Thirteen focused UI runs passed, each executing one test with
no skips. Those runs cover ten distinct journeys, including two repeated on iOS
26.5 and the affected unknown-balance rerun. Two earlier driver failures are
recorded separately with their corrections.

| Journey | Evidence |
| --- | --- |
| Expense to recurring expectation, Home Upcoming, confirm paid, relaunch | Pass on iOS 27. Preparing an expectation does not move the balance. Confirmation records one payment. Home stays at 30 days when Plan changes to 60 days. |
| Home movement to detail, linked account, and back | Pass on iOS 27. The return retains the Home position. |
| Account swipe to Add, Edit, More, Archive, and Restore | Pass on iOS 27 and 26.5. |
| Movement swipe to Edit and Category | Pass on iOS 27 and 26.5. Existing correction review and reason remain. |
| Plan overview and list return after close and relaunch | Pass on iOS 27. |
| Spanish recurring setup | Pass on iOS 27. |
| Lost recurring-save response, relaunch, and retry | Pass. One expected payment is saved. |
| Lost payment response, another user, then owner retry | Pass. The second user sees no pending command. The owner records one payment. |
| Unknown USD balance and Spanish presentation | Pass after the fix. No invented forecast or empty known-zero subtotal appears. |
| Release avatar and photo visibility | Pass in the existing DEBUG release-gate harness. |

Seven focused model tests pass. They cover account-read state, identity reset,
large exact amounts, fractional shares, signed movement legs, missing dates,
and known zero versus unknown. Native provider configuration passes eleven cases
in both Debug and Release. Effective Release settings pass both forced-off
checks even when ignored developer settings enable the providers.

Debug and Release simulator builds pass at the final application source.
Release remains a compile check, not a signed-device or store-distribution check.

The manual read-failure check injected one 503 response for financial accounts.
Home showed Retry without the first-use prompt. Retry restored the existing
accounts and removed the error. The fault proxy recorded one consumed read fault.
At Accessibility XXXL, currency and amount now occupy separate rows. Changing
DOP to USD retained the actual unknown state.

The isolated API and Postgres used synthetic accounts, ports 59850 through 59855,
and the 112 migrations present when the stack was created. The initial two-user
smoke passed fourteen checks. Provider keys were blank. The later Apple-only
migration was not exercised by these financial tests. Hosted Apple verification
belongs to its owning lane.

## Reviews and limits

[Decision and review history](decisions.md) records the architecture choice,
findings, fixes, and clean delta reviews. The final accessibility review found no
actionable issue. Branch CI is checked at the published head; a past green result
is not a standing release approval.

Xcode reports an invalid-frame warning while the account nickname keyboard opens
in the financial journeys on both simulators. Those journeys pass. Its runtime
cause is not established here. Release also reports the existing weak-capture
warning at ConnectedCuadraoRoot.swift:27, which this lane does not modify. This
work does not claim to settle the separate lag report or all accessibility work.

No merge, deployment, hosted migration, paid call, or phone installation occurred.
Automatic approval review rejected creation of the new draft PR. The branch is
published with evidence, and PR creation awaits explicit approval. A PR was not
created through an alternative tool.
