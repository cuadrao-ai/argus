# Connected Household evidence

This packet belongs to [PR #766](https://github.com/lagarcess/argus/pull/766), the
[existing execution manifest](../../../specs/argus-execution-board.md#connected-spaces-and-household-lane)
and native restart instructions (removed; see tag `archive/ios-personal-2026-10-30`).
It extends landed #763 membership and #760 connected native presentation.

## Usable native demo

The assigned simulator is **C93072E7-D29A-4B0A-BE76-E6418E4E9F88**, bundle
`local.argus.household-current-demo`, cache `/private/tmp/argus-household-current-build`.
Its mirror is <http://127.0.0.1:59513/>. The current signed-in synthetic recipient
can select **HH native 69447E**, open **HH shared 69447E**, inspect its 980 DOP
balance and 20 DOP canonical expense, then use History or Correct activity.
Personal accounts remain separate. People shows membership; administration and
owner consent require switching to the original synthetic owner with the
existing secure local fixture. Do not copy credentials or invitation links into
published evidence. No external invitations were sent.

[Short functional recording](correction-demo.mp4) captures the final native
correction preview 975→980 and refreshed Home with one 20 DOP expense.
[Current Home](home-corrected-current.jpg),
[current correction preview](correction-preview-current.jpg) and
[current opening scene](home-before-current.jpg) were captured at source
`d1084805fa1da72dba8faf6c78971c73c1e97882`. System-dark appearance keeps the
Household white canvas readable and its native sheet dark. The white canvas
was also inspected with system-light appearance.

## Default-off and recovery review follow-up

The later [P1 review](https://github.com/lagarcess/argus/pull/766#discussion_r4153356691)
identified a real error: the native app treated the server's disabled feature as
lost membership. Source `c38e4d107fd983cd95d5adf703513b913e443b0f` fixes that class
through one server-derived availability state. Controls, routes and sheets stay
hidden until discovery succeeds. Disabled responses clear protected views,
retain actor-specific selection and exact pending bytes, and return to Personal.
Foreground can restore the surface; writes still require explicit retry.
Actual scoped membership loss remains distinct from generic errors. A transient
429 preserves the journal, and denying a saved H1 command cannot clear a valid
current H2 selection.

[Scoped independent review](feature-off-review.md) is clean atc38; 14 actual
production model tests pass, alongside64 Session cases with4 opt-in Auth skips.
The real native default-off test atc38 is **PASS**, archive
`ui-20261001T141415Z.xcresult`: ordinary registered authentication, English and
Spanish relaunch, working Personal Home/Accounts/Search, and no Household
selector/add/People/pending/editor or false access-ended state.
[English Home](household-default-off-personal-home-en.png),
[Spanish Home](household-default-off-personal-home-es-419.png),
[English Search](household-default-off-personal-search-en.png) and
[Spanish Search](household-default-off-personal-search-es-419.png) are safe test
attachments. Existing Personal Search dark contrast remains recorded polish;
these images prove routing/absence, not a redesign of that inherited screen.

[Real two-user API readback](feature-off-api-proof.json) passes10 checks on
API59520 versus disabled59620, sharing existing Auth59501/Postgres59502. Every
Personal account/Home financial field is unchanged; only Home's fresh
`recorded_at` timestamp is excluded from equality. No financial writes occurred.
Ten focused Household/projection regressions also pass on actual Postgres.
After restoring this bundle's direct API59520 and rebuilding, the original
69447E selection,980 DOP balance and one20 DOP activity reappear.
[Restored Home](restored-household-home.jpg) and the
[short restored detail/history/back recording](restored-household-demo.mp4)
show current source. Original financial/lifecycle evidence below is retained;
unchanged backend/migrations/money calculations were not reopened. The final
PR audit records publication-head equality, CI, review reply and resolution.

## Assembled acceptance and truthful disposition

The full setup test at `ui-20261001T073216Z` reached household creation,
invitation preview/defer/accept, membership-only empty state, explicit default
view consent, recipient view-only detail and owner edit consent. It then hit the
unchanged local eight-logins-per-ten-minutes limit; **that full test failed**.
The same actual AAE272 fixture was continued, with no replacement data, by
`testHouseholdResumeEditingSearchAndWithdrawalOnPreservedFixture`: **PASS,
224.032 seconds**. It records25, corrects the same activity20 (1000→975→980),
opens actual Search/detail/back, reopens in Spanish, withdraws sharing as owner
and confirms recipient absence after relaunch. [Consent](view-consent.png),
[Spanish reopened detail](spanish-reopened-detail.png) and
[withdrawn account absent](withdrawn-account-absent.png) retain those states.
The withdrawal image predates the two-line contrast fix; it proves access state,
not final visual polish. Current images and recording supersede its colors.

`testHouseholdConfirmedResponseLossCreateAndAcceptRecoverAfterRelaunch`:
**PASS, 228.443 seconds**, source d108, `ui-20261001T075255Z`. The local proxy
confirmed **two dropped committed responses**, then was unarmed. Exact saved
commands recover the original household and membership after relaunch, without
duplicates. Direct API59520 was restored and the owned proxy59532 stopped.
Earlier failed runs from stale API process/canonical UUID normalization and
navigation test setup remain ignored diagnostic archives, not accepted proof.

## Real financial and authorization evidence

The separate retained API scene **Family demo43b5b12d** has Ana's bank972 DOP,
private bank8988 DOP and property whole8000 DOP with50% recorded ownership.
Bruno receives only explicit current grants. Household DOP4972 includes bank972
and property4000 once; unknown USD remains unknown. A private transfer keeps its
canonical type while the private leg and primary note are redacted.
[Retained readback](retained-demo-proof.json), [closed lifecycle](lifecycle-proof.json)
and [RLS](rls-proof.json) contain safe assertions from real Auth/API/Postgres.
Departure/rejoin/close preserve owners' balances and legitimate transactions;
authenticated direct table access cannot bypass the service authorization.

[Initial independent review](independent-review.md) records three confirmed
findings. [Affected-fix review](affected-fix-review.md) is clean at financial
source8e, helper095 and native contrastd108. [Verification record](verification-checkpoint.json)
contains exact lineage, check counts and evidence disposition. Integration
reconciliation4fed incorporates09ce landing documents only. All later packet
changes are documentation/media; the terminal PR audit records final-head CI
and confirms unchanged accepted source. No raw credentials, capabilities,
private journals, auth recordings or xcresults are published.

## Limits and preserved resources

API59520 reuses Auth59501/Postgres59502/CAPTCHA59505. Existing demos, financial
records, old API59500 and all other agents' devices/caches remain preserved.
Do not reset/seed this allocation or choose another booted simulator.
The broad local suite has an inherited SciPy `_spropack` collection failure;
focused checks and real Postgres pass; full Linux CI is the broad-suite gate.

No physical-phone/internet delivery, deployment, hosted migration/configuration,
external invite delivery, shared plans, Business/Custom lifecycle, imports,
voice/runtime or Cuadrao Profile redesign is claimed. Existing shared-shell
navigation/Personal semantic colors in dark appearance remain visual polish
in the manifest; Household content and sheet contrast are verified here.
