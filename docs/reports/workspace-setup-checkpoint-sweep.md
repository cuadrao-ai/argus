# Workspace setup design checkpoint sweep

Date: October 24, 2026. Local design lane, existing server on port 4387.
Status: review evidence prepared; checkpoint approval and handoff remain held.
No backend integration, hosted changes, real invitation, WhatsApp message or upload.

## Scope and authority

Authority: `.agent/designs/cuadrao-business-app/DESIGN.md`.
Reviewed Home setup, its document choices, email, WhatsApp, invoicing/RNC,
invitation, progress and the connected upload/email Business surfaces. Existing
shared components own buttons, copying and email state. Model the Domain guided
separating Business data, received-document outcome and per-surface navigation.

## Confirmed gaps corrected

| Gap | Result |
| --- | --- |
| Guide invented a second forwarding address and alias editor | Guide mounts the existing BusinessEmailAddress. The guide and upload dossier display the same fixture address. No custom alias promise. |
| Email alone asked for a separate reading choice | Removed interception and retired alias/sender handlers. Automatic reading stays in Business settings. |
| Other preview tabs could replace the open step | Storage updates retain local navigation. Per-tab, per-surface session state restores navigation on refresh. Shared saved data still updates. |
| First document could never show completion | Isolated validation routes now provide a labelled received/not-received fixture outside the customer form. Normal Home still awaits receipt-event wiring. |
| Connected WhatsApp looked real | Sample-data identification remains in connected state; state headings use the shared heading font, 21px/500. |
| New address could leave shortcuts stale | Address consumers now observe Business revision; successful existing activation refreshes that revision. |
| Shared email copy used smaller type | Address text uses 16px; support and errors use 14px. |

## Verification in this pass

- 27 focused tests: preview overlay/copy/email reuse (7), shared forwarding refresh
  regression (1), sidebar and existing email contracts (19). New email reuse and
  refresh tests failed before their fixes and passed afterward.
- Browser: Home email and upload dossier show the same receiving address. Old
  saved alias-edit routes render the shared email view.
- Browser: two isolated review tabs retain independent open steps when the other
  navigates; shared sample Business data remains available.
- Browser: empty creation validates name/country; creation shows ready/optional.
  Empty invitation focuses email and shows inline error. Tapping help shows the
  permission limit; Escape closes help and leaves the form open.
- Browser: EN dark 390px guide wraps the two invoicing cards, and the explicit
  received-document fixture changes the ring from 1/4 to 2/4. ES light 390px
  invitation error and tooltip fit without horizontal overflow.
- Browser: EN light 768px invoice details allow continued editing while registry
  lookup checks. Match shows legal name/status, optional name use, confirmation
  and details disclosure. Editing RNC to an invalid value removes the old match
  and confirmation immediately and shows the format error.
- Browser: ES dark 1365px WhatsApp shows QR, one primary instruction and a manual
  disclosure. Manual message matches the link. Clicking Sent transitions to
  waiting, not connected. Only the selected response fixture completes linking;
  connected still says preview. No message was sent.
- Locale key parity: 268 EN/ES setup keys. Script parsing, scoped ESLint and diff
  checks pass. This is representative crossed coverage, not every possible state
  at every width or physical-device testing.

## Held integration requirements and limits

1. The setup's create/rename fixture is not yet bound to the actual selected
   Business directory. Its sample name can differ from the sidebar. Map one
   Business ID and owner capabilities across creation, settings and all dossiers;
   never use a display name as identity.
2. Persist guide progress per Business. Bind document completion to a confirmed
   received document; no check for opening upload, copying an address or linking.
3. Email must reuse existing intake and creation endpoints. Custom alias editing
   remains unresolved and is removed from the customer guide. Confirm creation
   semantics, permission/error handling and address refresh across all consumers,
   including global search. No new receiving service was built.
4. WhatsApp still uses fixtures: owner-only sending-number linkage, one destination,
   exact returned message/link/expiry and server confirmation. Reuse one component
   in guide and Business dossier. Keep receipt processing health separate from
   linkage. Do not enable automatic reading by linking.
5. Registry, authority and invoicing activation remain separate. Reuse the existing
   general registry process, validate server-side, keep source/check dates and
   user confirmation separate, and inspect existing invoicing wiring requirements.
   Refresh during lookup clears the in-flight state; no permanent checking bug was
   found. Missing information is a sample state, not an invented universal rule.
6. Invitations still use labelled local response fixtures. Real permissions,
   delivery, pending invitation and access granted must come from existing APIs.
7. The preview route currently reads ignored `temp/home-setup` assets. Before any
   integration transfer, package reviewed source into tracked lane files and repeat
   checks. The demo alone is not a portable delivery artifact.
8. Review-only standalone pages lack the parent React bridge. Shared email is
   verified inside actual Home, not represented by another standalone fake. Shared
   control inheritance is verified in the adapter tests and actual Home.

## Evidence

Local images in the task's `home-setup-study` evidence directory:
`checkpoint-en-dark-phone.jpg`, `checkpoint-es-light-phone.jpg`,
`checkpoint-en-light-tablet.jpg`, `checkpoint-es-dark-desktop-whatsapp.jpg`,
`checkpoint-whatsapp-connected.jpg`, and `checkpoint-shared-email-home.jpg`.

No handoff has been sent. Design review acceptance and integration readiness are
separate; the unresolved wiring above must accompany any later approved handoff.
