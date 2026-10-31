# Staging checkpoint gate ledger, 2026-10-27

**Reconciled at integration `dffee6925`, 22:45 UTC.** The original local inspection
at `c74221f69`/API `af5d14a20` (18:50 UTC) found no safe gate-only product fix.
That historical review is not a claim that editing remains disabled. Later #1400
and hosted editing acceptance completed; API is now `dffee6925`, web/Marketing
`c74221f69`. Source anchors below identify inspected owners, not fresh line-level
hosted probes. See [start here](../START_HERE.md) and the
[release policy](../handoffs/staging-release-policy-20261027.md).

## Decisions

| Gate and source at inspected SHA | Saved value / observed state | Class, owner and risk | Removal or completion criterion |
| --- | --- | --- | --- |
| [Business pilot](../../web/lib/private-alpha-flags.ts#L28), `NEXT_PUBLIC_BUSINESS_PILOT_ENABLED` | true; Business shell visible | Release rollout; release owner; controls app entry | Retire only after supported-account release acceptance. No change needed here. |
| [Business search](../../web/lib/private-alpha-flags.ts#L59), `NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED` | true; search visible | UI rollout; frontend/release owner; scoped result correctness | Real search is already exposed. Retire the flag after scope/account-switch coverage and release decision, not to cure an unrelated hidden preview. |
| [Account WhatsApp preferences](../../web/lib/private-alpha-flags.ts#L48), `NEXT_PUBLIC_BUSINESS_WHATSAPP_PREFERENCES_ENABLED` | true | Temporary UI entry; account-channel/release owner; real account link/unlink controls | Keep account/Business attribution separate; this flag cannot reveal the independently gated Reception row. |
| [Reception canvas](../../web/components/business-app/BusinessInboxPanel.tsx#L248), development + `NEXT_PUBLIC_MOCK_AUTH` | production; mock auth absent/false; legacy connected inbox visible | Missing connected contract; Reception domain/frontend owners; local archive/seen and loaded-arrival behavior would look durable | Connect authorized arrivals/counts/pages/identities and durable archive/restore/personal seen before removing the gate. |
| [Reception WhatsApp row](../../web/components/business-app/BusinessReception.tsx#L18), development + mock | hidden live; row uses local connection state and setup preview | Attribution and simulated state; account-channel/frontend owners | Authoritative account-link destination must bind to the selected Business; then reuse real controls with switch/revoke guards. Do not expose local linked state. |
| [Invoice UI](../../web/lib/private-alpha-flags.ts#L80), `NEXT_PUBLIC_CUADRAO_BUSINESS_INVOICING_ENABLED` | on; Facturación visible after editing release | Durable editing rollout; release owner | Bounded save/reload/exact-retry acceptance passed; retain permissions and require a separate decision to retire the flag. |
| [Invoice API](../../src/argus/domain/business/invoicing/config.py#L9), `CUADRAO_BUSINESS_INVOICING_ENABLED` | on; customer/incomplete-draft editing accepted | Durable editing control; Business backend/release owners | Editing-only acceptance passed. Backend authorization remains mandatory; fiscal issuing remains held. |
| [Fiscal service/contact](../../src/argus/domain/business/fiscal_sandbox/config.py#L14), `CUADRAO_FISCAL_SANDBOX_ENABLED` / `CUADRAO_FISCAL_SANDBOX_CONTACT_ENABLED` | off in latest release handback | Consequential provider controls; fiscal/release owner | Keep held until separate exact fiscal approval. Editing activation does not start the service or authorize contact. |
| [Profile invoice setup](../../web/app/design-workspace/BusinessProfilePreview.tsx#L130), `!live` | hidden in live profile | Missing fiscal readiness/configuration contract; fiscal/profile owners | Replace local setup state with supported readiness/configuration facts; keep approved layout. Not a safe pure-UI removal. |
| [Personal invitation](../../web/components/sidebar/ProfileMenu.tsx#L152), development + mock; [example URL](../../web/components/sidebar/CuadraoInvitationPreview.tsx#L18) | hidden live | Missing account invitation service/policy; account/product owners | Unique real links, delivery/history/expiry/limits and admission decision. Never expose the example URL or simulated sent state. |
| [General notices](../../web/components/business-app/foundation/BusinessNotifications.tsx#L119), preview + development + mock | sample notices hidden; live Business membership invitations already connected | Missing durable notices; notification owner; local read/dismiss/count state | Implement recipient-scoped notices/read/dismiss/counts; preserve existing Business invitation acceptance. |

The separately read `[removed obsolete setting]=false` is not a UI
cleanup candidate. No matching application consumer was established by the
targeted source lookup; retain it and require its operational owner to resolve
that declaration before any removal. No diagnostic/provider tests were run.

## WhatsApp attribution boundary

[Link status](../../web/lib/whatsapp-link-api.ts#L13) has no Business ID.
The client calls the header helper without a path; its
[default forwards the chosen grant](../../web/lib/argus-api-transport.ts#L29).
The [server owner-only guard](../../src/argus/api/whatsapp.py#L543) refuses
client/non-owner grants, then resolves the account's own open Business and
returns account-owned link facts. That does not supply an authoritative
selected-Business-to-link-destination binding.

An Owner role alone is not that binding.
[`GET /business/space`](../../src/argus/api/routers/business.py#L272) uses the
selected working scope, so it is not an independent account-destination proof.
Do not use `startBusinessSpace` for discovery: its missing-space path may POST.
The missing contract is a read-only canonical destination ID or equivalent
authoritative binding, with safe account/Business/grant-switch behavior. Until
then, hold the Business-labelled row. Do not build a second link system or
automatically generate codes, unlink, or change reading consent.

## Remaining work, no new implementation authority

Editing-only activation and bounded acceptance are complete. Continue with:

1. Canonical Reception arrivals and identities/counts/pages, durable Business
   archive/restore and personal seen/unseen, idempotence/concurrency/Activity.
   Include the account-to-Business WhatsApp attribution gap.
2. Durable recipient notices and real unread/read/dismiss counts. Keep the
   already-connected Business membership invitation behavior.
3. Account-owned personal invitations with real links/history/delivery/expiry/
   limits; settle direct admission versus approval queue separately.

This is a compact gate/approval handoff, not a replacement roadmap. Historical
local-only evidence supplied with the original review was `reconciliation.json`, `live-inspection.json`,
`current-nonsecret-gates.json`, and
`next-stabilization-approval-bundle.json`. These artifacts are not prerequisites to understand the summarized gaps. This
documentation reconciliation ran no browser/provider probes or hosting changes;
it incorporates the later authorized editing outcome from the coordinator.
