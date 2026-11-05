# Connection decisions and review

The founder assigned this connection on October 5. Cuadrao Preview is the approved
presentation. Cuadrao Check supplies the working financial operations. Rebuilding
the interface or replacing canonical records with Preview state is outside scope.

| Decision | Reason and verification |
| --- | --- |
| Extract actual Preview view bodies. | The experience-first principle preserves the approved geometry, typography, artwork and navigation. Original screenshots were captured before edits and retained unchanged. |
| Feed shared views display values and callbacks. | The model-the-domain principle keeps AccountsModel, FinancialLoopModel and FinancialPlanModel authoritative. A whole-app snapshot or writable Preview-store adapter would duplicate record and command ownership. |
| Use the approved empty-history treatment. | The API provides current balances, dates and breakdowns but no balance-history series. Future Plan points cannot establish past coverage. |
| Keep Home's rolling window independent. | Upcoming uses homeProjection and existing explicit confirmation. The passing recurring journey changed Plan to 60 days while Home stayed at 30 days, then verified payment and relaunch. |
| Preserve the opening section in Plan navigation. | Review found that overview cards returned to the category list. An additive navigation-origin case restores either Overview or the original list, including after relaunch. No financial record schema changed. |
| Respect busy account navigation. | Review found Back could remove the route while AccountsModel declined to clear selection during a request. Back now derives availability from that same owner and removes the route only after selection clears. |
| Share the remaining space-selector body. | The cross-model audit found duplicated selector presentation. The live adapter retains HouseholdModel selection and permissions while both hosts use the same horizontal layout and labels. |
| Hide an empty known-balance subtotal. | Visual inspection found that a Plan containing only unknown balances still displayed a known subtotal of zero. The subtotal now requires at least one account with a known balance; an actual known zero is preserved. The affected journey passed again at `d50678438`. |
| Stack the balance header for accessibility text sizes. | The largest text setting wrapped the currency code. `eddb7da97` gives currency and amount separate rows at accessibility sizes. Standard-size captures still match the original content. Currency selection works on the running app. |
| Adapt test drivers to native surfaces. | The first two attempts failed before the financial assertion path. Apple's compact calendar has its own dismiss region. Native TabView does not mount offscreen Profile. The drivers now use those visible controls; monetary and persistence assertions were retained. |

## Independent review

The first source review found missing projection scope/freshness context and an
unread-account spinner. Both were corrected. The next pass found the Plan-origin
and busy-back issues above. Delta review through `ae78b7d02` found no remaining
P1/P2 findings and no semantic overlap problem from integration's sign-in/CI
follow-ups.

A separate architecture audit found no Preview-store use in connected records or
commands. Its selector observation was fixed in `0fbe310cb`. Independent delta
review of `ae78b7d02..0fbe310cb` found no actionable findings. Test-driver return
navigation in `24108a515` adds the existing Back helper before a Plan tab tap;
it changes no financial assertions or production code.

Independent review of `d50678438` found no actionable issue in the unknown-balance
fix. A fresh review of the accessibility delta in `eddb7da97` also found no
actionable issue. The parent verified the running large-text layout and repeated
standard-size screenshots afterward.

The prove-it-works principle separates source review, screenshot parity, local
API/Postgres journeys, and physical acceptance. A simulator pass does not replace
the final phone review. Neither installed phone app was changed.

## Delivery boundary

This branch contains no API contract change, migration, hosted operation, provider
call, merge, or phone installation. It reconciles integration in one direction.
The original base is `875de09ac2115acec42e09060b92878aa5f18eff`; the recorded
first integration merge is `ae78b7d02`, bringing in `a6688eea10895d9f57664f1ece8a7eba96503732`.
The overlap was native build/auth configuration only. Merge `195c4839a` then
brought in deletion-recovery tests and docs at `26c0692d`. Merge `550202da9`
brought in Apple identity binding at `f5c83cd88`. Neither later merge changed
this lane's iOS or financial contracts. No new financial acceptance was invalidated. Financial journey evidence
is tied to the application source identified in the verification record.

The forge CLI available here is gh; Origin is not installed. Branch publication
succeeded. The GitHub connector rejected draft PR creation during automatic
approval review. No PR was created, and no alternative creation path was used.
