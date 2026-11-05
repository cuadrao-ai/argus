# PR 849 reconciliation after primary currency

This October 5, 2026 record extends [the preceding reconciliation](reconciliation-d08.md). It records verification input for independent review and CI.

- Original integration base is `875de09ac2115acec42e09060b92878aa5f18eff`.
- Previous published PR head is `8221da20dd74a9d9925c29bd0a41ba55b605b723`.
- Fetched integration is `2b2d0d9e8ed311c11b7585fbd757fb37f915e12f`.
- The normal reconciliation merge is `82509307b2a1094d37f7bdd22929388820a49493`.
- This evidence commit changes no implementation. The final published head is recorded in the handoff.

PR 853 adds a Profile currency menu, a ProfileAuthModel action, an authenticated SessionController PATCH and profile reread, optional profile currency fields, and focused tests. Inspection of those native changes found no new required-reason API call. All 35 inventory rows still match their path, line, and source string. The complete recorded UserDefaults, AppStorage, and systemUptime match set is unchanged.

A broader comparative scan of the entire `ios` tree found no change in matches for UserDefaults, AppStorage, systemUptime, mach absolute or continuous time, creation or modification dates, file modification dates, available-volume capacity, file-system attributes, or active input modes. This comparative scan supplements the earlier source audit. It does not assert a new complete platform API audit.

The app manifest, project resource inclusion, package declarations, both resolved package files, and build configurations are unchanged. All 12 manifests in the retained unsigned Release app match their recorded SHA256 values. Its app manifest bytes equal current source. Seven validators pass with zero failures and zero skips. The combined tree's modularity budget has zero violations. `git diff --check` passes.

The retained app is explicitly a baseline packaging artifact. It proves the unchanged manifest was packaged through the unchanged resource mechanism. It does not prove the newly landed currency code builds or works. That behavior belongs to PR 853's evidence. No fresh whole-app build or simulator run occurred. Signed archive privacy verification, App Store answers, legal approval, provider proof, and phone acceptance remain open.

Prove It Works shaped this decision through direct source and packaged-byte comparisons. No database lease, Mac build slot, provider call, hosted operation, or feature activation was used.
