# PR 849 integration reconciliation

This record covers the reason-only manifest after a normal integration merge on October 5, 2026. It is verification input for the release captain, not a terminal review or release approval.

- Original integration base is `875de09ac2115acec42e09060b92878aa5f18eff`.
- Inherited PR head is `5a20a16d0f4bad89c0190940cdf62b4c10f4901a`.
- Fetched integration is `7018e0edebbc370b999005a857230bf3c3a1ad8b`.
- Reconciliation merge and verified runtime tree are `5b8a118db43a91c036e2f4d828335e32f3833894`.
- This record's commit adds evidence only. The pushed evidence commit is the final PR head recorded in the handoff.
- The manifest-only stable patch ID remains `54fcbcff41ecafce9b9ad0fed4a9733f8a8a8d29`, equal to the original implementation commit `47ee1de0f2d79729bf026b8570a6bf1dea231576`.

## Semantic overlap

PR 857 changes native provider button appearance and the auth page's foreground/background colors. Its `colorScheme` read introduces no required-reason API. It does not change any of the 35 inventory references, their source owners, or manifest inclusion.

PR 858 binds Apple capture to the linked identity in backend auth and persistence. Its API/data changes and migration do not alter an app-owned required-reason API, the manifest resource, or SDK dependencies. PR 846 adds backend deletion recovery tests. These integration changes introduce no directly affected manifest test.

The earlier PR 844 changed the Release configuration reference and social-provider guard. The synchronized app resource group, target resource membership, package declarations, and resolved package files remain unchanged. Its Release configuration includes Development configuration and overrides only the two social flags. Both checked-in defaults remain false, and non-Debug `NativeProviderConfiguration.load` returns `.off`. No configuration was enabled by this lane.

The source audit still supports app-local defaults with `CA92.1` and local elapsed-event measurement with `35F9.1`. The manifest retains only required-reason declarations. No collection, tracking, legal, or provider-operation claim was added.

## Evidence disposition

The prior unsigned Release simulator build remains evidence that the unchanged manifest is packaged through the unchanged synchronized resource mechanism. This reconciliation does not claim a new build of the merged application. The earlier whole-app build cannot prove the newly landed auth code compiles, and its runtime behavior belongs to those landed lanes' evidence.

No overlap invalidates this lane's manifest declarations or packaging acceptance. A fresh build is therefore not required for this bounded manifest reconciliation. The final release archive privacy report, dependency signatures, device acceptance, and App Store answers remain open. No Mac build slot, simulator, or device was used in this pass.

[Reconciliation checks](reconciliation-checks.txt) record seven passing validators, including five rejection cases. The retained built app's 12 manifests match all 12 recorded hashes. The app manifest bytes match the source. All 35 inventory lines and the complete matching source set remain identical. Package sources and both resolved package files are unchanged from the original base.

The combined tree passes `python3 scripts/check_modularity_budget.py` with zero violations. `git diff --check` passes. The seven tests reran with the existing `verify_manifest.py --app` command against the retained unsigned Release app. The source check compared every TSV path, line, and stripped source string to current Swift sources and compared the complete UserDefaults, AppStorage, and systemUptime match set. The package check compared each retained manifest's SHA256 and the total manifest count to `built-manifest-inventory.json`.

Prove It Works shaped this pass by checking source lines and packaged bytes directly. Independent final review, terminal CI, and any merge remain with the release captain. No hosted operation, provider contact, simulator journey, policy publication, or feature activation occurred.
