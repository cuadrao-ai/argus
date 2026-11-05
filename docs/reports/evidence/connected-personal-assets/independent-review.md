# Independent connected personal assets review

Reviewed head: `158664979513048e64abe30a4f3972518e078c28`
Base: `9d6ed94491be9d904da881901a6d7a2dc8cf635b`
Scope: complete base-to-head diff, including financial Recording/API/Postgres, native asset journey and journal, Search return, local helpers, contracts, migration and focused tests.

**Findings: none confirmed.** The reviewed paths keep whole estimates in canonical observation revisions, apply the existing personal share once, leave unknown distinct from zero, and link existing debt by owned account ID without adding a second liability. Corrections retain observation identity and order. Asset changes use the account version and an accepted replay receipt. Native creation and asset confirmations use the owner-scoped durable journal; nested debt detail returns to the asset and preserves the Search destination.

The bounded source-comment/deslop pass found no actionable comment, workaround explanation, or correctness lint suppression in the added code. Existing FastAPI `B008` and pytest fixture `F811` suppressions are style/tool-convention scoped.

This is a static independent review. It does not claim live API, Postgres, simulator, or device acceptance; the captain owns that evidence. No repository files, processes, services, or simulators were changed or started.

At final status check, the shared checkout had advanced to `f83232cf5ad8e212d01f4a66ee49cffced761569`. This report is scoped to `158664979513048e64abe30a4f3972518e078c28`; it does not cover the later commit.

## Affected-delta review

Reviewed delta: `158664979513048e64abe30a4f3972518e078c28..173c62200a88870f0300a5ae06528ac0fe4f8278`
Exact reviewed head: `173c62200a88870f0300a5ae06528ac0fe4f8278`

**Findings: none confirmed.** I reviewed only the six changed files. The local API journey now selects the known DOP cash account before asserting its forecast, compares savings pools by financial facts while allowing expected version/date changes, and verifies canonical Search readback and owner isolation. The native test seeds known cash before its net-worth delta assertion. The SwiftUI edits move accessibility IDs from `DisclosureGroup` ancestors to their visible labels. The response-loss proxy adds account writes only after a successful upstream response, excluding reads, previews, failed writes and unrelated paths; the added tests cover those cases and actual proxy delivery loss. `git diff --check` passed.

The captain reported the live API journey green at this head. I did not run it or the native journey, and this review makes no native success claim. I made no repository edits and started no processes or simulators.

## Unknown-asset type guard and native locator delta

Reviewed delta: `173c62200a88870f0300a5ae06528ac0fe4f8278..9d49cde3359a54d8d28624e5f16973d032bbd61b`
Exact reviewed head: `9d49cde3359a54d8d28624e5f16973d032bbd61b`

**Findings: none confirmed.** The guard now treats accepted asset-details changes as retained provenance even when the asset has no estimate and its debt link is null. The memory edit path reads the same stored change tuple; Postgres hydrates it while holding the owner metadata lock shared with details writes. The guard does not set `has_records`, so a later first estimate remains possible. The new parametrized test covers all three optional asset types, a changed share, the domain and API `422`, unchanged history, nickname/archive/restore, receipt replay and first estimate. The native test now scopes account/Search and nested debt locators to the visible detail and clears a retained Search query before typing; the referenced `screen.accounts` and `search.detail` identifiers exist in the shell/Search views. The manifest explicitly leaves native acceptance pending. `git diff --check` passed.

This is a read-only affected-delta review. I did not run the captain's live Postgres or simulator checks, and I make no native success claim. No repository edits or processes were created.

## Final native recovery test locator delta

Reviewed delta: `9d49cde3359a54d8d28624e5f16973d032bbd61b..0aabfb1605336d695fa59b636061e53995b65282`
Exact reviewed head: `0aabfb1605336d695fa59b636061e53995b65282`

**Findings: none confirmed.** This delta changes only `ConnectedAssetUITests.swift`. It selects the Home retry button inside the active Home scroll view, then scopes the unknown-value, recovered row, and asset-ready checks to the active Accounts scroll view. The referenced `screen.home` and `screen.accounts` identifiers are assigned by `FoundationShell`, and Home and Accounts each mount their own pending state. These changes address the duplicate mounted retry locator without changing app behavior or weakening the recovery assertion. `git diff --check` passed.

The captain reports the full native lifecycle/Search/Spanish run and 394 real financial/Postgres/recovery tests passed at the previous head. The affected recovery rerun at this head is captain-owned and was not complete when I reviewed. I made no repository edits and started no processes, app or simulator.
