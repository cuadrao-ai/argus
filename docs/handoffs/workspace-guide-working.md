# Workspace guide working preview

Local design only. No checkpoint clearance, handoff, backend changes or release.

Current sweep: [workspace-setup-checkpoint-sweep.md](../reports/workspace-setup-checkpoint-sweep.md). This supersedes earlier alias and separate reading-flow notes below. Those descriptions are historical, not current behavior.

The existing Home on port 4387 embeds the existing scratch source in temp/home-setup/index.html through web/app/design-workspace/card/route.ts. The guide has creation or received-access entry, followed by independent document, invoicing and invitation actions. Optional business details no longer block onboarding. Country does not restrict DOP, USD, EUR or CAD document currencies.

Document methods reuse the existing upload flow and Business receiving-address component. Email no longer offers a separate alias editor, sender simulation or reading-consent step. Automatic reading stays in Business settings. Inputs keep visible labels and reserved feedback.

## Local checks

- Browser checked required name feedback, creation to independent actions and document method choices.
- Browser checked separate reading consent, unavailable alias, suggested alias selection, address confirmation and sender setup.
- Browser checked saved name, address and draft sender across navigation/reload.
- Narrow 390px container checked in light and dark themes; alias layout had no horizontal overflow. This is a container review, not a physical phone check.
- Invoicing choice and deferred fiscal fields opened correctly.
- Local JavaScript syntax and focused ESLint checks passed.

## Integration and remaining verification

- Every mutation and availability result is a local fixture. No emails, invites, files, WhatsApp messages or invoice requests are sent. Do not use the displayed address or code as a live destination.
- Real alias results, domain, collisions at save, limits and route readiness must come from the API. The prototype uses the reserved example.test domain.
- Access must follow enforced capabilities. The current preview describes document preparation separately from approval and administration. No additional role is asserted as implemented.
- Invited users reuse the existing Business; a local scene=invite review state shows the acknowledgement. Real invitations and workspace selection need binding.
- WhatsApp displays its receiving Business. Multi-client routing and client ownership remain unresolved; the preview does not implement either.
- Invoicing activation remains visible, with issuance gated. This local guide does not replace or qualify the separate provider sandbox evidence.
- Automatic reading must use the Business-wide consent contract, including server disclosure and permission checks.
- Shared FormField components and both locale files must own the integrated version. This scratch HTML uses the approved field geometry for visual review. English coverage, live API behavior, physical devices and assistive-technology checks remain before a shipping checkpoint.

## Setup rail review, 2026-10-23

Local prototype only. The existing 4387 Home embeds the updated scratch card.
- A neutral vertical rail holds numbered available actions. Completed actions show a check; the open action keeps its number with a filled accent circle.
- The header shows the completion count and a compact progress track in both expanded and collapsed states. It no longer repeats the Business name.
- Invoicing activation is numbered and included in the count, per the October 23 correction. Choosing a path or saving fiscal details marks neither registry authority nor issuance as complete. Users can collapse the guide and continue basic use.
- Upload and email use the existing FileUp and Mail icons. WhatsApp uses the requested recognizable bubble and handset in the same 44px tinted tile. Text labels remain visible.
- Opening a channel, saving an alias or selecting a file does not complete the first-document action. The prototype cannot prove receipt of a document.
- Invitation progress represents the local simulated submission, not real delivery or permission grants. Editing a later draft does not undo that earlier simulated outcome.

Verified in the existing preview: desktop light, 390px light/dark, collapsed count after reload, keyboard expansion, focus on the selected step/subview, email round trip with saved alias, and no horizontal overflow at 390px. JavaScript syntax check passed. Hosted completion events, real invitation delivery and actual document receipt remain integration checks. No handoff.


## RNC lookup and validation, 2026-10-23

Frontend-only review. No DGII requests, new integration, handoff, or hosted changes. The fiscal form includes a visible fixture selector labeled “Vista previa · datos de ejemplo”. Its outcomes are coincidence, status requiring review, no match, and unavailable. Invalid format is a separate field state. A delayed fixture response exercises checking and stale-response handling.

The workspace minimum remains name plus country. RNC and the fiscal-name draft are optional. An empty RNC does not trigger a lookup. A nonempty RNC checks the existing nine-digit format rule, permitting spaces/hyphens and rejecting letters/all zeros. This is not a registry check or checksum certification. The form remains usable during lookup; draft saving never completes invoicing activation.

Registry responses contain the queried RNC, legal name, returned business status, source date and check timestamp. The user can confirm the intended business and explicitly apply its legal name. Applying it updates only the fiscal draft, never the workspace display name. An RNC edit clears the response and confirmation immediately and invalidates older requests. The preview stores entered RNC, fiscal-name draft, returned record, lookup status, check date and confirmation date separately. A failed or absent match is pending, not fraud or an invalid business.

### Backend requirements held for clearance

- Provide the lookup service and authoritative response contract, source-refresh process, source/check timestamps, freshness thresholds, stale-data policy, timeout/retry/error handling and any rate limits. Source date and check date are distinct.
- Validate on the server. Never trust a frontend verified or confirmed flag as registry proof, authority or invoicing readiness.
- Store entered RNC, normalized queried RNC, returned registry details and source/check dates independently from the user's business-identification confirmation and its actor/date. Define when stored results require rechecking.
- Resolve fiscal legal-name storage separately from workspace display name. The inspected fiscal-profile backend currently shares the Business name; the proposed explicit adoption must not overwrite that display name during integration.
- Apply existing permissions to edit/confirm these details. Flag identity/status changes affecting invoicing for the appropriate checks; do not give document editors implicit approval or issuance authority.
- Keep registry matching, the user's authority to act and invoicing activation as separate states. A confirmed match is not electronic-invoicing readiness.
- Bind alias availability, reserved/review-required verdicts, save-time conflicts and the real receiving domain to the existing API. Local availability remains a fixture.
- Keep upload validation and active limits in the existing upload dossier and its API capabilities. The setup guide has no separate file picker or upload rules. Server MIME/content validation remains required.
- Migrate this scratch form to the shared FormField and locale owners before integration. Tests must cover real permissions, persistence, stale responses, all lookup states and backend errors.

No orchestrator message until explicit checkpoint clearance.


### Verified locally in this pass

- Empty workspace submission reports both required fields and focuses the first invalid field. Name plus an explicit country creates the preview workspace.
- Invalid RNC typing stays quiet until blur; letters and all-zero numbers are rejected. Empty fiscal details can be saved.
- Checked all labeled RNC fixtures: checking, match, status requiring review, no match and unavailable. Saving remains possible while checking and for unsuccessful lookups.
- Confirmed explicit legal-name adoption preserves the workspace display name. Editing the RNC immediately removes the old record and confirmation; delayed earlier results cannot reappear.
- Blank and unavailable aliases cannot be saved. A valid alias saves with one click after availability completes. Sender and invitation email errors clear after correction; invalid invitations do not advance progress. All submissions in these forms were synthetic local fixtures.
- Inspected the RNC match at 390px in both themes, including dates, optional labels, confirmation and draft saving. No horizontal overflow. These are narrow-container checks, not physical phone or screen-reader certification.
- JavaScript syntax and focused ESLint checks passed.

### Reuse of the existing upload dossier

The setup card's Subir archivo now invokes the same upload_receipt action used by + Agregar. The parent validates the message origin and iframe source, applies the existing menu's access condition, and runs the current Business action. The duplicate inline file picker and its validation were removed. Opening or closing the dossier does not complete the first-document step.

Browser verified both entry points open the same Agregar dossier with file selection, paste, typed-document entry and document classification. No file was uploaded. The dossier uses the parent's actual selected Business; the guide's simulated workspace name is not a routing instruction. Binding the whole guide to the real selected Business, actual document-received progress and final keyboard focus restoration across the prototype iframe remain integration checks. No backend changes or orchestrator handoff.

## WhatsApp connection preview and theme sync, 2026-10-23

Local design only. The existing Home preview and its Business settings panel share one connection renderer. The guide now follows the applied root theme through a DOM observer and ready handshake; the previous theme effect could read the old class. The parent sends mobile viewport state so a narrow desktop dossier retains its QR while mobile prioritizes Open WhatsApp.

The view shows destination, receiving number, exact message, expiry, waiting, expired, linked, unavailable, missing-recipient and ineligible fixtures. QR, button and manual message use the same response object. A small channel mark sits inside a high-error-correction black-on-white QR; Cuadrao appears above. Expiry removes sending actions and the QR. Linked state follows a simulated status response, never opening/scanning. Disconnect explains that existing receipts remain. Automatic reading stays separate and applies across channels.

### Wiring held for checkpoint clearance

- Reuse the existing message_text, wa_me_url and expires_at response without rewriting the message. Server expiry is authoritative; fixture timestamps are not a production timer contract.
- Provide authoritative destination Business and receiving-number metadata. The inspected current link contract is owner-scoped, not an arbitrary selected-client routing API. Enforce eligibility server-side and handle null links, rate limits, status refresh, expiry and disconnect/reconnect.
- Move the entry point from Personal settings to Business settings only with the integration owner's review. Replace stale reading-consent copy; linking must not grant consent.
- Keep linking, media intake and document processing separate. The reported media failure requires independent integration verification.
- Replace local fixtures/storage with API state; package the ignored QR runtime and shared view into normal frontend components and locale owners before shipping. No production dependency was changed here.

### Evidence and remaining checks

- JavaScript syntax, focused adapter/route ESLint and git diff --check passed.
- Browser checked waiting, expired, connected and disconnect states; connecting and disconnecting preserved reading=false. Guide and Business settings displayed the same code and expiry.
- Live dark-to-light change updated the guide without reload. Desktop dark and mobile-width light/dark were inspected during this pass; these are preview checks, not physical-device proof.
- Decoded a screenshot of the rendered QR including its center logo: it exactly matched the Open WhatsApp URL and manual message. No external message was sent.
- Remaining: physical iOS/Android camera scans, real server status/expiry/routing, recipient ownership and media processing, all error fixtures, final theme roundtrip in the dossier, and keyboard/screen-reader focus across the preview iframe.

No orchestrator handoff. The working preview remains local and synthetic.

## Compact WhatsApp presentation, superseding the expanded flow above

The Home guide now has only destination, connection status and one connect/manage action. It opens the existing AdaptivePanel. Below the app's 1024px desktop breakpoint, the panel opens at its full sheet snap; phone presentation uses the shared 720px threshold. The content iframe expands to its measured height and leaves scrolling to the panel.

Ready, waiting, expired, connected and error are mutually exclusive views. Desktop/tablet lead with QR and one sentence; phone leads with Open WhatsApp. Manual number/message copying is collapsed. Automatic reading is removed from the linking surface and remains a separate Business-setting responsibility. A simulated linked response closes the panel and updates the guide. Linking does not complete the first-document task. Management contains only the linked sender, destination and disconnect action until confirmation is requested.

EN/ES strings for this WhatsApp path and its surrounding guide framing live in the common locale files under workspace_setup_preview. Language changes are passed from the app to both frames. Other draft setup forms are outside this copy pass and still need the shared-form/locale migration noted above. The local app language picker failed its existing profile API save during QA; EN was therefore checked using the same route's explicit local language option. Do not claim live account-language persistence was verified.

Evidence in the local visualization directory home-setup-study:
- compact-{phone,tablet,desktop}-{guide,connection,connected}.jpg shows the three requested views in the actual app.
- Browser viewports checked at 384x844, 768x1024 and 1440x900; also checked the manual flow at 320x568. No horizontal overflow in the checked parent/frame layouts. The iframe's scroll dimensions matched its allocated dimensions; the outer panel owns vertical overflow. Primary action text remains 16px and controls at least 44px tall.
- English guide framing, connected summary, ready/manual flow, error and expiry checked. Dark English connection and guide screenshots are saved separately. The normal preview hides fixture controls; ?qa=1 exposes them for review only.
- Waiting did not claim connection. Expiry removed QR and sending actions. Error replaced the instructions with retry. A linked fixture closed the flow and updated the compact guide; disconnect preserved the existing receipt explanation.
- Syntax, focused ESLint and locale-key parity checks passed. No real connection, message, receipt intake or hosted verification occurred.

Still held for integration: real server status refresh, permissions/destination binding, live expiry and media receipt, phone-camera scan proof, app-language API save, full screen-reader/focus review, and migration from ignored scratch/iframe to normal shared components. No handoff or commit authorized in this pass.

### Preview outside-click dismissal and typography

A pointer press inside the setup iframe did not reach the parent document, so the Settings popover stayed open. The preview now sends a pointer notification from the frame and accepts it only from the same origin and one of its two mounted frames. It dispatches on that frame element so the existing overlay registry still decides containment and topmost ownership. Shared Settings behavior is unchanged.

The focused DOM regression failed before the bridge and passes afterward. It covers outside dismissal, rejection of unrelated windows/origins/null sources, and keeping an enclosing overlay open without dismissing a lower menu. The focused bridge and shared overlay tests pass together (13 tests). The parent design pass also verified the Settings → Preferences → close submenu → outside guide press sequence in the live preview.

The dev-only preview route also serves the two existing app fonts from fixed asset names. This avoids inheriting a font-family name without loading its face inside the iframe. When integrating the guide, use the shared FormField and app typography directly; the preview adapter is not production wiring.


### Workspace first step and header, October 23

The setup header now uses a neutral surface, the app heading face, and a completed-count label. Green remains on the main action and completed rail nodes. The numbered rail is the progress pattern; the extra header progress track is hidden. This is a local design proposal awaiting founder review, not a new approved rule.

The first step keeps name and country together in a 560px form. The three supported countries use labelled native radios with visible selection and keyboard behavior. No country is preselected. Input and action text stay at 16px; country choices stack on phones. Both values save to the existing local draft on edit. Submit validates both and focuses the first invalid control; invalid submission cannot create a workspace. This pass localizes the creation form and its invitation entry in EN/ES. Other prototype forms still need full locale migration before integration.

Browser checks: empty submit shows both inline errors and focuses name; correction clears errors; name and country survive refresh; back from the invitation entry retains the draft. Shared form styling/validation remains the production integration owner; the ignored HTML is a design prototype. Settings outside dismissal was also checked after opening/closing Preferences and after opening/closing Appearance, then reopening Settings. The same iframe boundary fix covers the observed guide-click case. No separate shared Settings lifecycle defect was reproduced.


### Invitation step presentation

Replaced the green permission banner with a neutral access row and an accessible info disclosure. The optional label belongs to the task. Email remains required only when sending; Skip for now keeps the draft without completing the rail. The field, actions, disclosure and result messages use EN/ES locale keys. Pending uses amber with an explicit label; access granted is a separate confirmed fixture and can complete the rail.

The local invitation object holds email and status (draft, deferred, sending, error, pending, granted). A refresh during the synthetic request restores a draft. The normal mock returns pending. Review routes can set inviteResult=error or inviteResult=granted; these are fixtures and send no email. Production must derive state from the returned grant/invite lists and invite_delivery, including not_configured/failed. The current giveBusinessAccess request takes only email and grants read+prepare for a confirmed account, otherwise a pending invitation. It exposes no arbitrary role selector. Confirm real eligibility and destination binding at integration. No backend change or handoff.

Invitation preview verification: initial empty field stays quiet; empty submit shows localized inline feedback and focuses email. Info disclosure opens and Escape closes it. Skip preserves the draft and keeps the completed count unchanged. Error fixture preserves the email and offers retry; retry to pending does not increment completion. The granted fixture increments completion and shows Access granted. Checked English dark phone (384px and 320px) and tablet (768px), plus Spanish light in the existing Home. No horizontal overflow in measured narrow views; input text is 16px. Syntax, locale parity (118 keys) and diff checks pass. Evidence: invite-es-light-desktop.jpg, invite-en-dark-phone.jpg, invite-pending-en-dark-phone.jpg in the local home-setup-study directory. No live delivery, real permission grant or hosted verification was performed.

### Dropdown and checkbox review, October 24

This remains a local design preview. No handoff is authorized.

- All select controls in the sketch now use one picker treatment matching the
  existing menu geometry, theme surfaces and selected check. Native source
  selects retain their values and change handlers; visible controls use
  combobox/listbox semantics, keyboard selection and outside/Escape dismissal.
- RNC and WhatsApp fixture controls are siblings of the setup card, behind
  Preview controls, and appear only with explicit review/qa parameters. Normal
  Home has no scenario selector. Registry fixture results remain labelled.
- Checkbox rows use native labelled inputs with 20px rounded glyphs, 4px corners
  and at least 44px row targets. The RNC result keeps confirmationDraft separate
  from confirmedAt. Save applies it; toggling alone only preserves the draft.
- Neutral instruction and email-address surfaces replace green informational
  fills. A registry status requiring review uses an amber edge and explicit text.
- RNC fields, result states, validation, actions, dates and preview controls now
  have EN and ES copy. The locale namespace has 166 matching keys.

Observed local checks: label click, Space toggle, save confirmation, validation
focus, stale-result clearing on RNC edit, match/review/no-match/unavailable,
Arrow/Home/End selection, Escape focus return and outside dismissal. ES light
and EN light/dark were inspected, plus ES dark at 320px. Phone row targets were
68px or 92px when text wrapped; desktop 44px. No horizontal overflow at 320/384px.
The 320px menu stayed within viewport bounds. Tablet was 768px. Syntax and locale
parity checks passed. Evidence is under the existing home-setup-study directory,
controls-*.jpg. These are browser previews, not physical-device or live-service
proof. Existing API, server validation and permission wiring gaps still apply.

The Model the Domain principle keeps the draft checkbox separate from the saved
confirmation. Production integration must use the shared UI controls and persist
that distinction without trusting a frontend confirmation flag.

### Electronic invoicing paths and dossier, October 24 (held)

Scope: frontend preview on the existing 4387 server only. No handoff, backend
service, live registry call, provider connection, certificate upload or issuance.

The Home task now says Set up electronic invoicing. Two compact cards choose
existing issuer or getting started; a small help disclosure explains the choice.
The shared Business AdaptivePanel hosts the full flow. Home shows only destination,
current status and Continue setup once a path starts. Cards stack at narrow widths.

Existing issuers review their declared setup, saved Business details and pending
connection requirements. There is no universal provider-connection promise. New
issuers see Business details, one certificate-readiness question, one authorization
question and activation review. The exact proof and service requirements remain
integration work. Back, close/reopen and refresh retain local progress. Changing
paths reuses the same Business details. These local readiness answers are not
certification or authority evidence.

The five preview states are not started, in progress, needs information, awaiting
verification and active. Only explicit preview controls can select active; saving
Business details never does. Request review is simulated and labelled. Production
must render service-returned states and next actions. The needs-information fixture
uses missing Business details as its example; do not hardcode that as every failure.

RNC remains optional. Its result shows the legal name, registry status, confirmation
and use-name action. Source/check dates and queried RNC are under View details.
Changing RNC clears the result and draft confirmation. Saving applies confirmation.
Saved legal name and RNC appear as editable summaries; missing fields stay visible.
The display name is separate. Blank details can be saved and basic use continues.
A malformed entered RNC has inline feedback and focus; no match/service failure stay
pending review. The general registry lookup does not depend on issuer activation.

Read-only integration map, to hand over only after founder clearance:

- Reuse domain/business/rnc_registry.py (DgiiRncRegistry, RncRecord) and the existing
  public.dgii_rnc_lookup process. The registry migration is
  supabase/migrations/20261018190000_dgii_rnc_registry.sql. Lookup is service-role-only;
  never call it directly from the browser. No customer lookup HTTP route was found
  in this checkout. Add/reuse an authorized service boundary after integration audit.
- Reuse the existing source import and refresh runbook, docs/runbooks/dgii-rnc-import.md,
  .github/workflows/dgii-rnc-import.yml and scripts/ops/dgii_rnc_import.py. Configured
  import code is not proof that hosted data is loaded or fresh. Preserve source date,
  check time, no-match, unavailable/not-loaded and stale-data distinctions.
- GET/PATCH /business/fiscal-profile already exist in api/routers/business_fiscal.py.
  GET returns name, tax_id, can_edit. PATCH uses Idempotency-Key and previous-value
  checks. Its name is the workspace display name, not a legal name. Do not map a
  returned DGII legal name into that field. Server editing currently requires the
  owner plus approve capability; use enforced permissions, not a frontend role label.
- Separate legal name, entered RNC, registry snapshot/source/check dates, confirmation,
  authority evidence, activation path/progress and next action need a contract review.
  There is no complete persisted activation model in the inspected profile endpoint.
  Server validation and conflict handling remain mandatory. Editing invoicing-relevant
  details must trigger the appropriate service checks, not a client active flag.
- Retrieve the separate electronic-issuer sandbox proof and exact provider contract
  from integration when cleared. That proof was not located in this checkout. The
  provider's issuer-directory check is not the general DGII registry. Keep the two
  independent; do not infer absence of the sandbox work from this checkout.
- The preview currently uses ignored temp/home-setup/index.html, invoicing.js and
  invoicing.css through a dev-only route. This is not a production bundle or portable
  checkpoint yet. Convert to shared components and persisted contracts at integration.

Local verification: both paths, saved details reused, blank details allowed,
step-local validation, Back preserves answers, close/reopen and refresh resume the
saved step, Home reflects status, and all five fixture states were exercised.
RNC checking, compact match, source disclosure and stale-result clearing were checked.
Phone 320px and 422px standalone previews, actual Home dossier at 349px, tablet 768px
and desktop were inspected. No horizontal overflow observed in measured views.
Spanish light actual Home/panel and English light/dark plus Spanish dark isolated
previews were inspected. Actual app language save returned an error on this mock;
English content was verified through the preview URL, not successful account-setting
persistence. Physical devices and full screen-reader review remain unverified.

19 focused overlay/iframe tests passed. Focused ESLint passed for the adapter and
route. Syntax, locale parity and diff checks are recorded with the final local pass.
Screenshots remain local in the existing home-setup-study evidence directory.

Final local pass: actual Home dossier also checked at 320x568 in dark theme and
1440x900 desktop. The 320px panel had one scroll container and no horizontal
overflow; its primary action remained reachable at normal type size. Removed
redundant existing-issuer status sentences. Syntax passed and EN/ES have 220
matching namespace keys. git diff --check passed. No live activation or registry
verification was performed, and no handoff was sent.

Correction after founder review: invoicing path cards belong in Home and reuse the
Upload/Email/WhatsApp card and icon-tile treatment. Removed the duplicate chooser
from inside the dossier. Change path closes the dossier and returns to Home's
cards. Choosing the same path resumes its saved step; changing paths preserves
shared Business details. The Model the Domain principle keeps the guide's chooser
view separate from activation status. Both card-to-dossier routes and the return
to Home were verified on the existing preview. No handoff.

Form correction after founder review: RNC and legal name use the existing labelled
input pattern, prefilled with saved values. Removed the per-field edit summaries
and their dividers. There is no extra click to edit a saved value. This supersedes
the editable-summary presentation above. The preview reuses its existing field
renderer; production integration must use FormField, as signup does. RNC remains
text with numeric input mode. Inline validation and saved draft behavior remain.

First-step and invitation polish: removed the redundant introduction and reduced
extra gaps while preserving error space. Country has no default; saved drafts
retain the selected radio. The name is a workspace display name, not a legal-name
requirement. Known invitations reuse existing business details. Invitation access
is fixed to the supported permission, with short limits in a keyboard/touch tooltip.

Country checkpoint, held for approval: treat operating country as a declaration,
not verification. A different fiscal jurisdiction can be legitimate. Define the
relationship before rejecting a mismatch. The server must check jurisdiction,
fiscal details and invoicing eligibility; unresolved conflicts need correction or
review before activation, without blocking basic workspace use. Keep country,
registry matching, authority and activation separate. Country corrections need
existing edit permissions and checks for affected invoicing configuration. Never
silently overwrite country from a registry, location or phone prefix. Document
currencies remain independent. No backend enforcement was added in this preview.

Workspace-pattern sweep, October 24: the design guide now owns form sizing,
feedback reservation, recovery after completion, and tooltip versus disclosure
rules. Email alias and authorized-sender forms now use localized EN/ES copy,
44px suggestion targets and the shared form scale. Invoicing choice errors reserve
space and expose the invalid radio group. Completed workspace setup reopens a
summary and permits a local display-name correction. It preserves the workspace
object, country, legal details, alias and completion state. Shared-access fixtures
have no rename action. Integration must use enforced edit permissions, persist the
rename on the same Business, update the directory/sidebar and expose it in Business
settings. The preview changes only local fixture data. No checkpoint was sent.

Verification for this sweep: local browser checks covered creation, reopening the
completed step, rename validation, Cancel, refresh recovery and unchanged forwarding
address. Email alias and sender errors were checked in English. Suggestion targets
measure 44px; narrow alias inputs keep the suffix on a separate line. The invoicing
choice error left the action at the same vertical position and cleared aria-invalid
on selection. WhatsApp manual instructions remain a disclosure. Layouts inspected
at 320px, 768px and desktop, with EN/ES and both themes represented. These are local
browser fixtures, not physical-device or backend proof. Literal translation keys,
262-key locale parity, JS syntax, focused adapter/route lint and diff checks passed.
The Model the Domain principle keeps the editable name draft separate from the
saved workspace, so cancellation does not replace the stored name.

Button inheritance correction, October 24: the existing preview adapter now imports
business-ui button classes and mounts the shared CopyButton in the email and
WhatsApp copy slots. It loads the app stylesheet into both guide and dossier
frames. Legacy sketch styles stay in the components layer so shared utilities win.
Cancel and defer actions use the outlined secondary level. Email removes the
redundant Done action. EN/ES copy remains in the existing locale files. Integration
still owns real sending, permissions and persistence; no checkpoint was sent.

Typography and review consolidation, October 24: setup progress and supporting
labels use 14px; Business navigation and its current business name use 16px.
The preview inherits the app's loaded Inter and Space Grotesk variables. Awaiting
review and active now render the status and saved details together. The summary
round trip is removed, and Home opens View setup for these read-only states.
These remain frontend fixtures. No activation or verification behavior was wired.
