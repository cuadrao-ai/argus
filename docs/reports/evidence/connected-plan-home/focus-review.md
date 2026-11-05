# Account form keyboard affected-delta review

Reviewer: the same independent default Codex reviewer, not GitHub Codex.
Reviewed delta: `36abc0bc41fe0c12cb8651582e177dfd652013b0..20750992472ae3dfddb3f6f11718fa84f0ed3113`.
Disposition: **clean for this affected delta.**

The account form now binds its amount field and shared nickname/share/reason text fields to distinct values of one optional focus state. Both Done and Save clear that state, so keyboard dismissal is no longer limited to the amount field. No field retains the old amount-only focus binding. The test helper now dismisses the keyboard for unknown-balance creation as well, and the changed-account case targets the existing metadata type picker rather than the create-mode type controls.

Source inspection only. Simulator confirmation remains the captain's separate acceptance evidence. No repository edits, runtime processes, child agents, simulator, database, hosted or paid-provider operations. No additional actionable finding; review stops at this delta.
