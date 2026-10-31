# Six-lane MVEE delivery handoff

**Status:** Lane contract. Founder decisions of 2 October 2026 are written in as contract and acceptance. This file assigns no worker, merge, hosted change, or deployment.
**Integration:** `codex/private-alpha-next` at `2185aefe8390490f7edf7dc2f127b3a9d71f2e98`, 2 October 2026, which is landed PR #779. The code facts in this file were read at `d9a7acfc`, which includes landed PR #776. The two commits since then, #780 and #779, change docs only.
**Decisions:** [decision log, October 2 lane locks](../argus-decision-log.md#october-2-2026-cuadrao-lane-locks). That section landed with PR #780 at `3b840605`. This file links there and does not restate the rationale.
**Design checkout to preserve:** `codex/cuadrao-design-scan-recents` at `8f521518`. That branch owns Cuadrao UI chrome and has already diverged from integration. Delivery lanes do not edit its files and do not merge it.
**Product owner:** [MVEE](../argus-minimum-viable-ecosystem-experience.md). This handoff links to that owner. It does not copy a second scope list.
**Execution map:** [execution board](../argus-execution-board.md).

The lanes below land on integration one at a time, in the order under [Landing order](#landing-order), through one integration captain. The team is small, so lanes are built one after another, not in parallel.

On 2 October, account deletion moved out of account moves into its own lane, [Lane 6](#lane-6-account-deletion), so this is now a six-lane handoff. The file keeps its five-lane name so existing links still work.

## Decisions this handoff implements

Lucas locked rows 1 to 10 and rows 12 to 18 on 2 October 2026. Rows 12 to 18 were locked later that evening. Rows 12 to 14 settle what this file first listed as open items 1 and 2, and row 18 settles the Sign in with Apple item. Rows 11 and 19 and the extras listed under the table are Head of Engineering delivery decisions, not founder locks. The reasons and wording for the founder locks live in the [decision log](../argus-decision-log.md#october-2-2026-cuadrao-lane-locks). The right column says where each one lands and what the code has today.

| # | Decision | Lane | Today on `d9a7acfc` |
| --- | --- | --- | --- |
| 1 | An invite is a cuadrao.ai universal link plus a code plus a QR. Household email is out of scope for this pass | Household | Share link only, with the unregistered `argus-household://invite#` scheme. No code, no QR, no universal link |
| 2 | Each code works once and records who sent it. The one exception is the founder group link in row 13. The inviter gets an "invitation accepted" notice | Household, then Updates | Single use exists (`invitation_consumed`). Sender is `created_by`. No notice |
| 3 | On account deletion, keep an anonymous record that an invite was sent and accepted, with no name or user id | Household | Not there. `created_by` and `accepted_by` are set to null on delete, so the count of people is lost |
| 4 | 10 beta invites per user for TestFlight, more at Lucas's discretion. The in-app code is the real gate. A TestFlight public link only installs the app. No code means the cuadrao.ai waitlist | Household | No quota, no code gate, no TestFlight link |
| 5 | Three network numbers from day one: invites sent per user, share of invites accepted, share of invitees who invite someone. Household invites are counted separately from beta invites, and each group link is its own source | Household | No event and no durable record |
| 6 | A comparison against a zero month shows the amount difference, not a percent. A month with confirmed complete coverage and no spending shows 0. "Sin datos" shows only when coverage is missing (clarified 10:18 PM CT) | Home | No series on the API. `financial-home` returns zero strings for a month with no records |
| 7 | A bill appears in Updates 3 days before its due date and on the due date | Updates | No inbox, no trigger |
| 8 | Updates go to the in-app inbox, plus push for people who turn it on. Push never shows amounts. No email for updates | Updates | No inbox, no push code |
| 9 | Joint-plan export waits until after TestFlight | None in this pass | The read-only departure archive from #773 stays |
| 10 | When a member leaves, their account goes with them. The household keeps that account's history up to the move, greyed out and read-only, with the state at the move recorded. Moves are idempotent events and never rewrite past balances or settlements. Home recomputes from history. Explicit per-role access rules in RLS and API checks | Account moves | Leave revokes grants and the household sees nothing afterward. No move command, no locked history |
| 11 (HoE) | Landing order: Household, account deletion, space list on its own, Search, Home series, account moves, Updates | All | Not applicable |
| 12 | Two kinds of invite. Any user sends beta invites from the quota in row 4. Only the household admin sends household invites. Those don't count against the 10, and accepting one also lets the person into the beta | Household | Household invitations exist and only the admin creates them. No beta invite and no quota |
| 13 | Lucas, and only Lucas, can create a group link: a multi-use beta invite with a cap he picks and an expiry date, redeemed atomically. Once the cap is reached, the link sends people to the cuadrao.ai waitlist and says so. Each link is its own source, and the who-invited-whom record shows the link as the inviter. It is the one exception to single use in row 2. It is beta-only and never grants household membership | Household | Nothing. Every invitation is single use |
| 14 | When an owner deletes their account, the household's locked copy of that owner's history is deleted too, and the other members see a short note that it was removed | Account deletion, with the trigger exception in account moves | No in-app deletion and no locked history |
| 15 | When the household admin deletes their account, the admin role passes automatically to the longest-standing remaining member. If no one is left, the household closes | Account deletion | No handoff. The admin transfers administration or closes the household by hand before leaving |
| 16 | Deleting any account also clears the person's email from saved feedback and deletes the person in PostHog by distinct id, including their events. The PostHog wording was clarified Oct 2 via #782 | Account deletion | The feedback row's `user_id` is set to null on delete and `context.account_email` stays. No PostHog deletion call |
| 17 | When a person deletes their account, their amounts in plans other people own keep their values and dates under a nameless "Exmiembro" placeholder ("Former member" in English), numbered when more than one. Their receipts, photos, and notes are deleted. Open balances with them are frozen as a closed line, not settled or forgiven, until a member marks them settled. Their future responsibilities go back to the plan's owner with an Update to reassign. Shared plans they owned, and the #773 archive, pass to the longest-standing participant, or are deleted if nobody else is in the plan | Account deletion | Nothing. A plain delete fails on the restricting keys. No placeholder, frozen balance, or plan ownership transfer |
| 18 | Sign-in for TestFlight is Apple, Google, and email. Email works with any address and has an in-app confirmation step. Apple and Google are built behind default-off flags until Lucas supplies the keys. Because the app offers Sign in with Apple, deleting an account revokes the person's Apple tokens. Deletion also revokes every Google token Argus holds (Yelena's call) | Sign-in (Yelena), and Account deletion for the Apple and Google revocation | Updated for `a8c37d3a`. Native Sign in with Apple and Google sign-in exist on iOS (#795, `ios/ArgusFoundation/Auth/NativeProviderSignIn.swift`) behind `ARGUS_APPLE_SIGN_IN_ENABLED` and `ARGUS_GOOGLE_SIGN_IN_ENABLED`, both `false` in `ios/Config/Development.xcconfig`, and the buttons stay hidden while a switch is off. Later Mac builds and candidate verification are recorded in the [current mobile roadmap](../argus-execution-board.md#current-mobile-roadmap-october-4-founder-lock); connected physical-device sign-in acceptance remains open under #784 and #800. The backend captures, stores and revokes Apple tokens (#793 and #802, `src/argus/api/apple_sign_in.py`, table `apple_sign_in_credentials`) behind `CUADRAO_APPLE_REVOCATION_CAPTURE_ENABLED`, `"false"` in `render.yaml`. Nothing is enabled: the founder still owes the Apple and Google keys, `[auth.external.apple]` in `supabase/config.toml` is still disabled, and the ship gates in #800 stand before either sign-in switch goes on. Email sign-up still ends on "Check your email" with a confirmation link (`auth.confirmation.detail`), so there is no in-app confirmation step yet |
| 19 (HoE) | A shared debt plan whose owner deletes their account is not handed over, because nobody can own another person's debt account. It is archived read-only under the deleted person's placeholder for the plan's household. Yelena confirmed it as an exception to decision 17's plan handover. Contributions keep their values and dates under "Exmiembro", and open balances show as a closed line. Participants see Iris's banner and get the usual member note | Account deletion | Nothing. `financial_debt_plans.debt_account_id` is keyed to the owner's own account with `(debt_account_id, user_id)`, so it cannot move to another person |

Head of Engineering delivery decisions that go with decision 10. These are not founder locks:

- Locked history is read-only for everyone, the owner included. The one exception is the account-deletion function from [Lane 6](#lane-6-account-deletion). Lane 2 owns that trigger exception.
- Account moves need a manual Codex review plus a dedicated eval before landing.
- A member, including the household admin, reads a departed member's locked history only if they had an explicit grant to that account at the cut-off.
- The departure event is written by the system when a member leaves or is removed, not by the admin or the member.

Head of Engineering delivery decisions for account deletion, also not founder locks:

- Account deletion is its own lane. It lands right after Household and before external TestFlight. Applying Apple's deletion rule to external TestFlight builds is Yelena's call: Apple reviews the first external TestFlight build against the App Review Guidelines, and in-app account deletion is one of them.
- Account deletion needs a manual Codex review plus its own eval before landing.
- Guest accounts are covered by the same deletion command.

Already locked before today and still in force: the [Household permission policy](household-permission-policy.md) of 1 October, except where decision 10 narrows what happens on departure and decision 15 replaces the admin's transfer-or-close step when the admin deletes their account. Also still in force: the MVEE visibility rules, and the rule that a plan stays in the space where it was created.

## Build environment and how iOS lands

The October 2 remote build box was Linux with no Swift and no Xcode. That team built backend, database and docs pieces without compiling iOS. Later Mac verification is recorded in the [current mobile roadmap](../argus-execution-board.md#current-mobile-roadmap-october-4-founder-lock). The process below applies when a lane has not yet received that verification.

iOS pieces still land. The rule is:

- Each lane's iOS work goes in its own small PR, separate from that lane's backend PR.
- The iOS PR is behind a default-off flag. Its body names the actual tested commit and Mac evidence, or says that Mac compilation is still pending.
- The captain lands it as **landed unverified, Mac pass by Lucas's local agent**.
- Lucas's local Mac agent builds and verifies the landed commit. If it needs a fix, it returns a fix PR, and this team takes that PR over and lands it.
- If an iOS PR breaks the build, revert only that PR. The backend PR stays.

Each lane below marks its iOS parts this way. None of them is described as blocked.

## Outside services: fakes behind default-off flags

Lucas supplies some outside pieces later. The wiring lands now. Each outside piece sits behind an adapter with a fake, and a flag that defaults off. Turning a piece on later is configuration plus the real adapter, not a rewrite.

Flag convention to follow: backend flags are `ARGUS_<SURFACE>_ENABLED`, read once and treated as on only for `1`, `true`, `yes`, or `on`, as `households_enabled()` in `src/argus/api/households.py` does. Unset means off, and an off surface answers `404` before auth. iOS flags are xcconfig keys copied into `Info.plist` and read with `Bundle.object(forInfoDictionaryKey:)`, as `ARGUS_AUTH_ENABLED` does in `ios/Config/Development.xcconfig`, `ios/Config/Info.plist`, and `ios/ArgusFoundation/Auth/NativeAuthConfiguration.swift`.

The flag names below are proposals, and the captain confirms the final name in the lane PR, except `ARGUS_APPLE_SIGN_IN_ENABLED` and `ARGUS_GOOGLE_SIGN_IN_ENABLED`, which are confirmed.

| Outside piece | Lucas supplies | Lands now | Flag or setting |
| --- | --- | --- | --- |
| cuadrao.ai universal link | AASA file on cuadrao.ai and the Associated Domains entitlement | Server link builder for `https://cuadrao.ai/...`, iOS link handling | `CUADRAO_INVITE_UNIVERSAL_LINK_ENABLED`, backend and iOS. Off keeps today's share link |
| TestFlight public link | The link itself | A setting the app reads and shows with the invite | `CUADRAO_TESTFLIGHT_PUBLIC_URL`. Unset means no install link is shown |
| Code gate and waitlist | The cuadrao.ai waitlist page | Code check and the redirect to the waitlist | `CUADRAO_BETA_INVITE_GATE_ENABLED` and `CUADRAO_WAITLIST_URL` |
| Push | APNs key | Device registration, a push sender interface, and a recording fake that keeps payloads for tests | `[removed obsolete setting]`. Off uses the fake and sends nothing |
| Email | A cuadrao.ai sending domain in Resend | Nothing. Household email delivery and update email are out of scope for this pass | None |
| PostHog person deletion | A PostHog personal API key that can delete persons. The project token the server sends events with cannot | A deletion adapter and a recording fake that keeps each request for tests | `ARGUS_ANALYTICS_DELETION_ENABLED`. Off uses the fake and sends nothing |
| Sign in with Apple | Sign in with Apple enabled on the app ID, a Services ID, and a .p8 key | Apple sign-in, the encrypted refresh-token store, and an Apple revocation adapter for Lane 6 | `ARGUS_APPLE_SIGN_IN_ENABLED` (confirmed). Off hides the button. The deletion step has no fake: without the Apple configuration a stored token's revoke stays pending (`apple_unconfigured`), as [Lane 6 step 2](#steps-in-order) says. An external TestFlight build with Apple or Google sign-in turned on requires `CUADRAO_ACCOUNT_DELETION_ENABLED` on. TODO: name the Apple key settings and the backend token-capture switch as #793 and #795 land them. At their current heads these are `CUADRAO_APPLE_TEAM_ID`, `CUADRAO_APPLE_SIGN_IN_KEY_ID`, `CUADRAO_APPLE_SIGN_IN_PRIVATE_KEY`, `CUADRAO_APPLE_BUNDLE_ID`, and `CUADRAO_APPLE_REVOCATION_CAPTURE_ENABLED` |
| Google sign-in | A Google sign-in client, with its own names. It is separate from `GOOGLE_OAUTH_CLIENT_ID` in `render.yaml`, which belongs to the Gmail source connection | Google sign-in behind its own flag | `ARGUS_GOOGLE_SIGN_IN_ENABLED` (confirmed). Off hides the button. Client settings: `GOOGLE_SIGN_IN_IOS_CLIENT_ID`, `GOOGLE_SIGN_IN_WEB_CLIENT_ID`, and `GOOGLE_SIGN_IN_IOS_URL_SCHEME` (#795). An external TestFlight build with Apple or Google sign-in turned on requires `CUADRAO_ACCOUNT_DELETION_ENABLED` on. |

Lane surfaces with no outside piece also start default-off, one flag each: `[removed obsolete setting]` for the space list, `[removed obsolete setting]` for moves, `CUADRAO_ACCOUNT_DELETION_ENABLED` for in-app deletion, `[removed obsolete setting]` for the series, and `[removed obsolete setting]` for the inbox. Search documents stay behind the existing `ARGUS_DOCUMENT_EXTRACTION_ENABLED`.

**Email.** Household email delivery is out of scope for this pass. A Resend adapter already exists: `send_resend_email` in `src/argus/domain/resend_email.py`, sending through Resend SMTP from `noreply@get-argus.com` with `CUADRAO_APPROVAL_EMAIL_SMTP_PASSWORD`. It is used by `src/argus/api/feedback_notification.py` and `src/argus/domain/access_approval_email.py`. What is missing is a cuadrao.ai sending domain. When Household email comes back, it reuses this adapter with that domain and does not add a second mail client.

**Push today.** No APNs, `UNUserNotificationCenter`, or device-push code exists under `src/` or `ios/`. `financial_shortcut_device_tokens` stores Shortcuts enrollment tokens for ingestion. It is not a push token table and is not reused for push. `reminders_opted_in` and `reminders_opted_out` in `src/argus/observability/analytics_events.py` are analytics events only.

**Universal link today.** No `CFBundleURLSchemes`, associated domain, `applinks:` entry, or `onOpenURL` handler exists under `ios/`. The string `cuadrao.ai` appears nowhere in code or config.

## Contracts between lanes

Household owns permission rules. Other lanes call that owner. They do not store a second grant, a second membership, or a client-side allow list.

Account moves own what a move does to history, plans, Home, and Search. The account id stays the same. Current assignment changes by `space_id`. Historical balances, corrections, and settlements are not rewritten and are not copied onto the destination. The move is an idempotent event. Budget and goal rows stay in the space where they were created. Their inclusion of the account's activity changes with `space_id`. Home and Search read the same `space_id` and recompute from canonical history. They do not keep a private copy of which space an account is in, and they do not keep a copied series.

The lane that causes an event writes its Updates entry, through the inbox model. Household writes the closure entry when the last member leaves. Lane 6 writes the admin handoff entry and the closure entry that a deletion causes, along with its member note, new-owner message, and reassign entry. The Updates lane owns only how entries are displayed and the push opt-in. (Yelena's rule, October 2.) An entry stores read state and a source link. It does not copy the amount, the draft, or the invitation token into the inbox row. Display text is read from the current source at open time, so a revoked grant, an approved draft, or a paid bill cannot leave a stale private fact in the inbox.

### Source link

This shape is a technical contract for these lanes. It reuses ids that already exist.

```json
{"kind":"account|activity|expectation|budget|goal|debt|bill|document|conversation|invitation","id":"<uuid>","household_id":"<uuid or null>"}
```

| `kind` | `id` is | Open with |
| --- | --- | --- |
| `account` | `financial_accounts.id` | Existing account detail |
| `activity` | Logical activity id, never a leg or an old revision | Existing activity detail |
| `expectation` | Personal expectation id | Existing Plan expectation editor |
| `budget`, `goal`, `debt` | That plan's id | The existing Search open path in `FinancialSearchModel.open` |
| `bill` | Shared plan id whose `PlanRef.kind` is `bill`, or a personal expectation whose kind is `bill` | The owner already used by Household plan detail or the personal expectation editor. `household_id` is set only for the shared plan |
| `document` | `connection_id` from `/api/v1/financial-documents` | `GET /api/v1/financial-documents/{connection_id}` and, for bytes, `GET /api/v1/financial-documents/{connection_id}/source` |
| `conversation` | `conversations.id`, the same id `GET /api/v1/search` returns as `SearchItem.conversation_id` | The existing conversation reader. There is no native conversation screen in the connected shell today. Chat on that shell is still `ChatSampleView` |
| `invitation` | `household_invitations.id` | Household. Used only for the inviter's "invitation accepted" row. The token is not part of the link |

`household_id` is null for a personal record. It is set only for a household-authorized projection. Opening the link rechecks current Household permission. Failure uses the same unavailable destination Search already shows. A document link never carries `source_bytes`, a storage object key, or a bucket path.

Personal financial search and conversation search stay separate HTTP APIs. `GET /api/v1/search` returns conversation dossiers. `GET /api/v1/financial-search` returns financial records. The client can show them in one list. The server does not merge those stores.

## Landing order

One integration captain lands one lane at a time onto `codex/private-alpha-next`. The captain reconciles the current integration into the worker branch by merge, never by rebase, then lands the worker through its PR. Each lane may land as a backend PR and a separate iOS PR.

1. **Household.** Universal link, code, QR, single-use code with sender, the anonymous invite record, the beta and household invite split, the 10-invite quota, the founder group link, code gate, and the three numbers. No email.
2. **Account deletion.** In-app deletion and its ordered server-side steps, in [Lane 6](#lane-6-account-deletion). Lands before external TestFlight. Manual Codex review and its own eval before landing.
3. **Space list on its own.** Space rows, unique names, archive, and a new account choosing a space. No move of an existing account. This is the one `space_id` writer later readers use.
4. **Search.** Document and conversation hits and opens, so Updates has real destinations.
5. **Home series.** Derived from canonical history, filtered by the account's current space, with decision 6 for comparisons.
6. **Account moves.** Leaving a household with locked history, and moving an account between spaces. Adds the trigger exception for the deletion function. Manual Codex review and the dedicated eval before landing.
7. **Updates.** Inbox, bill rows, draft-ready rows, the inviter's accepted notice, and opt-in push without amounts.

A lane does not wait on an outside piece Lucas supplies later. It lands with the fake and the flag off.

## Codex review

Codex review is not a merge gate except where this file says so. Request it for work that changes durable money, authorization, or schema.

| Lane | Review |
| --- | --- |
| Household | Yes. The code store, the anonymous record, the quota, and the group link cap are schema and authorization work |
| Account deletion | Required. A manual Codex review plus its own eval, both before landing |
| Spaces list | Yes. The space table is migration and authorization work |
| Search | Yes if a query can return another owner's document or conversation. No for a read-only adapter that calls the existing document and conversation owners and adds no table |
| Home | Yes if the series is a new stored table. No if it is derived inside the existing financial-home read from canonical activity and balance observations |
| Account moves | Required. A manual Codex review plus the dedicated eval in that lane, both before landing |
| Updates | Yes for the inbox table, its RLS, the device token table, and any trigger |

## Shared file ownership

| Files | Writer | Rule |
| --- | --- | --- |
| `ios/ArgusFoundation/Cuadrao/**`, `ios/DesignPreviewTests/**`, `ios/ArgusFoundationUITests/Cuadrao*Design*`, `ios/ArgusFoundationUITests/CuadraoHomeChartUITests.swift`, navigation icons, `.agent/designs/cuadrao/` | Design lane on `codex/cuadrao-design-scan-recents` | Do not edit. `CuadraoUpdatesCanvas.swift` exists only on that branch |
| `ios/ArgusFoundation/Connected/ConnectedCuadraoShell.swift`, `FoundationShell.swift`, `CuadraoNavigationBar.swift`, `AppDestination` | One native navigation writer, assigned by the captain for the landing that changes tabs or the bell | Other lanes add a destination handler beside these files and hand the wiring to that writer |
| `docs/API_CONTRACT.md`, `docs/api/openapi.yaml`, `ios/Packages/ArgusSession/Sources/ArgusSession/*.swift` public types | The lane that owns the contract, one landing at a time | Swift types match the contract. No second client model of money or permissions |
| `ios/ArgusFoundation/Resources/en.lproj/Localizable.strings` and `es-419.lproj/Localizable.strings` | Captain, at the landing | The design branch has already diverged both files. Lane PRs list new keys in the PR. They do not edit the strings files |
| `supabase/migrations/*.sql` | The domain owner, one new file per landing, version assigned by the captain | Latest on this tip is `20261003130000_financial_document_drafts.sql`. New files sort after it. Do not edit a migration that is already on integration |
| `ios/Config/*.xcconfig`, `ios/Config/Info.plist`, entitlements | Captain, at the iOS landing | New flags and the Associated Domains entry are added once, by the captain |
| `docs/specs/argus-execution-board.md` | Captain | Lane PRs do not rewrite historical landing records |
| `docs/specs/argus-decision-log.md` | Docs seat | Lane PRs link to it. They do not edit it |

## Still open

These are not founder locks yet. Each one blocks only the piece named. Everything else in this file can be built.

Lucas settled the earlier open items on 2 October. Whether a beta invite is the same as a household invite is now decisions 12 and 13. What happens to locked household history when the owner deletes their account is now decision 14, a founder lock rather than a delivery contract. What happens to a deleted person's part in other people's plans is decision 17. Sign in with Apple, formerly open item 2, is now decision 18: Apple, Google, and email ship for TestFlight, and Lane 6 revokes Apple tokens and every Google token Argus holds on deletion.

1. **How the code gate fits the existing access gate.** `CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED` and the `private_alpha_allowlist` table already decide who can sign up and sign in, and the [API contract](../../API_CONTRACT.md) says public registration has been open in production since 12 August 2026. Turning that flag off to gate the beta would also close web registration. The code gate gets its own flag and does not flip the existing one. The exact way a redeemed code admits a person is a technical design item in the Household PR, under Codex review.
2. **Web account deletion.** Closed by #801. The web deletion dialog in `web/components/sidebar/ProfileMenu.tsx` calls the [Lane 6](#lane-6-account-deletion) deletion command, and files the earlier `account_deletion_request` support ticket only while `CUADRAO_ACCOUNT_DELETION_ENABLED` is off. The paragraph after [Lane 6's steps](#steps-in-order) says what the code does today.
3. **Where the inbox model comes from.** Under the Updates ownership rule in [Contracts between lanes](#contracts-between-lanes), Household and Lane 6 write their own entries through the inbox model. No inbox table exists on integration yet. The only Updates code is the design preview's `CanvasUpdate` in `ios/ArgusFoundation/Cuadrao/CuadraoUpdatesCanvas.swift`, and Lane 5 lands last. Which PR adds the inbox table before Household and Lane 6 write to it is not settled.

## Next steps for Lucas

These are the pieces only Lucas can hand over. Each lane lands without them, with the fake and the flag off. Turning a piece on is a separate, explicit step after he supplies it.

1. **A cuadrao.ai sending domain in Resend.** The Resend adapter already exists and sends from `noreply@get-argus.com`. The domain is needed only when Household email comes back into scope. Nothing in this pass sends email.
2. **The cuadrao.ai universal link.** Host the `apple-app-site-association` file on cuadrao.ai and confirm the app's Team ID and bundle id for its `applinks` entry. The captain then adds the Associated Domains entitlement in the iOS PR. Until both exist, `CUADRAO_INVITE_UNIVERSAL_LINK_ENABLED` stays off.
3. **APNs key** for push. Until then `[removed obsolete setting]` stays off and the recording fake is used.
4. **The TestFlight public link.** Until then `CUADRAO_TESTFLIGHT_PUBLIC_URL` stays unset and no install link is shown.
5. **Schedule Apple's first external beta review.** Apple must approve the first build for external testing before the TestFlight public link works for outside testers. Put that review on the calendar before the first distribution.
6. **A PostHog personal API key that can delete persons.** Until then `ARGUS_ANALYTICS_DELETION_ENABLED` stays off, the recording fake is used, and account deletion reports the PostHog step as not done.
7. **Sign in with Apple keys.** Sign in with Apple enabled on the app ID, a Services ID, and a .p8 key. Until then Apple sign-in and token capture stay off, and Lane 6 keeps any stored token's revoke pending (`apple_unconfigured`), as [Lane 6 step 2](#steps-in-order) says.
8. **A Google sign-in client.** It has its own settings, separate from the Gmail source's `GOOGLE_OAUTH_CLIENT_ID`. Its settings are `GOOGLE_SIGN_IN_IOS_CLIENT_ID`, `GOOGLE_SIGN_IN_WEB_CLIENT_ID`, and `GOOGLE_SIGN_IN_IOS_URL_SCHEME` (#795). Until then Google sign-in stays off.

Also needed later, not secret: the cuadrao.ai waitlist page URL for `CUADRAO_WAITLIST_URL`. The waitlist page itself is not in this repository.

## Lane 1. Household invitations

**MVEE:** [section 12](../argus-minimum-viable-ecosystem-experience.md#12-household-collaboration-approved-minimum-capacity), invitation delivery, and the [permission policy](household-permission-policy.md). Board rows for #763, #766, and #773. Decisions 1 to 5, 12, and 13.

### Journey and completion

A registered admin creates a household and shares one invitation. It shows as a cuadrao.ai link, a short code, and a QR of that link. All three resolve to the same invitation. The recipient, on their own sign-in, opens the link, scans the QR, or types the code, previews, and accepts. They see no accounts until an owner shares one. The code works once. A second use fails with the existing `invitation_consumed` error. Revoke and expiry fail with the existing `invitation_revoked` and `invitation_expired` errors. The same acceptance retried with the same idempotency key does not create a second membership. The inviter later gets an "invitation accepted" row in Updates, once that lane lands.

The beta gate: any user can send a beta invite, and each user has 10 for TestFlight. Lucas can add more. Only the household admin sends household invites. They don't use any of the 10, and accepting one also lets the person into the beta. A person without a valid code who installs from the TestFlight public link is sent to the cuadrao.ai waitlist. The TestFlight link only installs the app.

The founder group link: Lucas, and only Lucas, can create a link that many people can use, with a cap he picks and an expiry date. It is the one stated exception to single-use codes. Redemption is atomic, so a burst of taps cannot go past the cap. Once the cap is reached, a person who opens the link lands on the cuadrao.ai waitlist and the screen says so. After the expiry date the link admits no one. Each group link is its own source in the network numbers, and the who-invited-whom record shows the link as the inviter, not a person. The group link is beta-only. Redeeming it never grants household membership.

Completion is the link, the code, and the QR against Postgres, English and Spanish, relaunch, and a third registered user who gets `404` for the household. It also covers a beta invite inside the quota, a household invite that lets the person into the beta without using the quota, and a group link that stops at its cap. No email is sent.

### What exists and is reused

| Piece | Where | Reuse |
| --- | --- | --- |
| Membership API | PR #763 `fbcc399b`. Flag `CUADRAO_HOUSEHOLDS_ENABLED` in `src/argus/api/households.py`. Routes in `src/argus/api/routers/households.py` | Reused as is. Code and QR are a presentation of the same invitation |
| Invitation table | `household_invitations` in `supabase/migrations/20261001090000_household_membership.sql`: `token_hash` unique, `created_by`, `expires_at`, `revoked_at`, `accepted_by`, `accepted_at`. `accepted_membership_id` added in `20261001120000_household_consent_recovery.sql` | Reused. `created_by` is the sender for decision 2 |
| Token | `secrets.token_urlsafe(32)`, stored as a hash, returned once. TTL seven days, `INVITE_TTL` in `src/argus/domain/household/repository.py` | Reused for the link. The token is too long to type, so the code is new |
| Single use | `accept_invitation` in `src/argus/domain/household/postgres.py` locks the household and the invitation row `for update`. `invitation_consumed`, `invitation_revoked`, `invitation_expired` in `errors.py` | Reused |
| Idempotent commands | `household_command_receipts` keyed by actor, operation, and idempotency key, in `20261001120000_household_consent_recovery.sql`, used by `src/argus/domain/household/commands.py` | Reused for code redemption and quota grants |
| Access rules | RLS is on for all four household tables. `20261001090000` defines `households_member_select`, `household_members_peer_select`, `household_invitations_admin_select`, and `household_account_grants_member_select` with `is_active_household_member`. `20261001120000` then revokes all client privileges on those tables, so only the API service reads and writes them | Same pattern for new tables: RLS on, client privileges revoked, service writes, API checks the role |
| Native share | `ShareLink` in `ios/ArgusFoundation/Household/HouseholdManagement.swift` shares `argus-household://invite#` plus the token and shows it at `household.invite.link`. Paste-to-preview at `household.invite.input`. `ios/ArgusFoundationUITests/HouseholdUITests.swift` expects the `argus-household://invite#` prefix | Kept while the universal-link flag is off |
| Existing access gate | `CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED` in `src/argus/api/guest_access.py`, the `private_alpha_allowlist` table, and `POST /api/v1/auth/access-requests` | See [Still open](#still-open) item 1. Not flipped by this lane |

Not there, on integration or on the design branch at `8f521518`: a household invite code, a household QR (the only QR is the plan-group sample in `CuadraoGroupCodeCard.swift` on the design branch, which says it joins no real group), a universal link, a quota, a durable who-invited-whom record, and any network event. The `cohort` string on `signed_in`, `session_started`, `landing_viewed`, and `first_answer_shown` in `src/argus/observability/analytics_events.py` is a campaign code. It is not a person and is not the referral record.

### What is new

- **Code.** A short human-typeable code for each invitation, stored only as a hash beside `token_hash`, unique while the invitation is live, single use except for the group link, with the same expiry and revoke rules. New migration.
- **Universal link.** The server builds `https://cuadrao.ai/invite#<secret>` when `CUADRAO_INVITE_UNIVERSAL_LINK_ENABLED` is on. The secret stays in the URL fragment, as today's link does, so it never reaches a web server log. Off keeps today's link.
- **QR.** The QR encodes the same link. It is drawn on the device. No QR image is stored.
- **Who-invited-whom record.** One row per invitation that records its kind (beta, household, or group link), send and accept, and the invitation that brought the sender in, if any. A group link records each redemption with the link as the inviter. Live sender and acceptor user ids are kept beside it and cleared on account deletion. The row itself keeps no name, email, or user id once that happens. That keeps decision 3: counts and the "invitee invited someone" chain survive, and the deleted person is gone. New migration.
- **Quota.** 10 beta invites per user for TestFlight, with a grant command Lucas uses to add more. A live or accepted beta invite uses one. An expired or revoked unused invite returns its slot, as the [API contract](../../API_CONTRACT.md#beta-invites-founder-group-link-and-code-gate) says. Household invites and group-link redemptions do not count against it. Since #788 it is counted from `beta_invitations` (`_quota` in `src/argus/domain/household/invites.py`), not from PostHog.
- **Founder group link.** One more kind of code, with a cap, an expiry date, and a source label, created only from Lucas's account. Redemption is atomic: the count and the cap are checked and updated in one locked step, so concurrent taps cannot pass the cap. Over the cap, the waitlist response. It lets the person into the beta and never creates a household membership. How Lucas's account is identified, and whether he creates the link from a screen or a server command, is a technical design item in the Household PR.
- **Code gate.** Behind `CUADRAO_BETA_INVITE_GATE_ENABLED`. With the gate on, a signed-in user who has not redeemed a beta invite, a household invite, or a group link gets the waitlist response, using `CUADRAO_WAITLIST_URL`.
- **Three numbers.** Invites sent per user, share accepted, and share of invitees who send an invite of their own. Household invites are counted separately from beta invites, and each group link is its own source. Computed in SQL from the who-invited-whom record. A PostHog event, if added, goes through the closed registry in `analytics_events.py` and carries no person id.

**Flags wait on issue #789.** #788 landed this lane's backend (`bf6ccf85`). Issue #789 (HMAC the codes with a server secret, and rate-limit preview, redeem, and household accept-by-code) must land before `CUADRAO_HOUSEHOLDS_ENABLED`, `CUADRAO_BETA_INVITES_ENABLED`, or `CUADRAO_BETA_INVITE_GATE_ENABLED` is turned on in any hosted environment. Household accept-by-code goes through `CUADRAO_HOUSEHOLDS_ENABLED`, which is why that flag waits too. All three are `false` in `.env.example`, and `CUADRAO_HOUSEHOLDS_ENABLED` is `false` in `render.yaml`.

### iOS parts: landed unverified, Mac pass by Lucas's local agent

- Code and QR screens beside the existing share link in `ios/ArgusFoundation/Household/`.
- Code entry on the recipient preview.
- Universal-link handling that routes `https://cuadrao.ai/invite#...` to the existing preview, behind the iOS flag. The Associated Domains entitlement waits for Lucas's AASA file (next step 2).
- Showing the TestFlight public link from `CUADRAO_TESTFLIGHT_PUBLIC_URL` and the waitlist hand-off.

### Allowed files

`src/argus/domain/household/`, `src/argus/api/routers/households.py`, `src/argus/api/households.py`, one new migration, `ios/ArgusFoundation/Household/`, `ios/Packages/ArgusSession/Sources/ArgusSession/Household.swift`, `tests/household/`, and the Household section of the API contract and OpenAPI when this lane is landing.

No-touch: grant semantics in `_end_membership` (account moves owns the departure change), `CuadraoHousehold*.swift`, `CuadraoGroupInvitation.swift`, `CuadraoGroupCodeCard.swift`, financial account ownership, Plan math, `resend_email.py`, and email templates.

### Acceptance

Backend, on this box: two real users and a third who is denied, against Postgres. Create, then preview and accept by link token and by code for the same invitation. A second use of the code fails with `invitation_consumed`. Revoke and expire fail with the existing errors. Retry a lost accept response and get one membership. The who-invited-whom row records sender and accept. Delete the acceptor's auth user, then the sender's: the counts and the chain are unchanged and no row holds either user id, name, or email. An eleventh beta invite beyond the quota is refused, and a grant from Lucas allows it. A household invite from the admin does not use the quota, and accepting it also passes the beta gate. A member who is not the admin cannot create a household invite. A group link requested by anyone other than Lucas is refused. A group link with a cap of N admits exactly N people under concurrent redemption, and the next person gets the waitlist response. An expired group link admits no one. Redeeming a group link creates no household membership. The numbers count household invites apart from beta invites and report each group link as its own source. With `CUADRAO_BETA_INVITE_GATE_ENABLED` on, a user without a code gets the waitlist response. With it off, behavior is today's. With `CUADRAO_HOUSEHOLDS_ENABLED` off, `404 households_unavailable` before auth. No email is sent.

iOS, by Lucas's local agent after landing: share, code, and QR show the same invitation in English and Spanish. Code entry and QR scan reach the existing preview. Relaunch both clients. With the universal-link flag off, the existing `HouseholdUITests` prefix test still passes.

## Lane 2. Spaces

**MVEE:** [Financial spaces](../argus-minimum-viable-ecosystem-experience.md#financial-spaces), [managing private spaces](../argus-minimum-viable-ecosystem-experience.md#managing-private-spaces), and [reassigning accounts](../argus-minimum-viable-ecosystem-experience.md#reassigning-accounts-between-spaces). Board row D04. Decisions 10 and 11, and the trigger exception for decision 14.

Spaces lands in two separate slots: the space list in slot 3, and account moves in slot 6. They are described together here because they share the table.

### Space list, slot 3

Personal already exists for every account because `space_id` defaults to `personal`. The person creates one named private Business space and one named Custom space. Names are unique among their spaces, including archived ones. A new account chooses a space. Archive keeps the records. Delete is only for an empty private space. Personal cannot be renamed, archived, or deleted. An archived space cannot be the source or the destination of a move. Unarchive it first. This slot ships one Business and one Custom space per user, archive, and restore. It does not ship a purge job or an unlimited entitlement. It does not move an existing account.

### Account moves, slot 6

Two kinds of move, both under decision 10.

**Leaving a household.** When a member leaves or is removed, the accounts they own go with them, as today. That includes an account they had shared with the household: it moves with its owner. New: a server-side function runs when a member leaves or is removed. It writes the departure event, keyed for idempotency, and records the cut-off before grants are revoked. Neither the admin nor the member writes move events directly. The cut-off is the account, each grant that existed at that moment, and the exact activity and balance revisions those grants could see. The household keeps a locked, read-only, greyed-out copy only for the members who had an explicit grant to that account at the cut-off. Nobody gets locked history they could not see at the cut-off. That keeps rule 3 of the 1 October policy: an account is visible only through an explicit grant. Nobody can create, edit, or delete locked history, including the owner and the admin. The only exception is the account-deletion function, below. The owner keeps editing their own account. A later correction to an old record is a new revision in the owner's history and does not change the household's locked view.

**Account deletion.** Account deletion is its own lane, [Lane 6](#lane-6-account-deletion), and lands in slot 2, before this slot. This slot keeps only the trigger exception. The trigger that blocks update and delete on locked history and move events lets that deletion function, and nothing else, remove the deleting user's move events and the household's locked copy of their history (decision 14). Because the locked history table is created in this slot, this slot also adds that removal to step 5.4 of the deletion function. The deletion function writes no move events.

**Moving between spaces.** The person moves a standalone account from Personal to Business. Standalone means the account has no transfer, payment, cross-account refund, or loan link to another account, and no unfinished document draft. Only a standalone account can be moved. The account id is unchanged. Opening balance, activity, corrections, and notes still load. No new transaction appears. A budget that included the account stops including it in Personal and the budget row does not move. A goal or debt plan linked to the account still opens and points at the same account id. Household grants on that account are unchanged. An account that is not standalone cannot be moved, and the screen explains the link.

### Move invariants

- Do not rewrite historical balances, opening balances, corrections, or settlements. Do not copy them onto the destination.
- Each move is an event: account id, kind (`space_move` or `departure`), source, destination, actor, time, and an idempotency key. The owner creates space moves through the move command. Departure events come only from the system departure function. The Lane 6 account-deletion function writes no events. It only removes the deleted user's own move events and the household's locked copy of their history, in its step 5.4. The account id does not change. `space_id` is the current assignment only.
- The same idempotency key replayed is a no-op that returns the first result. A failed move leaves one end state, source or destination, with history intact.
- Home series and comparisons are recomputed from canonical history. They are not a snapshot copied onto the new space.
- Locked household history pins revisions. It never references a revision written after the cut-off.

### Access rules per role

New tables follow the household pattern: RLS on, all client privileges revoked, and the API checks the role on every route. Locked history and move events are append-only, and the service role gets select only on them, with insert revoked. Only three functions write them: the system departure function inserts departure events and the locked copy, the owner's move command inserts space-move events, and the account-deletion function from Lane 6 removes the deleting user's rows and the household's locked copy of their history. The writers are SECURITY DEFINER functions in the `argus_private` schema, owned by `postgres` and executable only by `service_role`, and each sets a transaction-local `argus.locked_history_writer` value (`departure`, `space_move`, or `deletion`) with `set_config(..., true)` before it writes; the trigger allows a write only when `current_user = 'postgres'` and that value permits the operation, the same pattern `argus.owner_transfer` uses in `20260724211312_guest_workspace_handoffs.sql` and `20260726185021_harden_guest_lifecycle_ownership.sql`. The departure function may write only `departure` events, and the move command only `space_move` events. The deletion function writes no events: its `deletion` writer value permits only the step 5.4 removal of the deleted user's own move events and the household's locked copy of their history. The trigger rejects an event whose kind does not match the writer value, and any insert under the `deletion` value. All three functions declare `set search_path = ''` and schema-qualify every name they use. The user id a writer acts for comes only from the API's verified JWT, and the API passes it in. A null `auth.uid()` never counts as ownership, and no writer falls back to it. Yelena (Head of Engineering) approved the move command as the third writer on October 2. That is a delivery call, not a founder lock. The trigger rejects every update, and every insert or delete that does not come from those functions, for every role, ordinary service-role writes included, because the service role bypasses RLS. Nothing else can add, change, or remove them.

| Role | Move events | Locked household history | Live account |
| --- | --- | --- | --- |
| Account owner | Create own space moves through the move command. Read own. No departure events | Read. No create, edit, or delete. Removed only by the account-deletion function | Full owner rights, unchanged |
| Household admin | Read departure events for the household. Never writes them | Read only if the admin had an explicit grant to that account at the cut-off. Otherwise none. No create, edit, or delete | Only what a live grant allows |
| Member who had an explicit grant at the cut-off | None. Never writes them | Read. No create, edit, or delete | None after departure |
| Member with no grant at the cut-off | None | None | None |
| Anyone else | None, `404` | None, `404` | None |
| System departure function, SECURITY DEFINER, `set search_path = ''` | Insert the departure event once per idempotency key. Writes `departure` events only | Insert at the cut-off only | None |
| Move command function, SECURITY DEFINER, `set search_path = ''` | Insert the owner's space move once per idempotency key, after checking that the user owns the account. The user id comes only from the API's verified JWT, which the API passes in. A null `auth.uid()` never counts as ownership. Writes `space_move` events only | None | None |
| Account-deletion function from Lane 6, SECURITY DEFINER, `set search_path = ''` | Remove the deleted user's own move events, in step 5.4 only. Writes no events | Remove the household's locked copy of that user's history, in step 5.4 only | Remove that user's rows |
| Other service-role writes | Select only. No insert, update, or delete | Select only. No insert, update, or delete | Existing writes |

Reused: `financial_accounts_owner_select`, `financial_records_owner_select`, and `financial_record_revisions_owner_select` in `supabase/migrations/20260928200000_financial_accounts_first_slice.sql`; `is_active_household_member` and `household_account_grants_member_select` in `20261001090000_household_membership.sql`; the client-privilege revoke in `20261001120000_household_consent_recovery.sql`; `household_command_receipts` for idempotency; and the revision-pinning pattern of `household_plan_archived_activities` in `20261002020000_shared_plan_retained_revision_scope.sql`, which already pins exact activity revisions when a shared plan's owner departs.

### Reconciliation cases the lane must test

- Opening balance and later corrections stay the same rows and revisions. The move does not write a new opening balance.
- Recorded activity amounts and dates are unchanged. A month with missing coverage stays no data, and a covered month with no spending stays a known zero.
- A settlement between two accounts, including a transfer or a payment, is not rewritten. Moving one account in a linked pair is blocked, and both histories stay put. The same block covers a cross-account refund, a loan link, and an unfinished document draft.
- Backfill after the move: a correction or an activity dated before the move appends to canonical history. It does not create a destination copy, does not rewrite the pre-move revision, and does not change locked household history.
- Repeating the same move with the same key is a no-op: one event, one assignment.
- An interrupted move retries to the same end state. Never in both spaces, and history is never half-copied.
- Home series and the comparison read after the move match a fresh computation from canonical history for the destination space.
- Household grants, budget rows, and goal rows keep their ids.
- After a departure, an update or delete on locked history fails for the owner, the admin, and ordinary service-role writes.
- A stray service-role insert into locked history or move events, outside the departure function, the move command, and the deletion function, fails. This includes a direct insert of a move event. The move command rejects a caller who does not own the account, and rejects a call with no verified user id even when `auth.uid()` is null. A writer that inserts an event of another kind, such as the departure function writing `space_move`, fails. Any insert under the `deletion` writer value fails.
- After a departure, a member or admin who had no grant to the account at the cut-off reads no locked history for it.
- Replaying the departure with the same key writes no second event and no second cut-off.
- The account-deletion function, in its step 5.4, removes the deleted owner's own move events and the household's locked copy of their history, and nothing else here. It writes no event. The Lane 6 eval covers the rest of the deletion.
- A move from or to an archived space is rejected.

### Dedicated eval

The move needs a manual Codex review and a dedicated eval before landing. The eval runs the cases above against Postgres. It fails if any historical balance, correction, or settlement row changes, if a move event is missing or duplicated, if a service-role insert outside the departure function and the move command succeeds, if the account-deletion function inserts any event or removes anything other than the deleted user's own move events and locked copy, if locked history can be changed by anyone other than the account-deletion function, if anyone reads locked history they could not see at the cut-off, or if the Home series differs from a fresh read of canonical history.

### What exists and is reused

| Piece | Where |
| --- | --- |
| Column | `financial_accounts.space_id text not null default 'personal'` in `supabase/migrations/20260928200000_financial_accounts_first_slice.sql`. The [first-slice spec](financial-accounts-first-slice.md) says no route reads or writes it |
| Domain | `PERSONAL_SPACE = "personal"` in `src/argus/domain/recording/accounts.py`. `AccountFacts` has no space field. Household grants must not rewrite `space_id` |
| Departure today | `_end_membership` in `src/argus/domain/household/postgres.py` revokes grants in both directions in the same transaction as `left_at`. Remaining members then see nothing of the leaver's accounts. Plans the leaver shared become the archived read-only projection from #773 |
| Canvas | `CuadraoSpacesPreview.swift`, `CuadraoSpacesSheet.swift`, `CuadraoSpaceSelector.swift` on the design branch. In-memory spaces. No move action |

### What is new

- A space table owned by the user, with the account's `space_id` pointing at it. Personal is the default row and cannot be deleted. Slot 3.
- A move command, written as a SECURITY DEFINER function, a move event table, the link check, and the budget-inclusion update. Slot 6.
- The locked household history table, the system departure function that records the cut-off before grants are revoked, and the trigger exception that lets the Lane 6 deletion function remove the locked copy. Slot 6. The API contract and data model departure paragraphs change in the same PR, because today they say remaining members lose access.

### iOS parts: landed unverified, Mac pass by Lucas's local agent

- Space picker on new-account entry and the space list screens. Slot 3.
- Move review and blocked-link explanation on Manage account. Slot 6.
- Greyed-out, read-only rendering of locked household history. Slot 6.

### Allowed files

`src/argus/domain/recording/accounts.py` and the account repository that writes `financial_accounts`, a new space module beside it, `src/argus/api/routers/financial_accounts.py`, `src/argus/domain/household/postgres.py` and `repository.py` for the departure cut-off only, one new migration per slot, the account and Household departure sections of the API contract and data model when landing, and the account and household tests.

Budget inclusion changes go through the existing budget reader, which already filters by `account_ids`. Spaces does not fork budget math.

No-touch: `CuadraoSpaces*.swift`, document storage, the chart canvas.

### Acceptance

Slot 3: Postgres. Create Business and Custom, relaunch, and see the same names. A second user cannot list the spaces. Delete is rejected while the space has an account. Personal delete and rename are rejected. `ARGUS_FINANCIAL_ACCOUNTS_ENABLED` off still `404`s the new routes, and the new space flag off does too.

Slot 6: the reconciliation cases and the eval pass. Move a standalone account, relaunch, and read the same activity on the same account id in the new space. A linked transfer blocks the move and leaves every row in place. After a departure, members who had a grant at the cut-off read the locked history greyed out and cannot change it. Members without one see nothing of it. iOS screens are checked in English and Spanish by Lucas's local agent after landing.

## Lane 3. Search coverage

**MVEE:** [Search](../argus-minimum-viable-ecosystem-experience.md#search-find-what-i-already-know). Board lane for #751. Documents are the #776 contract. Conversations stay on `GET /api/v1/search`.

### Journey and completion

The person searches from the connected Search tab. Existing results still open account, activity, expectation, budget, goal, and debt detail, and Back returns to the same query, filters, and scroll origin. A saved document and an existing conversation also appear. Opening the document loads it from the document API and shows the draft, not a filename with only Delete. Opening the conversation loads that conversation. A document or conversation owned by someone else is absent. A household member does not find another member's private document or chat. Relaunch restores the search origin and refetches.

### What exists and is reused

| Piece | Where | PR |
| --- | --- | --- |
| Financial search | `GET /api/v1/financial-search`. `src/argus/domain/financial_search.py` kinds `account`, `activity`, `expectation`, `budget`, `goal`, `debt`. Native `FinancialSearch.swift`, `FinancialSearchModel.swift`, `FinancialSearchView.swift` | #751, then #753, #755, #757 for the later kinds |
| Household financial search | `GET /api/v1/households/{id}/search`. Hit shape in `financial_schemas.SearchHit`, with `plan_ref` for shared plans | #766, #773 |
| Conversation search | `GET /api/v1/search` in `src/argus/api/routers/search.py`. Items are `type: conversation` with `conversation_id` | Existing Omnisearch, not the iPhone financial tab |
| Documents | `src/argus/api/routers/financial_documents.py`. List, get, source download, proposal patch. `require_document_surface` in `src/argus/api/documents.py` requires the ingestion gate and `ARGUS_DOCUMENT_EXTRACTION_ENABLED`, which defaults off. Bytes in `financial_document_extractions.source_bytes` via `src/argus/domain/ingestion/documents/store_postgres.py` | #776 |
| Design Search chrome | `CuadraoSearchCanvas.swift` has sample sections for plans, chats, files, and memory | Design canvas |

Reuse `financial_search.search` for financial rows, the document service's list and get for documents, and `GET /api/v1/search` for conversations. [Issue #778](https://github.com/lagarcess/argus/issues/778) plans to move retained document source bytes into a private Supabase Storage bucket before documents are enabled. Search uses the document API and never storage internals, so that move does not affect Search.

### What is new

- Document and conversation hits in the connected Search results, through the existing owners. Documents stay behind `ARGUS_DOCUMENT_EXTRACTION_ENABLED`.
- Household search keeps omitting documents and chats. No document-sharing grant exists, and this lane does not invent one.

### iOS parts: landed unverified, Mac pass by Lucas's local agent

- Document and conversation rows and their open paths in `FinancialSearchModel.open`. The assistant tab is still `ChatSampleView`, so the conversation open needs a reader destination the navigation writer adds.

### Allowed files

`src/argus/domain/financial_search.py`, `src/argus/api/routers/financial_search.py`, the connected search Swift files named above, `ArgusSession` search types, and the connected financial Search section of the API contract when this lane is landing. Conversation hits call the existing search reader. They do not copy its SQL.

No-touch: `store_postgres.py` except a bugfix the document owner makes, `CuadraoSearchCanvas.swift`, interpreter prompts, `GET /api/v1/search` ranking.

### Acceptance

Backend: Postgres with one saved document and one conversation for user A, and the same kinds for user B. A finds only A's rows. B's queries do not include A's ids. A household member without a document grant does not see the other member's draft. Document flag off: financial search still returns the existing kinds and returns no document hits. No test reads `source_bytes` from the Search package.

iOS, by Lucas's local agent: A opens the document through the document API and the conversation through its id. Back restores the query. Relaunch refetches. English and Spanish filters once the captain adds the strings.

## Lane 4. Home series

**MVEE:** [Home](../argus-minimum-viable-ecosystem-experience.md#home-understand-where-i-stand), populated summary, and [charts](../argus-minimum-viable-ecosystem-experience.md#13-complete-scope-checklist) row D05. Decision 6.

### Journey and completion

A signed-in person opens Home in Personal, then in a private space once the space list has landed. The balance chart and the activity insights use that space's recorded accounts and activity, one currency at a time. A month with confirmed complete coverage and no spending is a known zero and shows 0. A month whose coverage is missing is no data, "Sin datos". It is not a zero balance and not zero spending. A comparison against a known-zero month shows the amount difference, not a percent. A comparison with a no-data month is not shown. Unknown balances stay out of the known total. The person can open the account or activity behind a point. Relaunch shows the same series. Household Home includes only accounts that live grants allow, plus locked history after slot 6, and drops an account the moment its grant is revoked.

Completion is a real Postgres read, an app relaunch, a second user who cannot see the first user's series, and the same screen in English and Spanish. The design canvas sample series is not completion.

### What exists and is reused

| Piece | Where | PR |
| --- | --- | --- |
| Connected Home position, one reporting month, five recent activities, and the Plan forecast | `GET /api/v1/financial-home` and `GET /api/v1/financial-plan`. Built by `home_response` in `src/argus/domain/recording/loop_reads.py`. Month window is `period` in `src/argus/domain/recording/money_home.py` | #745, #747, #749 |
| Connected Cuadrao Home | `ios/ArgusFoundation/Connected/ConnectedCuadraoHome.swift` renders text, accounts, coming up, and recent activity. It does not construct `CuadraoHomeBalanceChart` or `CuadraoHomeInsights` | #760 |
| Chart and insight chrome, sample data | `CuadraoHomeOverview.swift`, `CuadraoHomeInsights.swift`, `CuadraoHomeBalanceChart.swift`, `CuadraoBalanceHistory.swift`, `CuadraoSpendingHistory.swift`, `CuadraoSpendingStory.swift`. `CanvasBalanceHistory.examples` and `CanvasSpendingHistory.examples` invent history | #775, #777, design canvas |

Reuse `home_response`, `spending`, and the Plan forecast. Do not add a second balance.

Today `home_response` returns zero minor-unit spending strings for a currency that has accounts and no expenses in the month, whether or not that month is covered. Under decision 6 the series shows 0 only when coverage is confirmed complete, and "Sin datos" when it is missing. Those strings are the current-month totals, not a series, and must not be copied into the chart. In the design preview, `CanvasSpendingStory` already shows a covered empty period as `.emptyPeriod` and an uncovered one as `.unavailable`. Its `previousEntries`, though, still drops a covered prior period with no records as a comparison baseline, citing #787. That is known-zero work owned by Lucas's #790, which changes it to the known-zero rule. The connected path must not show a percent change against a zero month.

### What is new

- A multi-month balance and spending series on the API, derived from canonical account observations and current logical activity, filtered by current `space_id`. Behind a default-off flag. Each month is marked as having records or not.
- The comparison rule of decision 6 in that series, with each month marked as covered or not.

### iOS parts: landed unverified, Mac pass by Lucas's local agent

- Binding the connected Home to the chart and insight views with the API series, instead of `CanvasBalanceHistory.examples`. This waits until the captain can touch `ConnectedCuadraoHome.swift` without colliding with the design branch, which also edits the chart files.

### Allowed files

`src/argus/domain/recording/loop_reads.py`, `money_home.py`, a new series module next to them, `src/argus/api/routers/financial_loop.py`, the financial-home section of `docs/API_CONTRACT.md` and `docs/api/openapi.yaml` when this lane is landing, and the tests that already cover `home_response`.

No-touch: `ios/ArgusFoundation/Cuadrao/**`, design preview tests, and `ConnectedCuadraoHome.swift` while the design branch still differs on it. Household grant tables. Plan definition tables.

### Acceptance

Backend: Postgres. An account with an unknown balance does not become zero. A month with missing coverage is no data, not the current zero string. A covered month with no spending shows 0. A previous known-zero month gives an amount difference and no percent. A no-data month gives no comparison. Household series hides an account the moment its grant is revoked. `ARGUS_FINANCIAL_ACCOUNTS_ENABLED` unset still returns `404` on the financial routes.

iOS, by Lucas's local agent: relaunch reads the same points. English and Spanish strings for no data and for the amount comparison.

## Lane 5. Updates

**MVEE:** [Updates](../argus-minimum-viable-ecosystem-experience.md#updates-tell-me-when-something-deserves-attention). Decisions 2, 7, and 8. The broader MVEE list, including budget thresholds, goal milestones, and scheduled summaries, stays on the board. This lane does not close it.

### Journey and completion

The person taps the bell and sees a persistent inbox. Rows in this pass:

- **Bill.** A personal or shared bill makes one row 3 days before its due date and one on the due date. Each row is written once per bill, due date, and offset, so a rerun does not duplicate it.
- **Draft ready.** A document whose status becomes `review_ready`.
- **Invitation accepted.** The inviter gets a row when someone accepts their invitation. There is no "invitation received" row, because an invitation has no named recipient before acceptance.

The row says what happened and opens the source through the source link. Opening marks it read. Read state survives relaunch. Another user does not see the row. After a grant is revoked, a household row disappears or opens as unavailable. Amounts, when the source still has them, appear only inside this signed-in inbox.

A person who turns on push also gets a push for each new row. A push never contains an amount, a balance, a merchant, or a document name. It says something needs a look and opens the app. There is no email for updates.

### What exists and is reused

- Connected shell: `ConnectedCuadraoHome` calls `showUpdates`, and `ConnectedCuadraoShell` presents `FoundationSheet.updates`.
- `FoundationSheets.swift` renders a sample page. Copy key `sheet.updates.detail` says delivery is not connected, in `en` and `es-419`.
- Bill facts: personal expectations of kind `bill`, and shared plans of kind `bill`, already have dates.
- Draft facts: document `status` includes `review_ready`, behind `ARGUS_DOCUMENT_EXTRACTION_ENABLED`, default off. PR #776.
- Invitation facts: `household_invitations.accepted_at` and the sender from lane 1.
- `conversation_read_states` is chat read state. It is not this inbox and is not reused.
- No push code exists. See [Outside services](#outside-services-fakes-behind-default-off-flags).

### What is new

- How entries are displayed: the inbox screen's rows, read state, and opening through the source link.
- Under the Updates ownership rule in [Contracts between lanes](#contracts-between-lanes), each row is written by the lane that causes it, idempotent per source and offset: bill reminders by the Plan service, which owns due dates, draft-ready rows by the document service, and invitation-accepted rows by Household. Yelena confirmed these three writers. Which PR adds the inbox table is [Still open](#still-open) item 3.
- Device-token registration for push, a push sender interface, and the recording fake. `[removed obsolete setting]` off uses the fake. The real APNs sender waits for the key.

### iOS parts: landed unverified, Mac pass by Lucas's local agent

- The inbox screen behind the bell, through the navigation writer. `CuadraoUpdatesCanvas.swift` stays on the design branch.
- The push opt-in prompt, device-token registration, and opening the app from a push.

### Allowed files

A new Updates package under `src/argus/domain/` and one router, a new migration assigned by the captain, `FoundationSheets.swift` only through the navigation writer, and tests that create a bill, a document draft, and an accepted invitation and then read the inbox as that user and as someone else.

The document service keeps owning draft status. The Plan service keeps owning due dates. The Household service keeps owning invitations. Each writes its own entry. Updates does not add a status column to their rows.

No-touch: `CuadraoUpdatesCanvas.swift`, `source_bytes`, invitation token storage, `resend_email.py`.

### Acceptance

Backend: Postgres. A bill due in 3 days makes one row, and the due date makes a second. Running the trigger again adds nothing. A draft reaching `review_ready` makes one row. An accepted invitation makes one row for the inviter only. Mark one read and read it back as read. A second user gets an empty inbox. Revoke a household grant and the related row is gone or unavailable. A document row's open path uses `connection_id`. With the document flag off, no draft row appears and the document routes still `404`. Every payload the push fake records has no amount. No email is sent.

iOS, by Lucas's local agent: relaunch shows the same unread and read rows. English and Spanish for the inbox and the push text. Push opt-in off sends nothing.

## Lane 6. Account deletion

**Decisions:** founder locks 3, 14, 15, 16, 17, and 18, and Apple's in-app account-deletion rule (App Review Guideline 5.1.1(v)). The Head of Engineering (Yelena) made these delivery calls, which are not founder locks: deletion as its own lane, its place in the landing order, applying Apple's deletion rule to external TestFlight builds, decision 19 for shared debt plans, confirmed as an exception to decision 17's handover, the Updates ownership rule, revoking every Google token at deletion, and the placeholder design for the census in #791, revised after Priya's review. It lands in slot 2, right after Household and before external TestFlight. An external TestFlight build with Apple or Google sign-in turned on requires `CUADRAO_ACCOUNT_DELETION_ENABLED` on. Internal TestFlight is not blocked by it. Guest accounts are covered by the same deletion command.

### Journey and completion

A signed-in person opens Delete account in the app, sees what will be deleted, and confirms. The server runs the steps below in order. When it finishes, the app signs out and that account can no longer sign in. If the person was a household admin, the admin role has passed to the longest-standing remaining member, or the household has closed if no one is left. The other members see a short note that a member deleted their account, without naming them. In plans other people own, the person's amounts stay under a nameless former-member placeholder, and any open balance with them shows as a closed line. Shared plans they created pass to the longest-standing participant in each, as live plans that person can edit, and that person gets a message saying so. A shared debt plan they created is the exception: it is archived read-only with a banner (decision 19). The anonymous invite record and the network counts stay. The wording is in [Copy](#copy-founder-locked-iriss-wording).

Completion is a real deletion against Postgres of a user who has their own plans, a part in a plan another member owns, a household membership as admin, a membership as a member, a Gmail or Plaid connection, a document, an accepted invite, and saved feedback. Nothing that identifies them is left, and the other members' balances are unchanged.

### What exists today

This is the state before Lane 6 landed, kept as the lane's starting point. Since #791, #799 and #801, the deletion command, the route and the web flow are on integration behind `CUADRAO_ACCOUNT_DELETION_ENABLED`, which is off; the [API contract](../../API_CONTRACT.md#post-accountdelete) and the [launch runbook](../../PRIVATE_LAUNCH_RUNBOOK.md#account-deletion-runs-lane-6) describe what landed.

- Deletion is a support request. `account_deletion_request` on `POST /api/v1/feedback`, in `src/argus/api/routers/feedback.py`, saves a feedback row with the account email and the user id in its context and emails `support@get-argus.com`. There is no in-app deletion function. `delete_auth_user` in `src/argus/domain/supabase_guest_accounts.py` is used only for guest cleanup.
- A plain delete of the auth user would fail for anyone who has ever made a plan. In `supabase/migrations/20261002000000_shared_household_planning.sql`, `financial_plan_definition_revisions.owner_id` and `actor_id` and `household_plan_receipts.actor_id` reference `auth.users` with `on delete restrict`. `household_members.user_id` cascades from `auth.users`, but `household_plan_bindings`, `household_plan_participants`, `financial_plan_responsibilities`, `household_plan_receipts`, and the `contributor_membership_id` columns on `financial_plan_links` and `financial_goal_allocations` reference that membership row with `on delete restrict`. In `20261002020000_shared_plan_retained_revision_scope.sql`, `household_plan_bindings.first_shared_revision` and `household_plan_archived_activities`, the #773 archive, also restrict. This comes from reading the migrations. The full list is in the [census](account-deletion-fk-census.md), landed with #791 as `1de71a6d`, linked from [Foreign keys and user-id columns](#foreign-keys-and-user-id-columns). A real deletion test against Postgres comes first in this lane.
- When a member leaves, `retain_membership` in `src/argus/domain/household/planning_retention.py` pins their contributions to plans other people own into `household_plan_archived_claims` and `household_plan_archived_allocations`, against exact activity and allocation revisions. The `retain_foreign_activity` trigger in `20261002010000_shared_money_original_leg_owners.sql` refuses to delete an activity group while it holds a leg recorded by another owner.
- Where a delete does go through, it skips other domains. `financial_source_connections` cascades, so the stored credential is dropped without revoking access at Google or Plaid. `household_invitations.created_by` and `accepted_by` are set to null. The feedback row's `user_id` is set to null and the email in its context stays. PostHog events stay under the person's distinct id.
- `disconnect` in `src/argus/domain/ingestion/hub.py` revokes at Google and Plaid and is idempotent. If revocation fails, it reports `provider_revocation: failed` and deletes the local credential anyway, so nothing is left to retry with.
- The PostHog distinct id comes from `actor_hash_for_user` in `src/argus/observability/product_events.py`: a SHA-256 of the user id with a fixed prefix, not a secret salt. Events are sent with `$process_person_profile` set to false in `src/argus/observability/envelope.py`, so there may be no person record in PostHog for that distinct id.

### Steps, in order

1. **Admin handoff, plan handover, then household leave.** For each of the person's households, in this order:
   1. If the person is the household admin, the admin role passes to the longest-standing remaining member, or the household closes if no one is left (decision 15). Lane 6 writes the admin handoff entry, or the closure entry, to Updates. Household writes the closure entry only when the last member leaves on their own. Longest-standing means the earliest `joined_at` on `household_members`, and a tie goes to the lowest membership id. The tie-break is deterministic but arbitrary: it always picks the same person, but nobody chose that person.
   2. Each shared plan the person owns that has another participant passes to that plan's longest-standing participant (decision 17), who gets the new-owner message. A shared debt plan is never handed over. It stays with the person until step 5.2 archives it (decision 19). This runs before the leave rules. The plan's binding, definition, and owner-keyed rows move to the new owner's user id and membership, and the plan stays live and editable, with the same name. It gets no `departed_at`, and it is not turned into the #773 read-only archive. The new owner can edit it as soon as the run finishes. Shared plans with no other participant are not handed over. Step 5.2 deletes them.
   3. Then the existing leave rules run for the membership. Grants are revoked, and `retain_membership` pins the person's contributions to plans other people own, including the plans just handed over. The leave archive, `departed_at` and the #773 read-only archive, never applies to a plan handed over in step 1.2, because the person no longer owns it when the leave runs.
2. **Revoke every connected source.** Revoke Gmail and Plaid at the provider for each source connection, and delete the credential only after the provider confirms. If a revocation fails, the run keeps a pending revocation for that source, with the encrypted credential it needs, and retries it. The encrypted credential is kept only while that revocation is pending, and it is deleted when the revocation succeeds. It is not deleted silently while the revocation is still owed, as `disconnect` does today. The pending revocation is held in the run record, not in the person's connection row, so it survives step 7. The run does not report done while a revocation is pending.

   **Sign-in providers (decision 18).** If the person signed in with Apple, the run also revokes their Apple tokens through Apple's REST API. The sign-in work captures the Apple refresh token at sign-in and stores it encrypted with the account. Lane 6 calls the revoke. The run keeps that token in the pending revocation only while the revoke is pending, and deletes it when the revoke succeeds, the same rule as the source credentials above. Until Lucas supplies the Apple keys, capture stays off and no token is stored; a process without the Apple configuration keeps a stored token's revoke pending (`apple_unconfigured`) and never skips it. #793 stores the token in `apple_sign_in_credentials`, whose `user_id` references `auth.users` with `on delete restrict`. Lane 6 moves the token into the pending revocation and deletes that row before step 7. The census lists that table.

   The run revokes every Google token Argus holds for the person, Gmail source tokens included, under the same pending-revocation rule (Yelena's call). Native Google sign-in exchanges an ID token through Supabase Auth and stores no Google refresh token, so there is nothing to revoke for it.
3. **Delete Storage files.** After #778 moves document bytes into a private Supabase Storage bucket, delete each of the person's Storage objects. A database cascade does not remove them. Until #778 lands, document bytes are database rows and go with the person's rows.
4. **Clear invite ids and keep the anonymous record.** Clear the live sender and acceptor ids (`sender_user_id`, `acceptor_user_id`) on `invite_referrals` from #788, and keep the anonymous row, so the counts and the invite chain survive (decision 3). This is an explicit step. It does not rely on `on delete set null`. Two more parts:
   - Rotate the deleted sender's `invite_referrals.sender_ref`: write a distinct new value on each of their rows, so no two of their sent invites share a `sender_ref`. Deleting the `invite_sender_refs` mapping row alone, which cascades, would leave one shared `sender_ref` on all of them. The `inviter_origin_id` chain stays as it is (decision 3), so rotation ends only the grouping by `sender_ref`. This keeps decision 3's "no identifier". As a result the deleted sender's invites can no longer be counted per user, and that is intended. The comment in `20261003140000_household_invite_codes_and_beta_access.sql` still says "invites sent per user" stays countable after a deletion. Landed migrations are immutable, so that comment stays; Lane 6's own migration, `20261004090000_account_deletion.sql`, records the correction in its header.
   - Revoke the deleted sender's unused beta invites: set `revoked_at` on their `beta_invitations` rows of kind `beta` with `use_count = 0` that are still live, so no one can redeem them afterward.

   Both run through one Household-owned function (decided Oct 2), as in the [census](account-deletion-fk-census.md): `argus_private.forget_invite_party`. It ships in Lane 6's migration, but Household owns its rules and its tests (`tests/test_household_forget_invite_party_postgres.py`); Yelena signed off as Household owner on Oct 3.
5. **Shared plans and protected plan history (decision 17, founder lock at 8:53 PM CT).** In this order:
   1. **Plans other people own.** The person's amounts keep their values and dates under a nameless placeholder: "Exmiembro" in Spanish and "Former member" in English, numbered "Exmiembro 1", "Exmiembro 2" ("Former member 1", "Former member 2") when more than one person has left that plan. The placeholder has no name, avatar, or email, and no id tied to the person. There is one placeholder per household or [standalone shared group](account-deletion-fk-census.md#sharing-scopes-and-the-standalone-shared-group) and departed person. Every shared plan sits in a household, because `household_plan_bindings.household_id` is `not null`. The person's kept rows are re-keyed to the placeholder of their household (see the engineering note). The "Exmiembro" numbering stays per plan, because it is only a label. Their receipts, photos, and free-text notes on those amounts are deleted. Amount, date, and category stay. Open balances with them are frozen: not marked settled and not forgiven. They come out of the active totals and show as a closed line. A member can later mark that line settled, which is recorded as a new event. Their future responsibilities go back to the plan's owner, who gets an Update to reassign or re-split them. Past legs stay as they are.

      **An activity two households claim (decision c, Lucas, Oct 3).** One of the person's activities can be claimed by plans in two households (for example, a claim archived when they left one household and a live claim in another). It goes with the household whose claim is oldest: by claim `created_at`, then claim id; an archived claim counts by `claim_created_at`, and an archived activity ranks last. That household's placeholder gets the activity. The other household's claims and archives on it are re-pointed to the same placeholder as read-only references that still resolve, the person's personal claims on it are deleted, and the run counts them as `cross_scope_references`. Priya to confirm.
   2. **Shared plans they owned.** Each one with another participant was already handed over in step 1.2, so its new owner has a live, editable plan with the same name. Here the function deletes only the shared plans where nobody else is a participant, with their bindings and revisions. A #773 archive left by an earlier departure passes as it is, still read-only, to the longest-standing participant of that plan. That archive's participants are the ones not revoked at its departure. With none, the archived binding is deleted. The deletion never creates a new archive, except for a debt plan.

      **Shared debt plans (decision 19).** A shared debt plan the person owns is not handed over and not deleted. It is archived read-only under the person's placeholder for the plan's household, because nobody can own another person's debt account. This is an exception to the handover in decision 17, confirmed by Yelena. Contributions keep their values and dates under "Exmiembro", and open balances show as a closed line, as in step 5.1. Participants see the banner in [Copy](#copy-founder-locked-iriss-wording) item 4 on the archived plan, and they get the usual member note. Nothing else changes for them.
   3. **Their own remaining plans.** Delete the person's personal plan definitions and their `financial_plan_definition_revisions`, explicitly, inside this function.
   4. **Locked copy.** Once account moves has landed, also remove the household's locked copy of the person's history and the person's own move events (decision 14), under the trigger exception in Lane 2. This is the only thing the `deletion` writer value permits on those tables. The function writes no move event.

   The other members then see the note in [Copy](#copy-founder-locked-iriss-wording).

   **Engineering note, not a product decision.** The design for this step is in the lane PR, under Codex review. It has to cover:
   - Every entry in the [census](account-deletion-fk-census.md), landed with #791 (see [Foreign keys and user-id columns](#foreign-keys-and-user-id-columns)), with the action it lists.
   - **Placeholder users (Yelena's call, after Priya failed the first #791 design).** Lane 6 creates one nameless, banned `auth.users` placeholder per household or [standalone shared group](account-deletion-fk-census.md#sharing-scopes-and-the-standalone-shared-group) and departed person. It holds no id tied to the person. A household is one scope: every plan and every membership-keyed row in that household re-keys to that household's single placeholder, because its members already knew it was one person. Every shared plan sits in a household, because `household_plan_bindings.household_id` is `not null`. A placeholder owns rows in one household or group only. Under decision (c) above, another household's claims and archives on an activity can name that placeholder as a reference, but they stay that household's rows, so it owns nothing there. The "Exmiembro" numbering stays per plan. Decision 17 says the placeholder has no user id. It is implemented as "no id tied to the person", because the foreign keys require a real `auth.users` row. The person's kept rows in that household, and the placeholder membership they point at, are re-keyed to that placeholder. They are not nulled, because nulling breaks the composite keys and `validate_shared_allocation_binding` in `20261002000000_shared_household_planning.sql`. A placeholder is created and deleted only through the Supabase Admin API, with no direct DML on `auth.users`. It is permanently banned, and the API rejects its JWTs. The run record keeps the mapping from the person's real ids to their placeholders only while a run is in flight, so a resumed run reuses the same placeholders, and it scrubs that mapping when the run completes. This is how the placeholder gets past `retain_foreign_activity`, which refuses to delete an activity group that holds another owner's leg, and past the `on delete restrict` references to the person's `household_members` row.
   - The activity, record, and allocation revisions that other people's plans still reference move to the placeholder of the referencing plan's household. Those references are composite keys that include the owner's user id (`activity_owner_id`, `record_owner_id`, `account_owner_id`, `goal_owner_id`), so the revisions cannot simply be deleted, and acceptance says no row may hold the person's user id afterward. For an archived debt plan, `financial_debt_plans.debt_account_id` cascades from the owner's account through `(debt_account_id, user_id)`, so the debt plan and the owner's debt account both re-key to the placeholder of the plan's household.
   - `financial_asset_changes.recorded_by` needs only an assertion, not a clear: its `check (recorded_by = user_id)` in `20260930230000_connected_personal_assets.sql`, plus the cascade from its account, already remove it with the person's rows.
   - The rows `retain_membership` pinned in `household_plan_archived_claims` and `household_plan_archived_allocations`, and the activity and allocation revisions they pin, which stay as the placeholder's amounts.
   - Moving ownership of a shared plan in step 1.2, and an existing #773 archive in `household_plan_archived_activities` in step 5.2, to the new owner across the owner-keyed columns, including `household_plan_bindings.owner_user_id` and `owner_membership_id` and the `first_shared_revision` reference from `20261002020000_shared_plan_retained_revision_scope.sql`.
   - Where receipts, photos, and notes attached to those amounts are stored, so they can be deleted while amount, date, and category stay.
   - "Longest-standing participant" for a plan. Lane 6 adds `joined_at` to `household_plan_participants`. It is backfilled from `recorded_at` on the plan definition revision named by the row's `granted_revision`. That column is `not null`, but it has no foreign key to the revision row (`20261002020000_shared_plan_retained_revision_scope.sql` adds it with only a `> 0` check), so the backfill checks that every row resolves to a revision. A re-grant resets seniority: when the participant list is saved, `planning_store.py` keeps `granted_revision` only for people who were still active participants, and a person who was removed and later added again gets the revision of that save. Rows that existed before `20261002020000_shared_plan_retained_revision_scope.sql` had `granted_revision` backfilled from the plan's `first_shared_revision`, so those participants tie on the same time. A tie goes to the lowest membership id, which matters for those older rows. This rule is deterministic but arbitrary: it always picks the same person, but nobody chose that person.
   - Lane 6 writes its own Updates entries through the inbox model, under the rule in [Contracts between lanes](#contracts-between-lanes): the admin handoff and closure entries from step 1, the reassign entry, the member note, the new-owner message, and the debt-plan banner. Updates lands later, in slot 7, and owns only how they are displayed and the push opt-in. The inbox table's origin is [Still open](#still-open) item 3.
6. **Clear the email from feedback.** Clear the account email and the user id from the context of the person's saved feedback rows. This runs before the auth user is deleted, because `feedback.user_id` is set to null at that point and the rows could then only be found by the email itself. The copy already emailed to support through Resend cannot be cleared by this function.
7. **Delete the auth user.** This runs after the steps above, so no restricting row blocks it.
8. **PostHog cleanup.** Delete the person in PostHog by distinct id, including their events (decision 16, wording clarified Oct 2 via #782). Person profiles are off, so there may be no person record for that distinct id. The lane PR shows which PostHog call deletes the events in that case and records the response. Until a real deletion adapter ships, this goes to the recording fake, which counts as done only in tests and local dev: anywhere else the step stays pending, so the Lane 6 flag stays off until #806 lands.

The whole run is idempotent and can resume after a partial failure. A retry continues from the first step that did not finish. The run record is keyed by a hash of the user id. While a run is in flight it also keeps the mapping from the person's real ids to their placeholders, one per household or group, the PostHog distinct id, and any pending revocation, Apple's and Google's included. When the run completes it drops all of them, the user id and both hashes included (both are unsalted hashes of the id), and keeps only its own random id, the step outcomes and the counts. A run in flight is resumed by the person's own retry or by the operator-run resume sweep (`scripts/ops/resume_account_deletions.py` inside scheduled_maintenance); no cron runs it until Lucas decides on a schedule. A third-party step pending for 7 days alerts an operator, and only an operator can force-complete it, with a reason kept in the run record.

**Ship gates (Lucas, Oct 3).** Two issues block turning on `CUADRAO_ACCOUNT_DELETION_ENABLED`: #805, decision 17's frozen closed-line balance and its settle event, which #799 does not build; and #806, a real PostHog deletion adapter.

Web is on the deletion command since #801: the deletion dialog in `web/components/sidebar/ProfileMenu.tsx` calls `POST /api/v1/account/delete` through `web/lib/account-deletion-api.ts`. While `CUADRAO_ACCOUNT_DELETION_ENABLED` is off the route answers `404`, and the web then files the earlier `type: "account_deletion_request"` support ticket through `POST /api/v1/feedback`, so that type is still accepted (Marcus's #801 review, S4), and the dialog says a support request was sent, not that the account was deleted. This fallback is the agreed behaviour (Lucas, October 4): `account_deletion_request` stays accepted while the flag is off, and is retired only once the flag is on everywhere and a later change removes the fallback. Guest accounts go through the same command; `delete_auth_user` in `src/argus/api/routers/auth.py` still removes the auth user when a guest session fails to start.

### Foreign keys and user-id columns

Superseded by the [census](account-deletion-fk-census.md), which landed on integration with [#791](https://github.com/lagarcess/argus/pull/791) as `1de71a6d`. It is the authoritative list of every foreign key and direct user-id column a deleted user touches, with its delete action and what Lane 6 does with it, taken from a real-Postgres census. This file does not repeat it.

The Lane 6 PR opens with a real-Postgres test that deletes a user who has a row behind every entry in that census. That test comes before any deletion code. The census test landed with #791 and runs in CI's real-Postgres matrix (`guest-release-gates`).

### What is new

- An in-app deletion route on the API, behind `CUADRAO_ACCOUNT_DELETION_ENABLED`. The route name and whether it asks the person to sign in again are confirmed in the lane PR.
- The ordered deletion function and its run record, keyed by a hash of the user id, with pending revocations.
- A revocation path for deletion that keeps the credential until the provider confirms, including the Apple token revoke, and the revoke of every Google token held.
- The placeholder users, one per household or [standalone shared group](account-deletion-fk-census.md#sharing-scopes-and-the-standalone-shared-group) and departed person: their creation and deletion through the Supabase Admin API, the permanent ban, the API check that rejects their JWTs, and the in-flight id mapping in the run record that is scrubbed on completion.
- The `sender_ref` rotation and the revoke of unused beta invites in step 4, in one Household-owned function.
- The read-only archive of a shared debt plan with its banner.
- The former-member placeholder, the frozen balance line with its settle event, the reassign Update for the plan owner, and plan ownership transfer, with the migration they need.
- The admin handoff on deletion, inside the Household owner.
- A PostHog deletion adapter with a recording fake, behind `ARGUS_ANALYTICS_DELETION_ENABLED`. See [Outside services](#outside-services-fakes-behind-default-off-flags).
- The note the other members see, and the admin handoff and closure entries, written through the inbox model.
- Moving web onto the deletion command, with `account_deletion_request` kept as its flag-off fallback. The paragraph after [the steps](#steps-in-order) says when that fallback is retired.

### iOS parts: landed unverified, Mac pass by Lucas's local agent

- A Delete account row and a confirmation screen that names what will be deleted. It goes on whichever profile screen is on integration when this lane lands.
- After deletion, the app signs out and clears what it keeps on the phone for that user.

### Allowed files

A new deletion module under `src/argus/domain/` and one router, `src/argus/domain/household/` for the admin handoff, the leave call, the former-member placeholder, frozen balances, and plan ownership transfer, `src/argus/domain/ingestion/hub.py` for the deletion revocation path only, the Apple token store from the sign-in work for reading and deleting the token only, `src/argus/domain/household/invites.py` for the step 4 invite changes only, `src/argus/observability/` for the PostHog deletion adapter, the feedback router, schema, and store for clearing the email, and, in the PR that moves web onto the deletion command, `web/components/sidebar/ProfileMenu.tsx`, `web/lib/argus-api.ts`, and their web tests, one new migration, the account and Household deletion sections of the API contract and data model when this lane is landing, the iOS profile row and confirmation screen, and the tests for all of these.

No-touch: what `disconnect` does for an ordinary disconnect, `resend_email.py`, invitation token storage, Plan math, and the design branch files.

### Acceptance

Backend, on this box, against Postgres. Delete a user who:

- owns a plan shared with two other participants, with a #773 archive from an earlier departure, and owns a second shared plan where nobody else is a participant,
- has amounts with a receipt, a photo, and a note, an open balance, a future responsibility, and a leg in a shared activity, in a plan another member owns,
- is admin of one household with two other members and a member of a second household,
- owns a shared debt plan with another participant,
- has a Gmail or Plaid connection on the provider fake, signed in with Apple on the Apple fake, has a document, an invite they sent and one they accepted, an unused live beta invite, and saved feedback that includes an account-deletion request.

After deletion:

- No row holds their user id or name, and the completed run record holds neither the id nor any hash of it, with the id-to-placeholder mapping scrubbed.
- The other members' balances are unchanged.
- In the plan another member owns, their amounts remain with the same values, dates, and categories under "Exmiembro" ("Former member" in English). Their receipts, photos, and notes are gone.
- The open balance with them is frozen, out of the active totals, and shown as a closed line. Marking it settled records a new event.
- Their future responsibility is back with the plan's owner, and the owner got the reassign Update. Past legs are unchanged.
- A second deleted participant in the same plan shows as "Exmiembro 2".
- The plan they owned with other participants, and its #773 archive, now belong to the longest-standing participant, with the same plan name. That person got the new-owner message. The plan where they were the only participant is deleted.
- The other members got the note. For a member with no open balance with the deleted person, the note has only its first two sentences and never shows a zero amount.
- The first household's admin is the remaining member with the earliest join time, with the lowest membership id breaking a tie. A household where they were the only member is closed.
- The provider fake recorded a revocation for each source. With the fake set to fail one revocation, the run keeps a pending revocation with its credential, retries it, and does not report done until it succeeds.
- The who-invited-whom counts and chain are unchanged and hold no id. Their `sender_ref` was rotated to a distinct new value on each row, so no two of their sent invites share one. The `inviter_origin_id` chain is unchanged. Their unused beta invite is revoked and cannot be redeemed.
- The Apple fake recorded a revoke of their token. The stored token is gone after the revoke succeeds, and is kept while the fake fails.
- The provider fake recorded a revoke for every Google token Argus held for them, the Gmail source token included. A person who signed in with Google through an ID token had no Google refresh token stored, so nothing else was revoked for that sign-in.
- Their shared debt plan is archived read-only under the placeholder of its household, with the same values, dates, and closed balance line. The debt plan and their debt account are both re-keyed to that placeholder. Its participant sees the banner and the member note. It was not handed over.
- Each placeholder is a nameless, banned `auth.users` row with no id tied to the person, one per household or [standalone shared group](account-deletion-fk-census.md#sharing-scopes-and-the-standalone-shared-group) and departed person, and the API rejects a JWT for it. All of the person's rows in one household, across every plan in it, point at that household's single placeholder. A placeholder owns rows in one household or group only; another household may hold a read-only reference to it under decision c.
- Their feedback rows hold no email or user id.
- The PostHog fake recorded a deletion for their distinct id with events included.
- The new owner of a handed-over plan can edit it right after the run. It has no `departed_at` and no #773 archive from this deletion.
- With `CUADRAO_ACCOUNT_DELETION_ENABLED` on, web deletion uses the deletion command. With it off, the web files the `account_deletion_request` support request, the API accepts it, and the dialog says a support request was sent, not that the account was deleted. Retiring that fallback is a later change, described after [the steps](#steps-in-order).
- A guest account is deleted by the same command.
- Replaying the deletion changes nothing. Stopping the run after any step and retrying reaches the same end state.
- With `CUADRAO_ACCOUNT_DELETION_ENABLED` off, the route answers `404` before auth.
- After #778, no Storage object of theirs remains. After account moves lands, the Lane 6 eval also checks that the locked copy and the person's own move events are removed, that no move event was written, and that no other person's move events or locked history changed.

iOS, by Lucas's local agent: the row and the confirmation in English and Spanish, with the copy below. Deletion ends signed out, and relaunch does not restore the deleted session.

### Copy (founder-locked, Iris's wording)

Lucas locked this wording with decision 17. The English labels and the banner in item 4 were added to the locked copy later on October 2. Iris amended the last sentence of item 1 for decision 19. `{plan}`, `{monto}`, and `{amount}` are placeholders. Lane PRs list the keys. The captain adds them to the strings files.

**1. Deletion confirmation screen.** This block is added to the existing confirmation, beside the general text that everything is deleted and the admin and owner lines. It does not replace them.

- ES: "En los planes que compartes, tus montos se quedan para que las cuentas de los demás sigan cuadrando, pero sin tu nombre: aparecerás como «Exmiembro». Tus recibos y notas se borran. Lo que debes o te deben queda cerrado en la app, no marcado como pagado. Los planes que creaste pasan a la persona que lleva más tiempo en cada uno, salvo los planes de deuda compartidos, que se cierran y quedan solo para consulta."
- EN: "In plans you share, your amounts stay so everyone else's numbers still add up, but without your name: you'll show as "Former member." Your receipts and notes are deleted. Anything you owe or are owed is closed in the app, not marked as paid. Plans you created pass to whoever has been in each one longest, except shared debt plans, which are closed and stay view-only."

**2. Note other members see.** It does not name the person, on purpose.

- ES: "Un miembro eliminó su cuenta. Sus montos en «{plan}» siguen como «Exmiembro», así que tus saldos no cambian. El saldo pendiente con esa persona quedó cerrado ({monto}). Si ya lo resolvieron fuera de la app, puedes marcarlo como saldado."
- EN: "A member deleted their account. Their amounts in "{plan}" stay as "Former member," so your balances don't change. The open balance with them is closed ({amount}). If you settled it outside the app, you can mark it as settled."

Rule: when the reader has no open balance with that person, drop the third and fourth sentences, so the app never shows a zero amount such as "($0)".

**3. Message to the new plan owner.**

- ES: "Ahora administras «{plan}». Quien lo creó eliminó su cuenta."
- EN: "You now manage "{plan}." The person who created it deleted their account."

**Related labels.**

- Placeholder: "Exmiembro" in Spanish and "Former member" in English. "Exmiembro 1", "Exmiembro 2" when more than one person leaves a plan.
- Frozen balance line, ES: "Saldo con Exmiembro: $X (cerrado)". EN: "Balance with Former member: $X (closed)".
- Action, ES: "Marcar como saldado". EN: "Mark as settled".

**4. Banner on a debt plan archived after its owner deletes their account (decision 19).** Participants still get the usual member note, and nothing else changes.

- ES: "Este plan de deuda se cerró porque quien lo creó eliminó su cuenta. Puedes consultarlo, pero ya no se puede editar."
- EN: "This debt plan was closed because the person who created it deleted their account. You can still view it, but it can't be edited."

Manual Codex review plus this eval, both before landing.

## Lane status

| Lane | Backend can be built and tested here now | iOS: landed unverified, Mac pass by Lucas's local agent | Waits on |
| --- | --- | --- | --- |
| Household | Backend landed in #788 (`bf6ccf85`): code, who-invited-whom record, anonymous record on deletion, link builder, the beta and household invite split, quota, founder group link, gate, the three numbers | Code and QR screens, code entry, universal-link handling, TestFlight link and waitlist hand-off | Issue #789 before `CUADRAO_HOUSEHOLDS_ENABLED` or either beta flag turns on in a hosted environment. Lucas's AASA file before the link flag turns on |
| Account deletion | Deletion route, the ordered steps, admin handoff, provider, Google, and Apple revocation with pending retries, placeholder users per household or group, former-member placeholder, frozen balances, plan ownership transfer, debt-plan archive, invite cleanup, feedback cleanup, PostHog fake, eval | Delete account row, confirmation screen with the founder-locked copy, sign-out after deletion | Landed default-off: the census (#791), the command (#799), the route and web flow (#801). `CUADRAO_ACCOUNT_DELETION_ENABLED` stays off until #805 and #806 close. #778 for the Storage step. Lucas's Apple keys before the real Apple revoke turns on. A PostHog personal API key for #806. An external TestFlight build with Apple or Google sign-in turned on requires `CUADRAO_ACCOUNT_DELETION_ENABLED` on. |
| Space list | Space table and routes | Space picker and space list | Nothing |
| Search | Document and conversation hits | Rows and open paths | Nothing. Issue #778 does not block it |
| Home series | Series and the decision 6 comparison | Binding the connected Home to the series | The design-branch collision on `ConnectedCuadraoHome.swift` for the iOS binding |
| Account moves | Move command, events, locked history, RLS, eval | Move review and greyed-out locked history | The Home series reader, then manual Codex review and the eval. Linked moves stay blocked |
| Updates | How entries are displayed, read state, device tokens, push fake. The other lanes write the entries | Inbox screen, push opt-in and handling | Lucas's APNs key before the push flag turns on |

No lane is dispatched by this document.
