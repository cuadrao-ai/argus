# Final privacy inventory reconciliation, October 5, 2026

Original inventory base: `875de09ac2115acec42e09060b92878aa5f18eff`.
First reconciled base: `7018e0edebbc370b999005a857230bf3c3a1ad8b`.
Published starting head: `bdb276c656e160ca39c419d9d61a2dc1ec1fcebc`.
Preceding integration: `70b0cd3891937f026900aceb96ce5f556c76b0b3`.
Preceding normal merge: `8ed6dc9ac43c260ec1b6c625732e34493bf53cda`.
Reviewed documentation head: `7d8bf088b98eed0b5c712976e90343013e62fbb0` (clean independent review).
Current integration: `7d037b07d4b98b34c6c0ad3026811c7d2f28ae47`.
Current normal merge: `968e2d8d3f6bdffeab70438f42679b4aec19a6d7`.
The commit containing this record is the final documentation head; the release captain records its exact SHA in the independent review and terminal CI report.

Semantic overlap was confined to the report's source claims: #849 app reasons/package evidence, #862 Apple admission/receipts/recovery, #869 server initialization and #847 personless completion. The integration merge had no conflicts. Runtime owners and API/data changes were inherited from integration without edits. The original outbound-path inventory, 14 dated official links and 19 reference/snapshot checks are retained. Native #864 is open and unmerged at `a24a6c60627460ddfd6042b3f42b342c5eff11f0`; local review does not supply Mac or phone acceptance.

Verification: 19 references/snapshots passed; 18 named source/configuration fingerprints match current integration; the retained baseline inventory contains 12 app/SDK manifests; combined-tree modularity has zero violations; whitespace passes. These are documentation/source checks, not execution of provider behavior. No behavioral test, database, app startup, simulator, device or provider request ran here.

Official Apple required-reason DocC JSON and PostHog create/retrieve documentation were refreshed on October 5. Apple's browser HTML was JavaScript-only and its Markdown response could not be rendered, so the official DocC JSON supplied the refreshed readable source. The existing #849 dated reason audit remains the reason-specific evidence. PostHog documents write/read scopes and separate create/retrieve endpoints, not successful deletion in this project. No other unchanged official source was refreshed unnecessarily.

PR #781 remains the open legal-draft owner at `b9a695d747b6ee1cf20c485cc5051a979c1d5a83`. Its unpublished Spanish/English draft was read without edits. The inventory gives factual corrections for provider omissions, confirmation/pending wording, retained financial facts, provider sharing, consent, withdrawal and deletion completion. Entity/contact, retention/backups and counsel facts remain unknown.

#818/#826 inclusion, #828 version/provider/purpose/shared-person consent, #805 frozen balance and #819 spaces remain open. #811 reuses #837 local migration/RLS evidence while hosted readback stays open. #700/#656 apply only to retained paths. #686/#694 remain promotion-window gates. Signed archive, SDK signatures, real provider completion, hosted settings and phone proof remain open. No flag, legal publication, operator, alert or cron was selected.

Independent review, exact-head CI, guarded merge and integration landing belong to the release captain. This owner stops branch writes after publishing this documentation update.

## Focused #854 follow-up

The actual financial/configuration delta adds optional destination amounts and visible per-leg amount/currency projection. Visibility filtering keeps a hidden source denomination out of the legacy summary. No new schema, FX rate, provider transmission or privacy consent owner appears. Current Plan attribution still requires every leg to use the Plan currency. Mixed-currency writes stay disabled through `CUADRAO_CROSS_CURRENCY_TRANSFERS_ENABLED=false` in the source default, example, release profile and Render declaration. `.github/argus-env.sh` now derives API environment membership from the release profile rather than a copied key list. These are source/configuration observations, not hosted readback or activation.

The original 11 privacy-source fingerprints are unchanged and still match integration. Seven financial/configuration fingerprints were added, making 18. The original 19 reference/snapshot checks and 12-manifest baseline package evidence remain applicable. Official sources, PR #781 legal ownership and all native/provider/phone/consent gates are unchanged. No external source refresh or runtime execution was needed for this source-only delta. A focused independent context review and new exact-head CI remain release-captain owned.
