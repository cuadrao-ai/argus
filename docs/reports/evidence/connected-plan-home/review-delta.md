# Connected Plan/Home affected-delta review

Reviewer: the same fresh-context default Codex reviewer used for the independent pass, not GitHub Codex.
Reviewed delta: `196ccea2c2d738cf3f106515f658900d135e6585..ab1e3e63036881590bba9fa173b840fbc80774d2`.
Disposition: **clean for this affected delta; all three prior findings are resolved.**

- Expectation UUIDs normalize before lookup and idempotency scope construction. Independently confirmed uppercase native-style edit plus lowercase same-key receipt replay with the memory repository.
- Forecast movements now update per-account whole positions and derive attributed changes using the existing canonical ownership/rounding function. Independently ran all six new income/bill fractional-share and minor-unit continuity cases using only memory repositories; all passed. Unknown selected accounts stay unknown and do not manufacture a known starting subtotal.
- The native selector retains controls for saved archived/ineligible accounts, labels their status, permits removal and prevents reselecting an ineligible account after removal. This closes the previously hidden-ID trap without silently changing saved selection.
- Moving `home.comingUp` to the heading confines its accessibility identifier instead of applying it to the entire section. The related calendar-dismissal and scroll test changes do not alter product behavior.

Reviewed the accompanying contract, localization, test and review-record changes. No additional actionable comment/docstring issue. No unchanged-code expansion, repository edits, child agents, simulator, database, hosted, network or provider operations. All reproduction processes exited. Native removal acceptance and assembled simulator acceptance remain the captain's separate verification; this report does not claim they passed.
