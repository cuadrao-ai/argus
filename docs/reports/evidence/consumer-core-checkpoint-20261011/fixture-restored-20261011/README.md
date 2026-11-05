# Core verification after fixture restoration

The unchanged local CAPTCHA fixture was restored at port 59485 for the existing
Consumer simulator tests. It uses public Cloudflare test keys. The app still
uses real staging authentication and financial records. No hosted configuration,
backend code, native product source or credentials changed.

| Journey | Result | Evidence boundary |
| --- | --- | --- |
| Account archive and restore | PASS, one test, zero failures or skips | Created a DOP 125 account, archived it, restored the same ID and checked the Home total |
| Search editors and origin | FAIL, one test, zero passes or skips | Account rename and correction review ran; the returned activity-row amount assertion failed at SearchUITests.swift:41 |
| Budget full continuation | FAIL, one test, zero passes or skips | Money, correction, refund, contributor-position relaunch, limit edit and remove/restore passed before Search could not find the Budget under the retained Activity perspective |
| Legacy retained Budget Home test | FAIL, one test, zero passes or skips | Stopped at the old Home budget-row identifier before reaching Search |
| Retained Budget Search regression | PASS, one test, zero failures or skips | Began in Activity, selected Plans, retained the DOP filter and saved values through Search and Spanish relaunch |
| Search with corrected activity-row wait | FAIL, one test, zero passes or skips | The exact corrected activity row reached 27.00; the later bill-row wait began before the editor closed and timed out |
| Search with actual editor-dismissal wait | FAIL before financial checks, one test, zero passes or skips | Fresh sign-in did not reach the authenticated profile; the repaired bill assertion was not reached |

Search started at 20:41:49 UTC and finished at 20:50:06 UTC on October 11.
The MCP call timed out at five minutes, but its underlying XCTest kept running.
The terminal result above comes from the completed result bundle. No duplicate
runner or automatic retry was started.

The Search test corrected `Search income A6D085` from DOP 25.00 to DOP 27.00.
The review screenshot shows the proposed account balance of DOP 127.00. The
test then accepted the correction and passed its DOP 27.00 detail assertion.
After Back, it waited only for the row to exist and immediately checked its
label. The retained old row can exist while the asynchronous refresh runs.

At 21:14:02 UTC, a read-only call to the same staging Search endpoint returned
one matching income record at revision 2 with amount 27.00 and 2700 minor
units. This proves the saved correction and canonical Search result. It does
not establish what the native list displayed after its refresh. The sanitized
readback retains the amount, revision, kind, note and reason. The native result
used activity ID
`2542D06E-4E1D-4C63-BBC8-B900E3244000`.

The later no-write simulator check confirmed the same native activity row at
DOP +27.00. Its screenshot and exact identifier are in `manual/`. This supports
the test timing diagnosis. The later bill edit and Spanish relaunch steps did
not run in the original failed Search case.

## Retained manual checks

The manual continuation used the original unchanged Core binary after the
Budget runner finished. It did not submit financial changes.

- Search displayed activity `2542D06E-4E1D-4C63-BBC8-B900E3244000` at DOP +27.00
  for `Search income A6D085`, matching the canonical readback.
- `Food 52C2E` had no result under the retained Activity perspective. Changing
  to Plans found Budget `7E52E53C-1EE6-4C7E-B14D-F7F22FF62332`. Its detail showed
  DOP 155.00 spent and DOP 5.00 remaining against a DOP 160.00 limit. Spanish
  relaunch preserved those values. Back preserved the query and DOP filter.
- Existing Goal `Emergency F6D90`, ID `C631C990-DA4B-4B71-8241-489AC197FC50`,
  showed DOP 750.00 supported savings in Spanish and after English relaunch.
  Entering 99 in a contribution draft and cancelling kept DOP 750.00. Back
  restored the Goal query, Plans result, DOP filter and DOP 2,500.00 target.

These manual results supplement the failed XCTest bundles. They do not turn
those runs into passes or relabel the earlier complete Goal journey.

## Test repairs

The bounded test repairs are committed locally at
`f9dae47a562e0c660d5c60d67506d0903ac02fea`. The final build's recorded file hashes
match that commit. No native product file changed.

The Search assertion now retains the original row ID and waits for that row to
show 27.00 after refresh. The Budget Search helper now selects Plans through the
existing helper, which also checks that currency filters remain intact. A
retained-Budget regression begins in Activity and checks Search, relaunch and
Spanish without creating another set of accounts.

Native product source is unchanged. The legacy Home test failure remains
preserved; it is not used to prove the Search repair. The rebuilt retained
Budget regression passed in 72.8 seconds. Its terminal result is in
`budget-retained-pass-summary.json`; the final Spanish screenshot is
`budget-retained-pass-spanish.png`. `repair-build-source.json` records the exact
test-file and binary hashes.

The complete Search rerun passed the corrected activity-row assertion. Its
later bill assertion failed at `SearchUITests.swift:55`. The bill changed from
DOP 30.00 to DOP 35.00. The test treated the disappearance of Save as editor
dismissal, but the form replaces Save with a pending-state control during the
request. Retained debug descriptions show the editor still present more than
six seconds after Save disappeared. The first poll without the editor was only
about three seconds before the result wait ended. The timing receipt is
`search-bill-dismissal-diagnosis.json`.

A later manual relaunch found the exact bill row at DOP 35.00 in English and
Spanish, with the query, Plans perspective and DOP filter preserved. These
screens are in `manual/search-bill-*.jpg`. A separate direct readback attempt
stopped at synthetic authentication with HTTP 400; it performed no financial
GET and was not retried. The simulator observations remain separate from that
unsuccessful readback.

The final bounded repair waits for the editor name field to disappear using
the existing 15-second timeout, then keeps the existing 10-second amount check.
The new Release test build passed. One full Search attempt then failed at fresh
sign-in, `FinancialLoopUITests.swift:468`, before any financial step. It ran
from 22:05:06 to 22:06:19 UTC. The local CAPTCHA fixture was running. The retained terminal UI showed
“We couldn’t sign you in.” This indicates rejected authentication; it does not
establish the credential, account-policy or CAPTCHA cause. No provider error
code is present in the inspected receipt. `search-dismissal-auth-diagnosis.json`
records that boundary. The result
does not establish whether the bill repair passes. No assertion or timeout was
removed or relaxed.

`dismissal-repair-build-source.json` records the final test source hashes and
the unchanged app binary. `search-dismissal-auth-failure-summary.json` retains
the last failure. The earlier bill failure remains in
`search-repair-bill-failure-summary.json`. Independent source and comment review
found no issue with the bounded test changes. Final Search runtime acceptance
remains pending an approved, working authentication route.

At 22:07 UTC, the runner was terminal, the signed-out simulator app was stopped,
and the owned local CAPTCHA fixture was stopped normally. No Consumer run or
app session remains active against the backend. This releases the test window;
it does not authorize hosted changes or establish complete Core acceptance.

`source.json` pins the unchanged build and its limits. This is synthetic Free
account evidence, not Full access, hosted CAPTCHA, phone or complete Core
acceptance. The earlier missing-fixture failures remain in the
[initial continuation](../core-continuation-20261011/README.md).
