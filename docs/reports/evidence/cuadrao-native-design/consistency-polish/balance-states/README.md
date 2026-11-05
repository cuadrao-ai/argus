# Cuadrao consistency polish acceptance

UI-only source: `629b8d070b2543d06198af11cedaa27cf0eaae9a`. October 2, 2026.
Previous published checkpoint: `5ae634279e358a6bd130b12f59c6a067f77c2c25`.

## Delivered

- Expanded Balance explains dated opening/closing values and account contributions.
  The line and stacked views derive from one period projection. Positive asset
  composition and deductions retain distinct meanings.
- First-use, empty-month and unavailable-history states use shared faded chart
  silhouettes and existing Cuadrao art. The first-expense action opens recording.
  Recorded zero and missing observations stay distinct.
- Temporary loading is a gallery specimen, not a fabricated live operation. System
  Reduce Motion is respected; the gallery can also preview the static variant.
- Plan uses “Lo que viene” / “What’s ahead” and the existing creation action.
- Display and editable money share typography roles. The native design guide now
  consolidates approved rules, with future work retained in the main roadmap.

## Verification

76 deterministic Home balance/coverage/projection checks passed. Modularity checks
and diff whitespace checks passed. This is branch-local preview acceptance, not an
integration READY or connected financial-history release claim.

At final source, eight native journeys passed with zero failures:

- Empty/loading/unavailable gallery, dark English, large text and reduced-motion preview.
- Reference gallery, light Spanish, shared money editing and cursor behavior.
- Spanish group journey, split and repayment flows.
- English dark group creation and shared savings.
- Balance breakdown, account navigation and return context.
- Balance breakdown with large English text.
- Interactive paging, cancelled drag and balance meaning.
- Plan forecast and goal playgrounds.

Result bundle: `test_sim_2026-10-02T05-14-03-056Z_pid473_8543eaa7.xcresult`.
Six earlier native journeys also passed at `1ad98e1c0`, including Spanish surface
headings, first balance observation, first expense, empty month and unavailable
history. Result: `test_sim_2026-10-02T05-08-34-416Z_pid473_815708d4.xcresult`.
The first-use/month screenshots here are retained from that source: subsequent
changes only add gallery specimens, align large-text balance rows, preserve nil
account participation in historical snapshots, and scope gallery motion control.
Their fixture/state paths are unchanged. Other screenshots were captured at final
source. Final delivery adds documentation/evidence only.

Review reproduced and fixed historical snapshots resurrecting an account whose
current balance was cleared. Regression checks pass. The final review of
`7ae6f23f9..629b8d070` returned clean; no outstanding blockers.

## Phone delivery

Signed build **3411** succeeded, was installed, verified by device app metadata, and
launched on the founder’s iPhone. Bundle: `local.cuadrao.design.47R3855RTJ`.
Existing phone preview state was preserved.

## Screenshots

- [Balance breakdown, Spanish](balance-change-breakdown-es.png)
- [Balance rows, large English](balance-change-dark-large-en.png)
- [Plan heading and existing art](plan-overview-es.png)
- [Empty month](story-empty-month-es.png)
- [First use](activity-first-use-es.png)
- [First balance observation](balance-first-observation-es.png)
- [First expense recorded](activity-first-expense-es.png)
- [Gallery, light Spanish](gallery-light-es.png)
- [Shared money, dark English](gallery-money-dark-en.png)
- [Empty gallery specimen](gallery-empty-dark-large-en.png)
- [Unavailable gallery specimen](gallery-unavailable-dark-large-en.png)
- [Loading gallery specimen](gallery-loading-dark-large-en.png)
