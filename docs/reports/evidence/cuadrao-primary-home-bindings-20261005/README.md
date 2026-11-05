# C1 primary-currency Home bindings preparation

Source prepared from recovered UI dependency `56b6de7ca` on `codex/cuadrao-connected-preview`. Original captain integration base is `7d037`. The dependency must land before this lane is published for readiness. No integration reconciliation or runtime acceptance is claimed.

One pure presentation helper orders supplied currency payloads. The server-resolved `auth.profile?.currency` takes first place only when present. Other codes follow deterministic code order. The helper preserves each row and does not create currency rows, amounts, exponents, permission fields, or defaults.

The recovered personal and Household Home already show one summary with an existing currency switcher. Their default and switcher choices now use the ordered server payloads. An explicit valid local choice remains selected. Upcoming orders its existing projected summary rows. Account lists, occurrence order, horizon, layout, formatting, scope and unknown-state handling are unchanged. Connected Plan forecast selection is outside this C1 preparation.

Synthetic Swift checks cover missing preference, unavailable preference, empty inputs, primary changes, 0/2/3 fraction digits, exact large minor strings, known zero, unknown-only rows and authorized Household subsets. The tests assert that every field survives ordering. Profile JSON decoding and canonical profile readback remain owned by #853.

`git diff --check` passed. Swift compilation, test execution, simulator, Mac and device checks are pending the UI owner's lease. None was run here. Suggested isolated pure check when that lease allows it:

```sh
swiftc ios/ArgusFoundation/Currency/CurrencyPresentation.swift ios/DesignPreviewTests/CurrencyPresentationChecks.swift -o /private/tmp/cuadrao-currency-presentation-checks
/private/tmp/cuadrao-currency-presentation-checks
```

The UI owner's source worktree and its foreign four-line `ConnectedBudgetUITests.swift` modification were preserved. This checkout owns no running build or device process.
