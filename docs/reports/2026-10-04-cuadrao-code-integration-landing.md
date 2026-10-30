# Cuadrao code integration landing, October 4, 2026

This is a pre-final record for the approved mobile landing batch. The source
combines the reviewed mobile work with the latest approved product documents.
Only PRs with recorded merge SHAs have landed; the remaining rows require
current-head CI, final review-thread checks and an observed GitHub merge. This
batch does not implement the future space model or agentic runtime in #814/#815, enable a hosted feature, or establish TestFlight readiness.

## Reconciliation

The lane started at integration `e78dda7c93812ff271c9ef63cdd6a73330eee52e`.
All four worker branches originally forked from runtime baseline
`a8c37d3a182fbdb3228f6003272418e65286bc1a` or its stacked descendants.
Published branches absorbed integration through normal merges. No branch was
rebased. Shared board and decision-log conflicts retained the newer authority,
the avatar release rule and the accepted UI dispositions.

Reconciliation commits: #790 `8792abc3941f89a31d2c2dd95f8be93e5d7f5b93` and
`dc3c4dcc087d277223376003c36110190554f780`; #810
`394d2bc11be5cb09c67b6591cb4f11286dd14194`; #812
`77c64816c2d269a9210e463b95f9b77743f47ae0`. Each retained the relevant
reviewed iOS source while adopting the current integration documents.

The combined verification candidate is
`25ce9a4d1a93516b21c3d52723b95468e5cbe149`, with iOS subtree
`e2404d5e1d05d51761343cd18d7747605d884794`. That subtree matches accepted
candidate `03a33ef2be86cd86f4ad65c51d3e95a08a0e7ba8` exactly. Reconciliation
changed documentation and verification evidence; it did not change the app's
artwork, navigation, gestures, API contracts or financial behavior.

## Verification and review

Each PR received its own independent review. Current-head checks and unresolved
review threads were checked again before each merge. The compact register below
records the exact heads, bases, patch identities and CI runs.

- #809: 15 focused gate tests and a real pytest/JUnit mixed-outcome report prove
  that the gate fails and names failed tests. Its patch did not change on merge.
- #790: Debug and Release builds passed; nine Swift host runners passed; 24
  selected simulator UI tests passed with zero skips or failures. A Release
  installation ignored preview launch arguments. Two inert gallery argument
  strings remain in the binary; that is not an active preview entry point.
- #810: fresh invitation, Household and wire-contract host runners passed.
- #812: 82 Home projection checks passed. Each of nine locale processes passed
  12,157 money-format checks, including 5,984 parity pairs plus reverse-order,
  concurrent-call and literal expectations.
- The combined candidate passed ten fresh simulator journeys, with zero skips or
  failures. The [committed screenshots and results](evidence/cuadrao-code-landing-2026-10-04/combined/README.md)
  cover invitations, charts, highlights, Search and chat return. The
  [release UI record](evidence/cuadrao-code-landing-2026-10-04/pr790/README.md)
  preserves its separate 24-case run.

The earlier full candidate run (119 passed, 48 skipped, zero failures) and visual
classification remain valid evidence for their named source trees. They were not
rerun or represented as new full-suite results. Simulator fixture journeys are
not hosted service or physical-phone acceptance. No frame-hitch improvement is
claimed from test idleness alone.

## Configuration and remaining gates

`CUADRAO_BETA_INVITES_ENABLED` and `CUADRAO_INVITE_UNIVERSAL_LINK_ENABLED` are false
in the tracked development configuration and local example, and are exposed by
Info.plist to the canonical invitation flag reader. No template is missing.
Provider keys, Associated Domains/AASA, push configuration, hosted flags and
migrations remain separately authorized work. No secret values changed.

Keep #784 open for remaining device and connected acceptance, #800 for sign-in,
#805/#806 for deletion enablement, #778 for retained document sources, and #811
for the default-grants security finding. The legal and privacy pass in #781,
complete onboarding, and separately assigned Cuadrao runtime work remain open.
No issue was closed merely because these PRs landed.

The phone was unavailable. This batch did not install a new phone build. No
main promotion, deployment, hosted mutation, paid model call or flag enablement
was performed.

## Landing register

The founder authorized this bounded landing on October 4. GitHub PRs are the
merge authority; no worker branch was merged into integration by hand. The
final #812 merge SHA and exact integration CI are recorded in its landing
comment after they exist. This document is prepared before that final merge;
its publication alone does not assert that a merge or CI run has completed.

| PR | Reviewed final head | Integration base | Merge | Independent verdict | Current-head CI |
| --- | --- | --- | --- | --- | --- |
| [#809](https://github.com/lagarcess/argus/pull/809) | `503ee3c813166ab7a8b8defec4befd134a032ff0` | `e78dda7c93812ff271c9ef63cdd6a73330eee52e` | `df446b6b6cd407ffd45f07ce86fbd7cb2425f1b8` | PASS | [Passed](https://github.com/lagarcess/argus/actions/runs/37244104464) |
| [#790](https://github.com/lagarcess/argus/pull/790) | `3e9cf5c04a1bee61fcca268f94fca9e5a82f849e` | `df446b6b6cd407ffd45f07ce86fbd7cb2425f1b8` | `594729617ebad59f7dad0796eaf69405ef0480c4` | PASS+NOTES | [Passed](https://github.com/lagarcess/argus/actions/runs/37245118307) |
| [#810](https://github.com/lagarcess/argus/pull/810) | `8d8c354572dc40e943688196b7a8aff2813d9b19` | `594729617ebad59f7dad0796eaf69405ef0480c4` | `ecb0623488992337c4a3d1999618f0c9aa07aae0` | PASS; source and documentation delta clean | [Passed](https://github.com/lagarcess/argus/actions/runs/37246091205) |
| [#812](https://github.com/lagarcess/argus/pull/812) | Final head and CI recorded in the PR landing comment | `ecb0623488992337c4a3d1999618f0c9aa07aae0` | Recorded after merge in the same comment | Independent source review PASS+NOTES; documentation delta review required before merge | Must pass at final head before merge |

Full patch IDs changed where documentation or evidence was added. Reviewers
checked those deltas. App source identity was checked separately, rather than
inferring safety from a clean textual merge:

| PR | Original full patch ID | Reconciled full patch ID | Source comparison |
| --- | --- | --- | --- |
| #809 | `efbc1b39584e2dc5ce75d34bebcac542a32a76b1` | `efbc1b39584e2dc5ce75d34bebcac542a32a76b1` | Unchanged complete patch |
| #790 | `7b154263125b74d29409d24c50b524b1d298a1f8` | `174a207a86a7227f66cdb8faad42014d826fc768` | iOS tree `93c02eae19e61b8cf858b2efd2ecc2fcb81f26ea` unchanged |
| #810 | `4e507ddfd216b12a4e9f33bda9b7100f44c1c9fe` | `f4a580eeccc2a432ebbff8e189dcd0b734919dfe` | iOS patch `75c96d329a8270d8a5d428930ea40ed62fd3d572` unchanged |
| #812 | `aab45fd349f480315a1319c852504a9b5007379d` | Final patch recorded in PR landing comment | Combined iOS tree must remain `e2404d5e1d05d51761343cd18d7747605d884794` |

The independent final delta review, merged-tree modularity check, clean local
integration synchronization and exact integration CI result are recorded in
[#812](https://github.com/lagarcess/argus/pull/812) after the final head is fixed.
The [decision trail](evidence/cuadrao-code-landing-2026-10-04/decisions.tsv)
records bounded choices and their evidence. The active board's future lanes and
unchecked release requirements remain open.
