# DATA_MODEL.md

## Argus Data Model Source of Truth (Alpha MVP)

**Status:** Active
**Audience:** Backend engineers, database agents, API agents, frontend agents
**Purpose:** Define existing entities, relationships, ownership rules, and persistence contracts. The [MVEE](specs/argus-minimum-viable-ecosystem-experience.md) owns the approved experience; its financial records and household permissions still need explicit schema and access-control design.

---

# 1. Data Model Philosophy

The existing model supports conversational finance and historical simulations.
It must preserve:

- multi-chat conversations
- persistent user preferences
- AI-generated titles/names
- legacy saved strategies (read compatibility only)
- legacy strategy collections (read compatibility only)
- reproducible backtest runs
- symbol-level and aggregate metrics
- soft deletion and archive behavior
- future expansion without schema churn

The database should make the Alpha experience reliable, not overly complex.

---

# 2. Source of Truth

Supabase Postgres is the canonical state store.

Supabase owns:

- private-alpha access allowlist
- private-alpha access-welcome claims and delivery evidence
- user profiles
- preferences
- conversations
- messages
- strategies
- collections
- backtest jobs
- backtest runs
- feedback
- telemetry-ready product state

Render/FastAPI owns orchestration and compute, not long-term state. Render
Workflows own temporary backtest execution, but job lifecycle and result truth
remain in Supabase.

---

## Cuadrao record design principles

These principles guide assigned financial and business schema work. Existing
entity contracts below remain the implementation reference; this section adds
no table, role or retention exception.

- Each durable fact has one record owner. Screens and tools derive views from
  that owner rather than maintain independent financial truth.
- Financial values use exact decimal or integer minor-unit arithmetic with
  explicit precision and rounding. Preserve original amounts, currency and
  provenance. Apply the [product currency rule](specs/argus-minimum-viable-ecosystem-experience.md#currency-rule).
- Accepted corrections remain distinguishable from extraction output. Reprocessing
  cannot silently overwrite a user's correction. Keep the source, accepted
  revision and resulting record connected during their permitted lifetime.
- Processing a document does not discard its evidence. Retention remains subject
  to [account deletion](#account-deletion-lane-6) and the applicable approved policy.
  Business retention exceptions remain open; source preservation is not a promise
  of indefinite storage.
- Commercial, fiscal, payment and settlement events represent different facts.
  A document marked fiscally accepted does not prove payment. A net deposit and
  its fee must not create another sale. Assigned business contracts must define
  these states and their evidence before implementation.

The quality guide's [partial-payment example](research/cuadrao-constitution-2026-10-04/QUALITY-SOURCE.md)
is a future business acceptance case. It does not require consumer launch to
include invoicing or payment-provider integration.

# 3. Core Entities

Alpha MVP requires these primary entities:

```text
private_alpha_allowlist
private_alpha_access_welcome_claims
private_alpha_access_welcome_deliveries
profiles
conversations
messages
chat_turn_lifecycles
strategies                         # legacy read compatibility; no new writes
collections                        # legacy read compatibility; no new writes
collection_strategies               # legacy read compatibility; no new writes
backtest_jobs
backtest_runs
ideas
idea_versions
evidence_artifacts
decision_notes
cost_ledger_entries
feedback
usage_counters
```

Incubation-only, with no API/runtime/UI consumer:
```text
memory_settings
memory_candidates
memory_consent_actions
memory_records
memory_provenance
memory_prompt_history
memory_reconciliations
memory_provider_projections
memory_provider_cleanup
```

Default-off, registered-only (`ARGUS_FINANCIAL_ACCOUNTS_ENABLED`):
```text
financial_accounts
financial_records
financial_record_revisions
financial_account_idempotency
```

Default-off, registered-only (`ARGUS_HOUSEHOLDS_ENABLED`):
```text
households
household_members
household_invitations
household_account_grants
```

Default-off, registered-only (`ARGUS_BETA_INVITES_ENABLED`; household
invitations also write the record):
```text
beta_invitations
invite_referrals
invite_sender_refs
beta_admissions
argus_private.invite_code_digests
beta_invite_quota_grants
```

Default-off, registered-only (`ARGUS_INGESTION_ENABLED`):
```text
financial_source_connections
financial_source_gmail_senders
financial_shortcut_device_tokens
financial_import_events
financial_import_observations
financial_import_account_links
```

Default-off, service-role only (`ARGUS_WHATSAPP_INTAKE_ENABLED`):
```text
whatsapp_link_codes
whatsapp_sender_links
whatsapp_inbound_messages
```

Optional or later:
```
- assets
- telemetry_events
- deleted_items view
- archived_items view
```

---
# 4. Entity Relationship Overview

```
auth.users
   └── profiles
private_alpha_allowlist
   ├── private_alpha_access_welcome_claims      # logical email identity, no FK
   └── private_alpha_access_welcome_deliveries  # logical email identity, no FK
profiles
   ├── conversations
   │      ├── messages
   │      │      └── decision_notes             # decisions on computed answers
   │      ├── chat_turn_lifecycles
   │      ├── backtest_jobs
   │      └── backtest_runs
   │
   ├── ideas
   │      ├── idea_versions
   │      │      └── evidence_artifacts
   │      └── decision_notes
   │
   ├── strategies
   │      ├── backtest_runs
   │      └── collection_strategies
   │
   ├── collections
   │      └── collection_strategies
   │
   ├── cost_ledger_entries
   │
   ├── usage_counters
   └── feedback
```

---

# 5. profiles

Represents the application-facing user profile. Supabase Auth owns identity and session, while the Argus `profiles` table owns product-specific preferences.

### Fields
- `id`: `uuid` (Primary Key, references `auth.users.id`)
- `email`: `text` (Nullable only for a verified anonymous Auth user)
- `username`: `text` (Unique, Nullable)
- `display_name`: `text` (Nullable)
- `preferred_name`: `text` (Nullable; 1 to 40 characters when present)
- `language`: `text` (Default: `'en'`)
- `locale`: `text` (Default: `'en-US'`)
- `avatar_theme`: `avatar_theme` enum (Default: `'ocean'`; one of `ocean`,
  `plum`, `teal`, `ember`, `gold`, `indigo`, or `slate`)
- `country`: `text` (Nullable; an ISO 3166-1 alpha-2 code when present)
- `currency_override`: `text` (Nullable; an ISO 4217 code when present)
- `is_admin`: `boolean` (Default: `false`)
- `onboarding`: `jsonb` (legacy/inert; the applied migration defaults new rows
  to the historical shape below)
- `created_at`: `timestamptz`
- `updated_at`: `timestamptz`

### Legacy Onboarding Shape (inert compatibility state)

The explicit onboarding flow is removed. This column persists only because
existing rows carry it and removing it would be a destructive migration. No
product behavior reads it, and no API path writes it.

```json
{
  "completed": false,
  "stage": "language_selection",
  "language_confirmed": false,
  "primary_goal": null
}
```

### Constraints & Notes
- **Supported Languages**: `en`, `es-419`
- **Supported Locales**: `en-US`, `es-419`
- Private-alpha signup persists `language` and its server-derived `locale` in
  the profile creation path. Browser detection is only a pre-auth hint; after
  authentication this row is authoritative and no frontend repair update is
  required.
- `display_name` is an identity field. It is what the account is called.
- `name_initialization_closed` is an internal monotonic boolean for the Apple
  first-authorization display-name command. Existing rows start closed; a new
  unnamed row starts open. Inserted names, successful initialization and any
  explicit update of either name column close it, including NULL clears and
  same-value writes. Database triggers prevent reopening, including privileged
  updates, and prevent a named insert from claiming open eligibility. Unrelated
  partial profile updates do not close it. It stores no second name value,
  appears in no API response and grants no new client column access. It never
  permits the initializer to write `preferred_name`.
- `preferred_name` is what Argus calls the user when it addresses them, and
  it is deliberately separate from `display_name`: people fill an identity
  field with a legal name. It is optional, and null means surfaces use no
  name. It is stated in settings and never inferred from conversation, so no
  runtime path writes it. A registered-account preference: restrictive
  policies read the trusted `is_anonymous` JWT claim to keep it off the guest
  surface, because anonymous Auth users share the `authenticated` role.
- `country` is where the user lives. It is chosen in Settings and never
  inferred from conversation, IP or behavior (decision 8). Research sends it
  as the reader's location, and a user with no country sends no location.
- `currency_override` is a currency the user chose over the one their country
  implies. The resolved currency is not stored: the API derives it from the
  override when there is one, otherwise from the country (the first tender
  currency CLDR records there with no end date, so it changes only with the
  installed CLDR data, never with the date).
- Both constraints check only a code's shape. Which codes are assigned is
  checked when an edit is accepted, so a code the standards later retire still
  loads. Both columns are registered-account preferences under the same
  restrictive policies as `preferred_name`, and guest responses omit them.
- `profiles.email` is null only for a verified anonymous Auth user. Permanent
  profiles require the verified provider email. Fake or placeholder guest
  addresses are forbidden.
- `username` is optional for Alpha. When supplied at signup, it is trimmed and
  case-folded before the case-insensitive uniqueness check and profile write.
  Same-email and same-username signup attempts are serialized across API
  instances so only the request that owns the available username may create an
  Auth user. An already-existing Auth email follows the provider's obfuscated
  duplicate path without a profile write or a username-dependent public error.
---

## 5.1 guest_workspaces

Server-owned policy record for one temporary anonymous identity.

### Fields
- `user_id`: `uuid` (Primary Key, references `profiles.id`)
- `conversation_id`: `uuid` (Unique, nullable, references `conversations.id`)
- `status`: `active`, `claiming`, `claimed`, or `expired`
- `created_at`: `timestamptz`
- `expires_at`: `timestamptz`
- `claimed_by`: `uuid` (Nullable, references `profiles.id`)
- `claimed_at`: `timestamptz` (Nullable)
- `updated_at`: `timestamptz`

### Invariants
- The owner must be a verified anonymous Supabase Auth user when the workspace
  is created.
- Exactly one workspace exists per anonymous owner and at most one
  conversation may bind to it.
- Expiry uses a fixed seven-day window after creation. Message, simulation, feedback, and
  conversation activity cannot extend it.
- Browser roles may read only their own active workspace and cannot mutate
  expiry, claim, or cleanup state.
- Cleanup locks `auth.users` and the workspace, re-verifies anonymous identity
  truth, removes the eligible graph, and deletes the Auth row in the same
  database transaction. A converted or permanent account is never eligible.
- Cleanup deletes conversation messages/jobs, guest feedback text, and the
  checkpoint rows whose `thread_id` matches the guest conversation before the
  transactional Auth deletion removes the remaining owner-scoped product rows.
  It also removes safely transferred source identities after a fifteen-minute
  reconciliation grace and abandoned bootstrap identities after five minutes.
  Privacy-safe append-only cost and route/security evidence may retain nullable
  attribution; transcript-bearing state may not.
- Guest Start over is one service-owned transaction. It locks the workspace,
  validates the complete conversation-owned graph, removes that graph and its
  checkpoint thread, and binds one new empty conversation to the same
  workspace. It does not replace the Auth identity, move `expires_at`, or reset
  any lifetime allowance or feedback counter. Append-only cost, route, security,
  and audit evidence is not rewritten.

---

## 5.2 guest_workspace_handoffs

Server-owned claim record for moving one anonymous workspace into one permanent
account created by signup or verified by login.

### Fields
- `id`: `uuid` (Primary Key)
- `secret_hash`: `text` (SHA-256 hex digest; the opaque secret is never stored)
- `source_user_id`: `uuid` (References the anonymous `profiles.id`)
- `destination_email_hash`: `text` (SHA-256 of the normalized destination
  email; required)
- `destination_user_id`: `uuid` (Nullable until a signup insert trigger or
  verified login resolves the permanent `auth.users.id`; cleared if that Auth
  user is deleted)
- `source_conversation_id`: `uuid` (References the one guest conversation)
- `pending_action`: `jsonb` (Nullable typed reason, conversation, action id, and
  decision artifact id when applicable)
- `handoff_kind`: `existing_account` or `new_account_signup`
- `status`: `pending`, `consumed`, or `revoked`
- `created_at`: `timestamptz`
- `expires_at`: `timestamptz` (Exactly ten minutes after creation for an
  existing-account handoff; the fixed guest workspace expiry for signup)
- `consumed_at`: `timestamptz` (Nullable)

### Invariants
- Browser roles cannot read or execute against this table. Only the service
  role may create or claim a handoff.
- A pending source workspace has at most one handoff.
- Preparing a signup handoff locks the source state, reuses the same pending row
  for a same-email retry, rotates its opaque-secret hash, and refuses to change
  the email after a destination Auth UUID is bound.
- A server-only proof in password-signup metadata binds the newly inserted
  non-anonymous Auth UUID in the same database transaction, then is removed
  from Auth metadata. A signup handoff never outlives its source workspace.
- Claim locks the handoff and complete source product graph, resolves the
  destination only from verified Auth email truth, verifies every foreign
  owner, and transfers all mutable product rows in one transaction.
- A consumed handoff remains a read-only replay oracle for the same bound
  destination when a signup or login response is lost. It never repeats the
  transfer or accepts another destination.
- Conversation, message, strategy, job/run, Idea/IdeaVersion, evidence,
  decision, and context ids do not change. Checkpoint rows keep
  `thread_id == conversation_id`.
- Guest counters and feedback are not merged into registered allowances.
  Immutable cost, provider, security, and audit evidence is not rewritten.
- Source anonymous Auth deletion occurs in bounded cleanup only after a
  fifteen-minute claim-reconciliation grace, and in the same transaction that
  re-verifies the source owns no transferred product row. Any claim or cleanup
  failure changes zero owners.

---

# 6. private_alpha_allowlist

Server-side access list for private alpha. This table is checked before signup
and login; it should not be exposed as a frontend product surface.

### Fields
- `email`: `text` (Primary Key, lowercased)
- `role`: `text` (Default: `user`)
- `language`: `text` (Default: `en`)
- `disabled_at`: `timestamptz` (Nullable)
- `created_at`: `timestamptz`
- `updated_at`: `timestamptz`

### Enums
- **role**: `admin`, `developer`, `user`, `requested`
- **language**: `en`, `es-419`

### Notes
- The public access-request endpoint may insert a missing `requested` row. It
  never updates an existing requested, approved, privileged, or disabled row.
- `requested` and unknown roles never grant an elevated role. While public
  account access is open they do not block signup either, because denial needs
  `disabled_at`; when it is closed, neither role admits the email.
- The ops approval action uses `claim_private_alpha_access_welcome` to lock and
  revalidate the active requested row before SMTP. It then sends the localized
  welcome and uses `complete_private_alpha_access_welcome` to record the
  accepted delivery, delete the claim, and promote `requested` to `user`
  atomically while `disabled_at` remains null.
- A before-update guard rejects only the direct `requested` to enabled `user`
  promotion when no matching welcome-delivery row exists. Revoking with
  `disabled_at`, re-enabling an existing `user`, language edits, inserts,
  deletes, and admin/developer roles never touch it.
- There is no invite dashboard, referral system, public invite-code flow,
  pre-created Auth user, or password-setup flow.
- Add a new private-alpha user with only an `email`; set `role` only for
  `admin` or `developer` access. Use `disabled_at` to revoke access.
- `ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED=true` decides what this table denies, and
  it has been open in production since 2026-08-12. Only a row with `disabled_at`
  set is denied now; a missing email is admitted. When that flag is off instead,
  a missing email is denied too.
- For a denied email, `/auth/signup` and `/auth/login` check this table before
  provider signup/session work, but public auth responses are normalized to
  reduce invite enumeration: signup returns `400 auth_signup_failed`, login
  returns `401 unauthorized`, and authenticated API requests reject the email
  after token validation with `403 private_alpha_access_required`.
- The table may contain emails for existing Supabase Auth users; seeding the
  allowlist must not create auth users by itself.
---

## 6.1 private_alpha_access_welcome_deliveries

Private evidence that Argus's access-welcome message for the recipient's
latest grant was accepted by the transactional email provider. This is
operational support truth, not a browser-facing notification or
marketing-email ledger.

### Fields
- `recipient_email`: `text` (Primary Key, normalized with
  `lower(btrim(recipient_email))`)
- `language`: `text` (`en` or `es-419`)
- `content_version`: `text` (Fixed to
  `private-alpha-access-welcome/v1`)
- `subject`: `text` (1 to 200 characters)
- `provider_receipt`: `text` (1 to 256 characters)
- `sent_at`: `timestamptz` (Provider acceptance time, default database time)
- `created_at`: `timestamptz`

### Invariants and access
- `recipient_email` permits at most one access-welcome delivery record. It
  records the latest grant: a fresh approval of a re-requested email replaces
  the stored language, subject, provider receipt, and `sent_at` in the same
  completion that sends the new welcome.
- Writes belong to the RPCs. RLS is enabled with no policies. `PUBLIC`,
  `anon`, and `authenticated` have no table privileges; `service_role`
  receives only `SELECT` plus execute on the security-definer RPCs below.
- `complete_private_alpha_access_welcome(email, language, content_version,
  subject, provider_receipt, claim_token)` is the service-role-only,
  security-definer completion boundary with an empty search path. A completion
  with a claim token validates the matching claim, upserts the delivery,
  deletes the claim, and promotes only an active `requested` row in the same
  transaction. A replay with a null token returns success only for an active
  `user` with no open claim and a matching delivery row; conflicting language,
  content version, or subject is rejected.
- `require_private_alpha_access_welcome_delivery` is a before-update trigger
  on `private_alpha_allowlist` scoped to the promotion edge: only a
  `requested` row becoming an enabled `user` must already have a matching
  delivery record. No other lifecycle transition can fire it, so it needs no
  backfill for rows that predate it.
- `delete_private_alpha_access_welcome_artifacts(email)` is the
  service-role-executable orphan cleanup: it removes claim and delivery rows
  only when no allowlist row exists for the email. The canary teardown and
  offboarding repairs use it; it refuses while the email is still listed.

## 6.2 private_alpha_access_welcome_claims

Private pre-send state for the single access-welcome operation. It closes the
crash window between SMTP acceptance and immutable delivery evidence without a
queue, scheduler, or general mail system.

### Fields
- `recipient_email`: `text` (Primary Key, normalized)
- `language`: `text` (`en` or `es-419`)
- `content_version`: `text` (Fixed to
  `private-alpha-access-welcome/v1`)
- `subject`: `text` (1 to 200 characters)
- `claim_token`: `uuid` (Unique opaque send identity)
- `claimed_at`: `timestamptz`

### Invariants and access
- A claim exists only between claim and completion; completion deletes it, so
  the email's primary key is free for a later grant.
- The claim RPC row-locks the allowlist row and accepts only the exact active
  `requested` language and fixed content contract. A compatible retry before
  24 hours reuses the same token. At or after 24 hours, an open claim cannot
  authorize SMTP again; the approval returns 409 until the claim is released.
- `release_expired_private_alpha_access_welcome_claims()` is the
  service-role-executable release: it deletes claims older than 48 hours (a
  full provider idempotency window plus one scheduled-maintenance day of
  margin). `scripts/ops/scheduled_maintenance.py` runs it daily, and an
  operator can call it directly to unstick an approval immediately. A release
  can produce one duplicate welcome if the original send succeeded and only
  its completion was lost; that trade replaces a permanent lockout.
- Completion revalidates role, language, and disabled state under the row
  lock, so an allowlist row edited while a claim is open makes that claim fail
  closed at completion instead of freezing the row.
- RLS is enabled with no policies. All table privileges are revoked from
  browser and service API roles. `service_role` can reach claim state only
  through the tightly granted security-definer RPCs.

---

# 7. conversations

Represents an isolated chat thread. Each conversation represents a single investing "idea journey."

### Fields
- `id`: `uuid` (Primary Key)
- `user_id`: `uuid` (References `profiles.id`)
- `title`: `text`
- `title_source`: `text` (Default: `'system_default'`)
- `language`: `text` (Nullable)
- `pinned`: `boolean` (Default: `false`)
- `archived`: `boolean` (Default: `false`)
- `deleted_at`: `timestamptz` (Nullable, for soft delete)
- `last_message_preview`: `text` (Nullable)
- `owner_space_id`: `uuid` (Nullable; with `user_id`, references
  `spaces(id, created_by)` ON DELETE CASCADE)
- `created_at`: `timestamptz`
- `updated_at`: `timestamptz`

### Enums
- **title_source**: `system_default`, `ai_generated`, `user_renamed`

### Notes
- Conversations use **soft delete** behavior.
- `owner_space_id` null is a Personal (`/chat`) conversation; a Business
  (`/biz`) conversation stores its space. Every conversation written before
  Business existed is Personal, with no backfill. The rule lives in
  `argus.domain.owner_scope`. Recents, History, search (one fragment on every
  `public.conversations` read in `postgres_search_reader.py`), computed answers
  and delete-all filter by it; reads by conversation id stay owner-scoped.
- A continued computed answer keeps its source's space; a public receipt fork
  is Personal. Decisions, evidence decisions, shared receipts and memory never
  attach to a Business conversation.
- AI-generated titles should be created once sufficient context is established.
- `language` can be stored at the thread level for continuity, but the user profile remains the primary source.
- `last_message_preview` remains a private compatibility/search projection of
  the immutable message. Reader previews derive from the latest owner-scoped
  message metadata at read time, in a single bounded batch for the returned
  page. No new column, per-language copy, backfill, or model call is required.
  This also repairs existing English-authored artifact previews after a
  workspace language change. Ordinary user/conversation text stays verbatim;
  artifact previews contain only kind, symbols and strategy keys and render
  through the frontend language bundle.
---

# 8. messages

Represents individual messages within a conversation.

### Fields
- `id`: `uuid` (Primary Key)
- `conversation_id`: `uuid` (References `conversations.id`)
- `user_id`: `uuid` (References `profiles.id`)
- `role`: `text` (e.g., `user`, `assistant`)
- `content`: `text`
- `metadata`: `jsonb` (Default: `{}`)
- `created_at`: `timestamptz`

### Enums
- **role**: `user`, `assistant`, `system`, `tool`

### Notes
- Message identity, owner, conversation, role, content, and ordering are
  immutable in Alpha. Narrow artifact metadata enrichments may update
  `metadata`, but they must not change message identity or ordering.
- Every durable message append uses the service-role-only
  `append_conversation_message` RPC. The function locks the owned conversation
  row, inserts the message, and updates `last_message_preview` in one
  transaction. `PUBLIC`, `anon`, and `authenticated` cannot execute the
  function or mutate `messages` directly.
- Sanctioned non-turn edits of a pending confirmation card or an editable local
  tool result use the service-role-only
  `update_conversation_message_artifact` RPC on the same serialized spine: it
  locks the owned conversation row and applies only while the caller's read
  still holds, comparing both the row's `metadata` and the conversation's
  latest message id (an empty result is the conflict signal, never a silent
  last-writer win). When the rewritten row is the conversation's latest
  message it carries `last_message_preview` with it while leaving
  `updated_at` untouched, so a non-turn change never reorders recents.
- `metadata.tool_result_cards` owns ordered general tool artifacts. Each card
  stores call/artifact identity, input revision, declaration card type/version,
  arguments, typed outcome, presentation and lifecycle state together. A local
  recompute retains the unknown, treats zero as known, and increments the
  revision through the same guarded writer. Sibling cards remain unchanged.
  Tool outcomes do not require a Strategy, Idea, EvidenceArtifact or backtest
  run. `metadata.tool_jobs` associates each asynchronous job with its call and
  artifact identity; repeated calls remain independent through completion and
  reload. The message remains the durable owner after direct edits, rather than
  writing a competing checkpoint copy.
- A computed answer is an artifact without a run. Its cards, one per
  calculation, live in `metadata.tool_result_cards` and its one marker in
  `metadata.computation`, which the chat turn, the recompute route and the
  continue route all write from every card in order; nothing else is stored.
  The marker is `{kind, inputs}` for one calculation and `{calculations: [{kind,
  inputs}, ...]}` for an answer that weighs options; both read alike. A
  research or no-search answer that computed its calculations carries the same
  pair, beside its `research` sidecar when it retrieved, and
  `metadata.answer_text_template` (`{cards: {<calculation name>: <artifact_id>},
  text, language}`; one stored as `{artifact_id, text, language}` reads as its
  one card), the prose with its figure references, which the recompute route
  re-renders into `content` from the current cards. `metadata.answer_assumptions`
  (`[{artifact_id, name}]`) names each assumed input that prose never names; the
  app lists them under the answer, and the recompute route derives the list
  again. A pending calculation
  question keeps `{calculations, requested_field, requested_fields, evidence,
  retrieved}` in its clarification payload until the reply completes it; a
  payload stored with one `calculation` reads as a list of one. A research
  answer whose calculations need figures only the reader knows stores the same
  shape as `metadata.calculation_offer` instead; the typed `calculation_offer`
  action turns it into that question.
  `metadata.continued_from` (`{conversation_id, message_id}`) marks a result
  continued in a new chat; the source message is never changed. Comparing,
  refreshing and re-running a computed answer store nothing: the stored card
  stays the durable truth and each read's result comes back beside it.
- A confirmation card's liveness truth lives on its own row:
  `metadata.confirmation_card.confirmation_state` (`active`, `consumed`,
  `cancelled`, `superseded`). Run admission stamps `consumed` through the
  guarded writer before dispatch; a run that dies without a result restores
  `active`; a cancelled or superseded card is never restored. Every
  liveness reader derives from one oracle over this field
  (`confirmation_card_is_dead`), with a compatibility clause for durable
  transcripts that predate the stamp and carry consumption only as later
  result messages. No reader may re-implement the predicate or infer
  liveness from job tables.
- Job success is one-way against the card lifecycle: both success writers
  (the worker's SQL update and the API gateway's PostgREST update) embed a
  predicate generated beside the card-restore classification in
  `argus.domain.backtest_job_lifecycle`, so success can only follow a state
  a worker legitimately holds (queued, running, or a re-claimable failure).
  A state the card was restored from can never convert into a result; a
  refused success write leaves the terminal state standing and is logged by
  its caller. This tightens a spine invariant so it can carry the
  consumption feature; the unguarded write was correct self-healing before
  cards were consumed at admission.
- Recent-window reads use `list_messages(newest_first_window=True)`: the
  newest N messages of the conversation restored to chronological order.
  An ascending read with a limit returns the head of the conversation and
  starves every recent-state reader on long conversations (#433).
- Conversation message order is deterministic by `(created_at DESC, id DESC)`.
  Under the conversation lock, a new append receives `created_at` at least one
  microsecond newer than the current maximum. Metadata-only updates do not
  change `created_at` or `id`, so they cannot promote an older message into the
  latest response-option source.
- A response-option request uses the same RPC as an atomic admission boundary.
  It matches the owner, conversation, exact latest assistant id, canonical
  metadata snapshot, option id, and replacement values before inserting the
  preallocated request id. An exact replay returns the existing request and the
  source immediately preceding it without inserting a duplicate; a stale or
  mismatched claim returns no row.
- `metadata` stores token usage, model identifiers, latency, and tool execution traces.
- Every terminal assistant message for an ordinary non-backtest chat turn stores
  immutable `metadata.agent_runtime_turn.turn_id`, `request_id`, `terminal`, and
  terminal `status`. These values match its `chat_turn_lifecycles` row and make
  terminal evidence discoverable if the lifecycle CAS does not complete.
- Assumptions answers persist `metadata.response_intent.kind =
  artifact_assumptions`, with `facts.artifact_kind`, `facts.asset_class`, and
  `facts.display_facts`. The confirmation fact projector owns the values for
  both the card and its answer; zero costs and the separate starting-capital
  and recurring-contribution roles remain explicit numbers. These are ordinary
  completed assistant messages even when `content` is empty. Reader language
  and copy come from the typed facts, without another model call or a stored
  per-language variant. Existing original prose stays immutable private
  audit/model context and is never a fallback for a typed assumptions answer.
  Old confirmation payloads can supply missing facts on read. Older freeform
  assumptions messages without a typed assumptions discriminator cannot be
  safely identified and keep ordinary transcript behavior; no prose classifier
  or destructive historical rewrite is permitted.
- Original result `content`, card `quick_take`/`breakdown`, and job
  `result_readout` remain immutable private audit/model context. Public reader
  projections omit them. New compositions store a closed
  `result_readout_content` envelope on the run's result card (Quick take) or
  assistant message metadata (Breakdown), with version, surface, authoring
  workspace language, and complete accepted text or null on fallback. Job and
  message read projections derive the Quick take envelope from its run card.
  Readers may show its text only when their language matches; every other case
  uses typed facts. This is additive JSON metadata, with no migration, backfill,
  read-time model call or rewritten historical content. Source and fallback
  provenance use the existing `result_readout_*` fields. The exact closed
  transport is documented in API_CONTRACT.md's Message section.
  A new draft's structured reported language must match the requested workspace
  language before accepted text is stamped. Its quoted-figure references are
  checked against one labeled fact sheet and remain internal; they do not
  widen the persisted/public envelope. Language or reference mismatch stores
  null text with the existing fallback/failure provenance, never a partial.
  Existing `result_fact_bank` is a read projection, not a second metrics owner;
  missing historical transport facts are repaired on read using owner and
  conversation scoped run identity. Its `figures` (and a public run's
  `figures`) are derived on read from the persisted two-decimal `metrics`,
  never stored: one backend rounding, no client rounding, no backfill. No
  language-specific rows or backfill are needed. Failed evidence lookup yields localized unavailable text, never
  saved-prose fallback. Python and TypeScript AST guards pin private readers.
- Message metadata may contain reloadable chat artifacts such as
  `pending_strategy`, `confirmation_card`, `confirmation_payload`,
  `result_card`, result identifiers, `chat_action`, `failed_action`,
  `retry_last_turn`, `recovery`, `clarification`, and the additive
  `discovery` sidecar (`argus_discovery/v1`: bounded sources, provider-resolved
  candidates, and unverified names for grounded asset discovery; the Search
  provider id is excluded by contract). These fields hydrate the
  transcript, action affordances, and localized degraded-fallback UI; they do
  not make free-form transcript text the source of truth for strategy state.
  A typed `clarification.prompt_source` distinguishes exact LLM-authored prose
  (`llm_generated`) from frontend-localized deterministic fallback
  (`degraded_fallback`); structured options remain reloadable in both cases.
  Degraded fallback `content` remains stored only as compatibility transport;
  it is not projected into later model history or `last_message_preview`, so
  Recents and conversation search do not expose the fallback language. Exact
  `llm_generated` prose remains eligible for those continuity surfaces.
  A confirmation card turn stores empty `content` and a card without
  `summary`. Its `last_message_preview` holds the card's typed facts as
  search text (symbols, strategy type, start and end dates), and later model
  history reads the same facts instead of prose. Rows written before this
  keep their stored English sentence and preview until the conversation's
  next message; readers never receive the sentence and model history derives
  from the stored card instead.
- User-message `metadata.mentions` may additionally preserve a selected asset
  or indicator's optional `message_range: { start, end }`. This is a UTF-16
  display span into immutable `content`, stored only when it exactly matches
  that mention's `insert_text`. It lets the transcript render the selected
  occurrence of repeated text after reload. A missing or malformed range falls
  back to legacy best-effort display matching; it is not resolution provenance,
  runtime state, or an Omnisearch input, and needs no migration.
- When a turn follows an artifact-backed setup, the runtime must reconstruct the
  working draft from canonical artifact state before applying the new user
  message as a patch. Canonical artifact state comes from, in order of
  specificity, the structured action payload, active confirmation payload,
  completed `backtest_runs.config_snapshot`, saved strategy state, or failed
  action launch payload.
- Persisted recovery or retry metadata is scoped to the failed turn/action it
  references. Later turns that create a new draft, active confirmation,
  completed result, or explicit cancellation should supersede stale retry
  affordances during hydration.
- Omnisearch may recall only `role = 'user'` message content. The partial
  `idx_messages_user_content_norm_trgm` GIN index uses the same checked-in
  Python 3.10-compatible normalized-content SQL expression as the bounded
  search reader and `extensions.gin_trgm_ops`. The index adds no function,
  view, grant, or RLS change; owner, active-conversation, guest-workspace, and
  exact-token rechecks remain query predicates before ranking and limits.
- A transcript jump reuses the owner-scoped message page read with
  `anchor_message_id`. The anchor is resolved inside the requested
  conversation, and the response remains capped at the requested page limit;
  it is not a transcript scan or a new durable memory record.
---

## 8.1 chat_turn_lifecycles

Represents one mutable current-state recovery record for each accepted ordinary
chat turn: any `POST /api/v1/chat/stream` request not admitted as
`chat.run_backtest`. Run actions use `backtest_jobs` instead. This table is not a
second job queue, transcript, event ledger, or LangGraph state store. Messages
remain immutable; message reads project the current lifecycle row into
`metadata.agent_runtime_turn` without rewriting the message.

### Fields
- `turn_id`: `uuid` (Primary Key and reference to the accepted user
  `messages.id`; this is also the `request_message_id`)
- `user_id`: `uuid` (References `profiles.id` ON DELETE CASCADE)
- `conversation_id`: `uuid` (References `conversations.id` ON DELETE CASCADE)
- `assistant_message_id`: `uuid` (Nullable, unique, references `messages.id` ON
  DELETE SET NULL)
- `request_id`: `text` (The request correlation id used by responses, logs, and
  route-receipt metadata)
- `status`: `text`
- `reconciled_outcome`: `text` (Nullable)
- `failure_code`: `text` (Nullable, stable and user-safe)
- `retryable`: `boolean` (Default: `false`)
- `accepted_at`: `timestamptz`
- `running_at`: `timestamptz` (Nullable)
- `terminal_at`: `timestamptz` (Nullable)
- `reconciled_at`: `timestamptz` (Nullable)
- `created_at`: `timestamptz`
- `updated_at`: `timestamptz`

### Enums and constraints
- **status**: `accepted`, `running`, `completed`, `recoverable_failed`,
  `abandoned`, `reconciled`.
- **reconciled_outcome**: `completed` or `recoverable_failed`; required only
  when `status = reconciled` and null otherwise. No-proof recovery uses
  `status = abandoned` directly.
- `turn_id` makes lifecycle creation idempotent for the accepted user message.
- `assistant_message_id` is unique when present so one terminal assistant
  message cannot settle two turns.
- `abandoned` requires `assistant_message_id = null`; by definition no
  qualifying terminal assistant message settled that turn.
- Terminal statuses are `completed`, `recoverable_failed`, `abandoned`, and
  `reconciled`.

### Transition ownership and idempotency
- The user message and `accepted` row are created in one database-owned
  transaction after request admission succeeds.
- One database compare-and-set function locks the lifecycle row and permits only
  the transitions named in `docs/API_CONTRACT.md` under
  `contract-chat-turn-lifecycle`.
- Repeating the same target status, assistant-message link, failure code, and
  reconciliation outcome returns the current row as a no-op. A different
  terminal target is rejected.
- Route receipts correlate through the same `user_id`, `conversation_id`,
  `request_id`, and message ids; the lifecycle row does not duplicate receipt
  payloads.
- Owner-scoped RLS uses `auth.uid() = user_id`, and `authenticated` receives `SELECT` only. `INSERT`, `UPDATE`, and `DELETE` are revoked from `anon` and
  `authenticated`; lifecycle creation and transitions use the server-side
  transaction/CAS boundary only. Any database function used for that boundary
  also revokes execution from `PUBLIC`, `anon`, and `authenticated`. The
  frontend cannot mutate lifecycle state directly.

### Reconciliation boundary
- `accepted`/`running` rows become stale after 15 minutes according to database
  time and `stale_since = COALESCE(running_at, accepted_at)`.
- The next chat POST and conversation-message read reconcile at most 20 stale
  rows for that conversation in `stale_since ASC, turn_id ASC` order. Private
  alpha does not add a background sweeper.
- Qualifying terminal evidence is an immutable assistant message whose
  `user_id`, `conversation_id`, `metadata.agent_runtime_turn.turn_id`, and
  `metadata.agent_runtime_turn.request_id` match the lifecycle row, whose
  terminal flag is true, and whose terminal status is `completed` or
  `recoverable_failed`.
- Candidates use `created_at ASC, outcome_precedence ASC, id ASC`, with failure
  precedence 0 and completed precedence 1. The first candidate wins and becomes
  `assistant_message_id`; its status becomes `reconciled_outcome`. Checkpointer
  state may corroborate that message but cannot prove a terminal user-visible
  outcome alone. With no qualifying message, the row becomes `abandoned` with
  `failure_code = turn_abandoned`.
- For `abandoned`, the read-time projection belongs to the accepted user message
  whose `id = turn_id`. It overlays terminal lifecycle, `turn_abandoned`
  recovery, and typed `retry_last_turn` metadata without changing the immutable
  message row. The frontend places the presentation-only recovery row directly
  after that user message; the API does not create or persist an assistant
message for this projection.

---

## 8.2 conversation_read_states

Stores one durable read boundary and optional manual-unread flag for an owned
conversation. It is not an event log and does not duplicate lifecycle, job,
message, or result content.

### Fields

- `user_id`: `uuid` (Part of the primary key; references `profiles.id` with
  update/delete cascade)
- `conversation_id`: `uuid` (Part of the primary key)
- `read_through_occurred_at`: `timestamptz` (Nullable)
- `read_through_source_kind`: `text` (`chat_turn` or `backtest_job`, nullable)
- `read_through_source_id`: `uuid` (Nullable)
- `manual_unread_at`: `timestamptz` (Nullable and independent of read-through)
- `created_at`: `timestamptz`
- `updated_at`: `timestamptz`

The three read-through fields are either all null or all non-null. Boundaries
compare as `(occurred_at, source_kind_rank, source_id)`, with `chat_turn = 1`
and `backtest_job = 2`, and advance monotonically. The primary key is
`(user_id, conversation_id)`. A composite foreign key to
`conversations(id, user_id)` uses `ON UPDATE CASCADE` and `ON DELETE CASCADE`,
so guest claim transfers the state and conversation cleanup removes it in the
same transaction.

Authenticated owners may select their row through RLS but cannot insert,
update, or delete it directly. Server-only RPCs own mutation, lock the
conversation/read/source rows, and revalidate terminal eligibility before
advancing a cursor. Read RPCs accept at most 100 owned conversation ids and the
activity reconciler settles at most 20 stale turns across that batch using the
existing lifecycle evidence predicate.

The migration baseline is idempotent and keyset-batched at 500 conversations.
It marks only the newest eligible terminal boundary at or before the captured
migration-start cutoff as read. Activity completing after that cutoff remains
unread. The baseline and later activity reads do not update conversation,
message, job, Run, artifact, or sort timestamps.

---

# 9. strategies

Legacy saved executable-idea record. The table remains owner-scoped and readable
so historical runs and history entries do not break; no active product path
creates, patches, restores, or deletes Strategy rows.

### Fields
- `id`: `uuid` (Primary Key)
- `user_id`: `uuid` (References `profiles.id`)
- `conversation_id`: `uuid` (Nullable, references `conversations.id`)
- `name`: `text`
- `name_source`: `text` (Default: `'system_default'`)
- `template`: `text`
- `asset_class`: `text`
- `symbols`: `text[]`
- `parameters`: `jsonb` (Template-specific config)
- `metrics_preferences`: `text[]` (List of metric keys for UI priority)
- `benchmark_symbol`: `text`
- `pinned`: `boolean` (Default: `false`)
- `deleted_at`: `timestamptz` (Nullable)
- `created_at`: `timestamptz`
- `updated_at`: `timestamptz`

### Alpha Constraints
- **Symbols**: Min 1, Max 5.
- **Asset Class**: All symbols must share the same asset class.
- **Side**: Long-only (Short is deferred).
- **Asset Classes**: `equity`, `crypto`, `currency_pair`.
- **Note**: Strategies may target multiple symbols but only within the same `asset_class`.

> [!TIP]
> **Global Rule**: Historical Collection rows may contain mixed asset classes.
> Backtest runs may not mix asset classes operationally, and no current flow
> creates or manages Collections.

### Notes
- Existing rows may still parent an owner-scoped direct backtest through
  `backtest_runs.strategy_id` compatibility.
- Display metrics on old rows remain readable; there is no Strategies surface.
---

# 10. collections

Legacy groupings retained only for owner-scoped historical reads.

### Fields
- `id`: `uuid` (Primary Key)
- `user_id`: `uuid` (References `profiles.id`)
- `name`: `text`
- `name_source`: `text` (Default: `'system_default'`)
- `description`: `text` (Nullable)
- `pinned`: `boolean` (Default: `false`)
- `deleted_at`: `timestamptz` (Nullable)
- `created_at`: `timestamptz`
- `updated_at`: `timestamptz`

### Notes
- No active product path creates, patches, restores, deletes, attaches, or
  detaches Collection records.
- Collections do **not** perform aggregate portfolio simulations.
- **Historical asset mixing**: Existing rows may contain Equity, Crypto, and
  Currency Pair strategies, but they cannot be executed as a mixed-asset batch.
---

# 11. collection_strategies

Join table mapping strategies to collections.

### Fields
- `id`: `uuid` (Primary Key)
- `collection_id`: `uuid` (References `collections.id` ON DELETE CASCADE)
- `strategy_id`: `uuid` (References `strategies.id` ON DELETE CASCADE)
- `user_id`: `uuid` (References `profiles.id` ON DELETE CASCADE)
- `created_at`: `timestamptz`

### Constraints
- `UNIQUE(collection_id, strategy_id)`
---

# 12. backtest_runs

Represents an immutable result of a simulation. Every run is reproducible from its `config_snapshot`.

### Fields
- `id`: `uuid` (Primary Key)
- `user_id`: `uuid` (References `profiles.id`)
- `conversation_id`: `uuid` (Nullable)
- `strategy_id`: `uuid` (Nullable)
- `status`: `text` (Default: `'queued'`)
- `asset_class`: `text`
- `symbols`: `text[]`
- `allocation_method`: `text` (Default: `'equal_weight'`)
- `benchmark_symbol`: `text`
- `config_snapshot`: `jsonb` (The exact parameters used for the run)
- `metrics`: `jsonb` (Canonical machine-readable results)
- `conversation_result_card`: `jsonb` (UI-friendly presentation object)
- `chart`: `jsonb` (Historical equity curve, detail-only)
- `trades`: `jsonb` (List of individual trades, detail-only)
- `error`: `jsonb` (Error details if status is `failed`)
- `created_at`: `timestamptz`
- `updated_at`: `timestamptz`

### Enums
- **status**: `queued`, `running`, `completed`, `failed`
- **allocation_method**: `equal_weight`

### Notes
- Runs are immutable after completion.
- `benchmark_symbol` is derived from `asset_class` defaults in Alpha (`SPY` for equities, `BTC` for crypto, tested pair for currency pairs).
- `metrics.aggregate.performance.portfolio_value_range` stores aggregate strategy portfolio equity close peak/lowest values for the run period.
- Every `metrics` `efficiency` block, aggregate and per symbol, stores `buy_fills` and `sell_fills` beside `total_trades`. When costs were modeled, `metrics.aggregate.performance.execution_realism` also stores `modeled_fee_cost`, `modeled_slippage_cost`, and `modeled_cost_total` in dollars. Older rows omit these keys, and readers treat a missing key as unknown, never zero. No migration is required.
- `chart` stores the aggregate portfolio equity curve, its matching `value_summary`, and capped executed-fill markers used by the result card. Multi-symbol runs store the portfolio curve, not separate comparison series.
- New chart writers also persist two optional additive objects inside the same
  immutable `chart` JSON: `exploration_policy` (generic range-eligibility hints
  resolved from the strategy capability: `minimum_visible_observations`,
  optional `minimum_meaningful_duration`) and `marker_summary` (exact
  `total_groups`/`included_groups`/`sampled` marker-cap evidence). Legacy rows
  omit both fields and remain valid; readers degrade to observation-only range
  behavior and make no marker-completeness claim. No migration is required, and
  these fields never change execution, metrics, or the effective window.
- Direct run rows store the normalized engine config directly in
  `config_snapshot`; chat-launched rows may include
  `config_snapshot.engine_config` with the exact normalized engine config
  executed by the launch adapter. This replay payload is canonical when present.
- Benchmark comparisons are persisted only when benchmark observations cover the
  selected window sufficiently; late, early-ending, or sparse benchmark data
  should fail as data unavailable rather than being silently backfilled.
- Legacy persisted chart payloads may include `value_extrema`; readers may use it
  as a fallback, but new run writers should persist `value_summary`.
- `trades` may mirror chart event markers for lightweight UI hydration. Detailed execution ledgers can preserve signals, order intents, fills, ignored signals, and position snapshots, but list endpoints must expose only lightweight result metadata.
- When execution realism is enabled and the engine models nonzero fees/slippage,
  `conversation_result_card.execution_costs` stores structured result evidence:
  `fee_bps`, `slippage_bps`, gross/net total return, return drag, and benchmark
  cost treatment. Idealized runs omit this object.
- Historical `strategy_id` linkage must be read from canonical stored records,
  never reconstructed from frontend display text.
- Follow-up refinements from a result card must be seeded from
  `config_snapshot` or equivalent canonical run metadata. A user's partial
  change request may update the relevant field, but omitted run fields such as
  symbols, contribution amount, cadence, timeframe, benchmark, and strategy
  template must carry forward unless explicitly changed or invalidated by
  deterministic guardrails.
- P1 completed chat backtests also attach sidecar evidence metadata to
  `conversation_result_card`:
  - `idea_id`
  - `idea_version_id`
  - `evidence_artifact_id`
  - `evidence_lifecycle`
  - `artifact_type = "backtest"`
  - `decision_note_id` and `decision_state` after explicit decision capture.
  These fields are stable codes/ids, not localized display prose.
- Local/in-process and Render Workflow writers pass a stable, preallocated run
  id into the same typed finalizer. Finalization commits the completed run,
  Idea, IdeaVersion, EvidenceArtifact, and result-card identity as one logical
  transaction. Readers must not observe a run as completed before that tuple is
  finalized, and retries must reuse the same run id.
- Reload reconciliation projects a succeeded job from that canonical finalized
  tuple. Its result-card evidence identity and any decision note/state remain
  attached to the same owner-scoped run, rather than being rebuilt from display
  copy or a stale queued-job projection.
---

## 12.1 P1 Idea / Evidence / Decision Spine

P1 adds a light evidence ledger around completed backtests. Persistence is
automatic; user commitment is explicit.

### ideas

Represents a durable investing idea container.

Fields:
- `id`: `uuid` (Primary Key)
- `user_id`: `uuid` (References `profiles.id` ON DELETE CASCADE)
- `source_conversation_id`: `uuid` (Nullable, references `conversations.id`)
- `title`: `text`
- `summary`: `text`
- `lifecycle`: `text` (`captured`, `reviewed`, `saved`, `decided`, `archived`, `discarded`)
- `active_version_id`: `uuid` (Nullable, references `idea_versions.id`)
- `created_at`: `timestamptz`
- `updated_at`: `timestamptz`

Creation order:
- Insert the idea with `active_version_id = null`.
- Insert the corresponding `idea_versions` row.
- Update `ideas.active_version_id` to the inserted version id.

This ordering keeps the circular idea/version relationship compatible with
Supabase FK enforcement. If artifact creation fails after either sidecar is
created, the gateway discards the transient idea/version sidecars and re-checks
`UNIQUE(user_id, source_run_id)` before surfacing an error, so worker retries do
not leave orphaned evidence records.

### idea_versions

Immutable material experiment definition that evidence can reference.

Version boundary:
- One `IdeaVersion` represents one material experiment definition.
- Material changes to the traded assets, date range, benchmark, strategy or
  executable rules, cadence, capital, or modeled fees/slippage create a new
  version linked to the same `Idea`.
- Multiple edits before one confirmed run collapse into one new version.
- Wording changes, explanations, retries, and abandoned edits do not create
  versions.
- An updated date range is a material change. Its new run/evidence belongs to a
  new version so Argus can compare performance and assumptions with the prior
  version.

Fields:
- `id`: `uuid` (Primary Key)
- `idea_id`: `uuid` (References `ideas.id` ON DELETE CASCADE)
- `user_id`: `uuid` (References `profiles.id` ON DELETE CASCADE)
- `source_conversation_id`: `uuid` (Nullable, references `conversations.id`)
- `source_run_id`: `uuid` (Nullable, references `backtest_runs.id`)
- `version_number`: `integer`
- `canonical_spec`: `jsonb`
- `strategy_snapshot`: `jsonb`
- `title`: `text`
- `summary`: `text`
- `lifecycle`: `text`
- `created_at`: `timestamptz`

DB immutability:
- After insert, immutable fields are enforced by a database trigger:
  `id`, `user_id`, `idea_id`, `source_conversation_id`, `source_run_id`,
  `version_number`, `canonical_spec`, `strategy_snapshot`, `title`, `summary`,
  and `created_at`.
- `lifecycle` may change for review, save, archive/discard, and decision
  transitions without creating a new version row.

### evidence_artifacts

Immutable proof package. P1 writes `artifact_type = "backtest"` from completed
backtests.

Fields:
- `id`: `uuid` (Primary Key)
- `idea_id`: `uuid` (References `ideas.id` ON DELETE CASCADE)
- `idea_version_id`: `uuid` (References `idea_versions.id` ON DELETE CASCADE)
- `user_id`: `uuid` (References `profiles.id` ON DELETE CASCADE)
- `source_conversation_id`: `uuid` (Nullable, references `conversations.id`)
- `source_run_id`: `uuid` (Nullable, references `backtest_runs.id`)
- `artifact_type`: `text` (`backtest`)
- `lifecycle`: `text`
- `title`: `text`
- `digest`: `text`
- `payload`: `jsonb`
- `created_at`: `timestamptz`
- `updated_at`: `timestamptz`

DB immutability:
- After insert, immutable fields are enforced by a database trigger:
  `id`, `user_id`, `idea_id`, `idea_version_id`, `source_conversation_id`,
  `source_run_id`, `artifact_type`, `title`, `digest`, `payload`, and
  `created_at`.
- `lifecycle` and `updated_at` may change for lifecycle transitions and
  timestamp bookkeeping.

Payload rules:
- `payload.result_card` is sanitized for recall and must not expose context
  packets, provider/model metadata, route receipts, retry payloads, or raw
  conversation transcripts.
- `payload.assumptions`, `payload.metrics`, `payload.provenance`,
  `payload.digest`, and when available `payload.quick_take` and
  `payload.breakdown` are first-class evidence context, not frontend-only copy.
- Search previews derive from this sanitized evidence payload and may expose
  digest, symbols, benchmark, assumptions, compact metric summaries, quick take,
  and breakdown context. Search previews must not expose internal ids inside
  `preview`; object identity remains on the top-level search result fields.
- `UNIQUE(user_id, source_run_id)` keeps completed-run capture idempotent.
  Replays or worker restarts must reuse the existing sidecar instead of
  creating another evidence artifact for the same completed run.
- Evidence search and recall require the source run's finalized identity. An
  incomplete finalization is not eligible for conversation reload, history, or
  Omnisearch, even if metric computation already finished.
- A rerun on fresher provider data may create a new immutable
  `EvidenceArtifact` on the same `IdeaVersion` only when the canonical experiment
  definition is unchanged. The artifact must retain its own run identity,
  data-through/freshness provenance, metrics, and timestamps.
- Freshness comparison may use multiple evidence artifacts from the same
  version or evidence from successive material versions. It must not overwrite
  historical evidence.
- Research/news context is not part of the implemented P1 table contract.
  A later freshness/research slice may attach sanitized, source-backed context
  only after its artifact type, source, timestamp, and ownership contract are
  explicitly specified.

### decision_notes

Explicit user judgment on a computation. A decision attaches to exactly one
computation owner and stores the current decision, not an append-only history:

- A backtest decision attaches to its evidence artifact. `evidence_artifact_id`,
  `idea_id`, and `idea_version_id` are set; `source_message_id` and
  `computation` are null. The run behind the artifact owns the inputs, so
  readers derive the computation (`backtest` with the run id) instead of
  storing a copy.
- A computed-answer decision attaches to the assistant message that carried
  the answer. `source_message_id` and `computation` are set; the three lineage
  columns are null. The computation is stored so the decision survives the
  message and can be re-run when opened. An answer that weighs options still
  takes one decision, which stores every calculation and re-runs each when
  opened; the column has no shape check, so this needed no migration, and
  `UNIQUE(user_id, source_message_id)` still holds.

Fields:
- `id`: `uuid` (Primary Key)
- `idea_id`: `uuid` (Nullable, references `ideas.id` ON DELETE CASCADE)
- `idea_version_id`: `uuid` (Nullable, references `idea_versions.id` ON DELETE CASCADE)
- `evidence_artifact_id`: `uuid` (Nullable, references `evidence_artifacts.id` ON DELETE CASCADE)
- `user_id`: `uuid` (References `profiles.id` ON DELETE CASCADE)
- `source_conversation_id`: `uuid` (Nullable, references `conversations.id`)
- `source_message_id`: `uuid` (Nullable, references `messages.id` ON DELETE SET NULL)
- `computation`: `jsonb` (Nullable; `{"kind": <slug>, "inputs": <object>}`, or
  `{"calculations": [{"kind", "inputs"}, ...]}` for an answer that weighs options)
- `decision_state`: `text` (`watching`, `promising`, `rejected`, `revisit_later`)
- `note`: `text` (Nullable)
- `created_at`: `timestamptz`
- `updated_at`: `timestamptz`

Constraints:
- `decision_notes_attachment_check`: `(evidence_artifact_id is not null) <>
  (computation is not null)`, one owner per row.
- `decision_notes_evidence_lineage_check`: `idea_id` and `idea_version_id` are
  null exactly when `evidence_artifact_id` is null.
- `UNIQUE(user_id, evidence_artifact_id)` enforces one current decision per
  user-owned evidence artifact.
- `UNIQUE(user_id, source_message_id)` enforces one current decision per
  user-owned answer message. Nulls do not collide.
- Duplicate POST/retry semantics update the existing decision row and return the
  canonical current decision; a repeated write on a computed answer keeps the
  first stored computation.
- The message metadata that declares a computation (`metadata.computation`)
  is written once by the backend. The decision beside it (`decision_note_id`,
  `decision_state`) is not stored on the message: every transcript read derives
  it from this table through `argus.api.decision_message_reads`, for computed
  answers and result cards alike, so no second durable copy can disagree with
  the row.
- Migration `20260908120000_decision_notes_attach_to_computations.sql` relaxes
  the three lineage columns and adds the attachment columns and constraints;
  no row is rewritten and no object is removed. The promotion gate classifies
  it destructive only because `alter column ... drop not null` carries the
  word the classifier reads as destructive.
- The public decision write contract accepts at most 500 note characters. The
  durable column remains nullable `text` so previously accepted longer notes
  stay readable; no migration or destructive truncation is introduced.
- A stored `computation` may carry `symbols`, at most five asset identities the
  marker owner derives from the computation's typed `symbol` inputs; a
  computation about no asset omits the key. Search counts a computed answer
  under an asset from `messages.metadata->'computation'->'symbols'` on the
  owner's assistant messages, bounded and owner-scoped, with no new table,
  index or migration. The message marker itself is written from the answer's
  tool result card by one owner (`argus.domain.computation_marker`), on the
  chat turn and on the recompute route alike.

### Run dossier read projection

Run dossier history is not a table or durable summary. The
`GET /api/v1/conversations/{conversation_id}/run-dossiers` endpoint projects
existing owner-scoped records in this order:

`Conversation -> completed BacktestRun -> EvidenceArtifact -> current
DecisionNote (optional) -> assistant result message anchor (optional)`.

Only completed evidence-backed runs are eligible. Ordering and pagination use
the run's effective completion activity, `coalesce(updated_at, created_at)`,
then run id, newest first. `total_runs` and `decided_runs` are scalar
server-owned counts over the complete eligible set; clients never accumulate
them from pages. This projection creates no record, migration, revision log,
embedding, or generated recap.

Durable decision capture:
- The API uses the service-role-only `upsert_current_decision_note` RPC so the
  decision row, evidence artifact lifecycle, idea lifecycle, and active
  idea-version lifecycle move to `decided` together.
- The RPC is not a public/client surface. Frontend code only calls
  `POST /evidence-artifacts/{id}/decision`.
- Omnisearch recall uses the same bounded normalized-text pattern over the
  existing canonical `decision_state` and `note` fields. The
  `idx_decision_notes_recall_norm_trgm` GIN index adds no new durable memory
  record, function, view, grant, or RLS change; owner and conversation checks
  remain in the recall query before ranking and limits.
- Asset rollups use the existing maximum-five-symbol BacktestRun contract as
  an index boundary. `argus_search_symbol_casefold(text)` is a pure immutable
  SQL helper with Python 3.10 raw-casefold parity, and
  `idx_backtest_runs_owner_symbol_{1..5}_prefix` are owner-first partial
  B-tree expression indexes for completed non-null symbol slots. They add no
  table, recall record, view, grant, or RLS change. The reader resolves an
  exact or unique indexed prefix before evidence/decision lineage hydration.

### RLS

All four P1 tables are owner-scoped by `user_id`. Select, insert, update, and
delete policies require `auth.uid() = user_id`. Backend P1 persistence uses the
service role server-side; service-role grants do not relax frontend/client RLS.

## 12.1.1 P1 Observability Envelope

P1 defines the private-alpha observability envelope in code. B3 measurement
slice 3 adds the first durable internal cost ledger while keeping product
analytics and eval-result persistence separate. Wave 1 (SPEC 0, package 0C-1)
replaces the earlier product and guest funnel events with one closed analytics
registry: PostHog receives only the events below, each under its own name.

Current behavior:
- `argus_observability_event/v1` is the canonical event-envelope schema;
  analytics events carry `argus_analytics_event/v1`.
- Default privacy mode is `metadata_only`.
- The only way an event reaches PostHog is `capture_analytics_event()` in
  `src/argus/observability/analytics_events.py`. Only the frozen
  `AnalyticsEnvelope` it builds can carry an event (the generic envelope has no
  such field), and the sink validates it again before sending, technical
  fields and build timestamp included. It suppresses everything else with
  `reason = "not_an_analytics_event"`, including an envelope that only names an
  event, a subclass or unvalidated copy of a model, extra attributes, or a
  `distinct_id` that is not an actor hash. The eval harness writes nothing to
  the product stream.
- Live PostHog capture is enabled only when `POSTHOG_PROJECT_TOKEN` and an
  explicit PostHog region/host are present; missing token suppresses with
  `reason = "posthog_not_configured"`, and missing or unsupported region/host
  suppresses with `reason = "posthog_region_not_configured"`.
- PostHog is server-side only and personless (`$process_person_profile = false`).
- US Cloud is the current PostHog region choice for private alpha compliance
  posture.

Analytics events. Each is one Pydantic model (`extra="forbid"`, strict) whose
fields are exactly the properties listed. Every field is a literal value, a
boolean, a bounded integer, a calculation name checked against the catalog, or
`cohort`. `tests/test_analytics_events.py`
fails if any field could hold free text or a money-formatted value (A4).

| Event | Properties | Fires (package) |
| --- | --- | --- |
| `first_answer_shown` | `account_kind`: `guest` or `signed_in`; `chip_audience`: `everyday`, `practitioner`, or `none`; `language`: `en` or `es-419`; `cohort` for guests with a stored cohort only | first completed answer per subject (0C-3) |
| `signed_in` | `signup`: `new` or `returning`; `trigger`: `save`, `goal`, `checklist`, or `other`; `guest_id_hash` only when the account came from a guest; `cohort` when the account has one | every sign-up and sign-in (0C-4) |
| `card_saved` | `calculator`: a registered calculation name or `backtest` | saving a card (0C-4) |
| `goal_created` | `goal_type`: `savings` | registered; fires in stage 2 |
| `checklist_step_completed` | `step`: `1`, `2`, or `3` | registered; fires in stage 2 |
| `reminders_opted_in`, `reminders_opted_out` | `channel`: `email` or `push` | registered; fire in stage 3 |
| `session_started` | `days_since_signup`: integer, 0 to 36500, computed on the server; `cohort` when the account has one | once per browser session, signed-in only (0C-5) |
| `installed_app_opened` | none | standalone launch, once per session (0C-5) |
| `landing_viewed` | `language`: `en` or `es-419`; `cohort` for guests with a stored cohort only | once per landing view (0C-5) |
| `receipt_shared` | `calculator`: a registered calculation name, `backtest`, `multiple`, or `none` | a real share-link insert (0C-8) |

- `cohort` is the invite cohort code, `^[a-z]{2,12}-[a-z0-9]{4,8}$` (for
  example `piloto-7kq2`). The pattern is enforced by the model.
- `calculator` is checked when the event is validated against the names
  `get_calculation_declarations()` returns, plus the listed fixed values. The
  calculation catalog is the only owner of that list; a new calculation is
  accepted without editing the analytics registry.
- Technical properties, sent with every event and nothing else besides the
  event's own properties: `$process_person_profile` (always `false`),
  `schema_version`, `event_id`, `environment`, and `internal_account`
  (a boolean every caller must state; the sink refuses an envelope without one,
  and any technical value the registry did not set). `distinct_id` is `actor_hash_for_user(<user id>)`:
  the account id for signed-in users, the guest user id for guests.
  `guest_id_hash` is the same hash of the guest user id, so a guest's events
  and the account's `signed_in` join without person profiles or aliasing.
- Saved-query filter (SPEC 0, 0C-6): `environment = production` and
  `internal_account = false`, broken down by `cohort`.
- Retired: `evidence_capture`, `decision_capture`, `recall_usage`,
  `continuity_mismatch`, `compare_started`, `next_experiments_offered`,
  `next_experiment_selected`, `eval_readiness`, the `receipt_*` funnel,
  `account_registration_completed`, every guest funnel event, and the research
  settlement event no longer reach PostHog. Research work kind and outcome stay
  on the cost ledger (`capability_class`). The guest funnel milestone claim
  table stays and is reused by `first_answer_shown`.

Deferred durable surfaces:
- Eval run/case result persistence.
- Route-receipt to cost/eval/product-event joins beyond existing product
  records.

### refusal_observations and refusal_log

`refusal_observations` is private question/outcome evidence for the grounded-finance
board's Refusal log and rejected artifact actions (#314). It observes every
terminal chat reply so a boundary stated only in prose is retained too. A row
does not assert that its answer is a refusal, a bug, or a missing capability.
Those judgments belong to the reader; the writer adds no semantic taxonomy.

`RefusalObservation` in `src/argus/observability/refusal_log.py` is the frozen
Python write contract. Stored fields are:

- `id`: generated `uuid`; each rejected request receives an independent identity.
- `user_id`: verified actor `uuid`, references `profiles.id` ON DELETE CASCADE.
- `request_id`: supplied/generated request correlation `text`, never a dedupe key.
- `conversation_id`: nullable `text`. For rejected requests it is only the
  submitted claim; it may be malformed, nonexistent, or belong to someone else.
  It is not a foreign key and never authorizes or resolves an artifact.
- `request_message_id`, `response_message_id`: nullable `uuid` pointers to the
  exact canonical messages, both ON DELETE CASCADE. A terminal pair requires
  both pointers; `response_message_id` is unique to prevent repeat persistence
  from inflating frequency. The insert guard verifies the owner, conversation,
  user/assistant roles, and existing runtime turn identity when available.
- `asked`, `action`, `outcome`: nullable `text`, `jsonb` object, and `jsonb` object.
  Linked turns must leave them null because messages already own those facts.
  Requests rejected before message storage retain the submitted question,
  validated action, and original HTTP problem here, without rewriting the shape.
- `status_code`: actual transport status, `200` for accepted streams and `400`–`599`
  for rejected requests; this is not a semantic outcome category.
- `created_at`: insertion `timestamptz`.

`refusal_log` is a service-only view with `security_invoker = true`. It exposes
the same identity/status columns plus `asked`, `action`, `outcome`, and `response`.
For linked turns it reads exact user-message content, `metadata.chat_action`,
the full original assistant metadata, and assistant content. For rejected
requests it reads the retained question/action/problem and has no response
message. It never pairs by timestamp or joins rejected target claims.

RLS is enabled with no client policies. `PUBLIC`, `anon`, and `authenticated`
have no table or view access. The service role has table `INSERT`/`SELECT` and
view `SELECT` only; there is no update/delete API, frontend surface, model-context
projection, or PostHog export. Deleting either linked message removes its
observation; deleting the actor removes both linked and rejected observations.
Conversation deletion removes linked observations through message cascades.
Rejected observations follow actor deletion because their conversation id is
only a claim. A failed write logs only a content-free operational failure and
does not change the original response or allowance settlement.

Read frequency from existing outcome fields without assigning write-time labels:

```sql
-- Original clarification shapes, including successful-context rows with null codes.
select outcome #>> '{clarification,reason_code}' as reason_code, count(*)
from public.refusal_log
where created_at >= now() - interval '7 days'
  and response_message_id is not null
group by outcome #>> '{clarification,reason_code}'
order by count(*) desc;

-- Original rejected-action problems; repeated request ids still count separately.
select action ->> 'type' as action_type, status_code,
       outcome ->> 'code' as code, count(*)
from public.refusal_log
where created_at >= now() - interval '7 days' and status_code >= 400
group by action ->> 'type', status_code, outcome ->> 'code'
order by count(*) desc;

-- Read the actual question and response before judging whether Argus could answer.
select created_at, asked, action, outcome, response
from public.refusal_log
where created_at >= now() - interval '7 days'
order by created_at desc;
```

The additive migration is `20260908205041_add_refusal_observations.sql`.
Rollback removes the view, table, and its pair-validation function after removing
the observation hooks. No model-facing or public request/response contract changes.

### cost_ledger_entries

Append-only operational spend records. This table is the first-party source for
provider/runtime cost attribution; PostHog is not the spend ledger.

Fields:
- `id`: `uuid` (Primary Key)
- `source`: `text` (`api_turn`, `render_workflow`, `eval_harness`,
  `manual_reconciliation`, `runtime_compute`, `storage`, `market_data`, `stt`,
  `research`)
- `service`: `text` (billing service, e.g. `openrouter`, `render`, `supabase`)
- `provider`: `text` (provider inside the service, e.g. `openrouter`, `alpaca`,
  `kraken`, `openai`, `elevenlabs`)
- `model`: `text` (Nullable; LLM/STT model when applicable)
- `feature_area`: `text` (e.g. `chat_runtime`, `result_readout`,
  `eval_readiness`)
- `task`: `text` (Nullable; OpenRouter task or future runtime task)
- `user_id`: `uuid` (Nullable, references `profiles.id` ON DELETE SET NULL)
- `conversation_id`: `uuid` (Nullable, references `conversations.id` ON DELETE SET NULL)
- `message_id`: `uuid` (Nullable, references `messages.id` ON DELETE SET NULL)
- `backtest_run_id`: `uuid` (Nullable, references `backtest_runs.id` ON DELETE SET NULL)
- `backtest_job_id`: `uuid` (Nullable, references `backtest_jobs.id` ON DELETE SET NULL)
- `route_receipt_id`: `uuid` (Nullable, references `route_receipts.id` ON DELETE SET NULL)
- `request_id`: `text` (Nullable)
- `correlation_id`: `text` (Required; joins cost records to a turn, run, or eval)
- `provider_request_id`: `text` (Nullable; for providers that return request ids)
- `upstream_id`: `text` (Nullable; future reconciliation id)
- `usage_metadata`: `jsonb` (Default: `{}`)
- `input_tokens`, `output_tokens`, `total_tokens`: `integer` (Nullable)
- `billable_unit`: `text` (`token`, `request`, `compute_second`,
  `audio_second`, `storage_byte`, `row`, `unknown`)
- `billable_quantity`: `numeric` (Nullable)
- `cost_amount`: `numeric` (Nullable)
- `cost_currency`: `text` (Default: `USD`)
- `cost_source`: `text` (`provider_reported`, `estimated`, `derived`,
  `reconciled`, `unavailable`)
- `latency_ms`: `integer` (Nullable)
- `status`: `text` (`succeeded`, `failed`, `skipped`, `estimated`,
  `reconciled`); nullable only for `source = "research"` and
  `feature_area = "research_rail"`, whose new rows always carry SQL NULL.
  Legacy discovery rows and other sources still require status.
- `metadata`: `jsonb` (Default: `{}`)
- `occurred_at`: `timestamptz`
- `created_at`: `timestamptz`

Append-only rules:
- Product code may insert rows only. There are no update, upsert, delete, or
  frontend read paths in the private-alpha slice.
- The migration grants service-role `insert` and `select` only. RLS is enabled,
  and no `anon` or `authenticated` policies are added.
- Writer rollbacks retain the ledger table and its permanent rows.

Current write hooks:
- The shared insert normalizer owns the research-rail status retirement:
  capability-class turns and invoice anomalies carry null status and
  `metadata.research_ledger_contract = "argus_research_ledger/v2"`.
  Detailed outcome/cache/pricing fields are unchanged. Legacy discovery
  retains its `fallback_code`-derived status and receives no new marker.
  Existing unversioned rows are left untouched, not reinterpreted or backfilled.
  Migration `20260909225701` follows the sharing migration `20260909183646`.
  Its `DROP NOT NULL` is classified destructive by the promotion gate, despite
  deleting no object and rewriting no row; the founder applies it at promotion
  before deploying the new writer. The database default remains for legacy
  writers. Roll back application code only; retain the nullable schema and
  existing versioned rows instead of rewriting history to restore NOT NULL.
- Unreconciled Perplexity Agent responses append an anomaly row at the response
  boundary, correlated for invoice reconciliation by provider response id. They have
  `cost_amount = null`, `cost_source = "unavailable"`, and
  `usage_metadata.pricing_status = "unpriced"`; reported components and the
  failed comparison's expected range remain in `usage_metadata`. The answer's
  success is independent of invoice reconciliation. Anomaly rows have unknown
  billable quantity and no cost amount; existing capability-class turn metering
  remains unchanged. Both records retain null cost for an unpriced call.
  An attempt the provider may have billed without answering, after a read
  timeout or a connection dropped mid-request, appends the same anomaly row
  with `usage_metadata.reason = "unanswered_attempt"`, null usage counts and a
  null provider response id.
  Tool invocation counts inside `usage_metadata` are null when the invoice did
  not establish them; a null count is unknown, not zero.
- API chat turns append OpenRouter cost rows from persisted route receipts.
- Grounded-discovery turns append one `source = "research"` row per attempted
  Search call with `feature_area = "discovery"`, provider identity, latency,
  and provider-reported or documented cost.
- Render workflow result-readout LLM calls append rows correlated to
  `backtest_job_id` and `backtest_run_id`.
- Eval harness judge calls can append rows with `source = "eval_harness"` and a
  stable eval correlation id.

Cost model notes:
- OpenRouter rows store provider-reported `usage.cost` when available and token
  counts in both dedicated columns and `usage_metadata`.
- Render, Supabase, market-data providers, STT providers, research/freshness
  providers, and future broker/export services may bill by request, compute
  time, storage, rows, audio duration, or provider reconciliation ids. The
  `billable_unit`, `billable_quantity`, `cost_source`, `provider_request_id`,
  and `upstream_id` fields are intentionally generic so those services can be
  added without changing the private-alpha chat runtime.
- Cost rows never store raw prompts, transcripts, credentials, balances,
  holdings, full audio, or frontend-only payloads.

## 12.1.3 public_excerpt_snapshots

A public evidence receipt: an immutable, sanitized snapshot of one or more
eligible answers selected from one conversation, created by a registered owner
and revocable by that owner. This extends the existing receipt table behind the
default-off `ARGUS_EVIDENCE_RECEIPT_SHARING_ENABLED` flag.

The pipeline is `owned assistant messages -> PublicExcerptSnapshot ->
PublicExcerptView`. Backtest messages resolve their canonical EvidenceArtifact
and run through this same boundary. The artifact endpoint is a compatibility
adapter to that same selection service and singleton identity. The header opens
the sole user-facing selection flow. Existing live version 1 receipts are reused
unchanged.

The snapshot is frozen at creation and the public read never queries the source
conversation, message, run or provider. Asking again or rerunning produces new
source material and leaves the earlier receipt unchanged.

### Receiver copies (founder-locked 2026-09-14)

A first follow-up creates a receiver-owned conversation and ordinary message rows
from the frozen public payload, inside one transaction. No new table, column or
migration is needed. Receipt rows and their source deletion/revocation lifecycle
are unchanged. The transaction serializes fork admission with revocation and uses
receiver/request retry identity to create exactly one copy. A receiver copy has
no source-conversation foreign key, so later revoke/delete keeps its copied text.
Replay matches the imported request id within current message and conversation
ownership. It does not derive replay identity from the current owner's user id:
the existing guest handoff transfers ownership without changing message IDs or
the imported request metadata, so the permanent account reuses the same copy.

Imported message metadata uses `shared_conversation` with `snapshot_at`, public
receipt id, request id, turn index, and the assistant's frozen public `card` where
present. These fields are provenance and retry identity, never analytics viewer
identity or live run/confirmation/calculation handles. All owner notes are removed,
including notes on individual turns. Normal history readers include the carried
user/assistant content; naming excludes imported messages. No runs, interests,
memory records, usage records, or owner activity are imported. Cards render only
frozen public fields and cannot be edited or recomputed in place.
Runtime history derives internal carried-context provenance from this metadata.
One selection rule retains that bounded context alongside the normal recent
receiver turns; provider messages still contain ordinary roles and content only.

Total ordinary history text is bounded at 64 KiB UTF-8, and total carried text and
card metadata at 512 KiB. Oversized public facts fail before any write or guest
replacement. Guest copies use the existing workspace, explicit nonempty-chat
replacement choice, unchanged counters/expiry and existing signup transfer.
Count-only followed-up and signed-up stages add no viewer identifier.

Fields:
- `id`: `uuid` (Primary Key)
- `public_id`: `text` (Unique, `^[A-Za-z0-9_-]{22,64}$`, 24 bytes of urlsafe
  entropy; this is the url token)
- `owner_id`: `uuid` (References `profiles.id` ON DELETE CASCADE)
- `evidence_artifact_id`: `uuid` (Nullable, references `evidence_artifacts.id`
  ON DELETE SET NULL)
- `source_conversation_id`: `uuid` (Nullable, references `conversations.id`
  ON DELETE SET NULL)
- `source_run_id`: `uuid` (Nullable, references `backtest_runs.id`
  ON DELETE SET NULL)
- `kind`: `text` (`backtest`, `research_answer`, `calculation`, `answer`, or `mixed`;
  existing rows default to `backtest`; migration
  `20260912190000_share_calculation_receipts.sql` added `calculation` to the
  check additively; `20260914120000_share_plain_answer_receipts.sql` adds
  `answer` using the same check and must be applied at promotion)
- `source_message_ids`: `uuid[]` (Private selected assistant messages; one or more
  for new receipts, empty for legacy rows)
- `source_run_ids`, `source_artifact_ids`: `uuid[]` (Private selected backtest
  sources)
- `selection_key`: `text` (Nullable for legacy rows; canonical sha256 selection
  identity, independent of note and payload content)
- `title`: `text`
- `payload`: `jsonb` (the closed public payload; see below)
- `payload_digest`: `text` (`^[0-9a-f]{64}$`, sha256 over the canonical payload)
- `created_at`: `timestamptz`
- `revoked_at`: `timestamptz` (Nullable)
- `revocation_reason`: `text` (Nullable, `owner_revoked`, `source_deleted`, or
  `removed_by_argus`)

The legacy scalar source references are `ON DELETE SET NULL` rather than cascade
so a tombstone outlives whatever it pointed at. The new private source arrays are
immutable provenance; insert and deletion triggers enforce their ownership and
liveness. These source identifiers never enter the public read or public payload.

### Closed payload

Version 1 `payload` carries exactly these keys and no others, enforced by `extra="forbid"`
on every model in `argus.api.public_excerpt_schemas`: `schema_version`,
`idea_title`, `asset_class`, `symbols`, `strategy_facts`, `assumptions`,
`date_range`, `metrics`, `benchmark_symbol`, `visual`, `owner_note`,
`content_language`, `framing`, `provenance_mark`.

Version 2 is a closed outer `{schema_version: 2, kind: "turns", turns: [...]}`
wrapper. It contains one or more per-turn payloads in conversation order. Each
turn has a closed `kind` discriminator. The active frozen-field policy is in
`docs/specs/conversation-sharing.md` section 4.2. Plain final answers use `answer`;
research keeps any available typed sources and dates without requiring them. New
backtest leaves also freeze question and final answer text; optional fields keep
older version 2 rows readable. The backtest leaf freezes the card's closed typed
fact bank, title, visual, note,
content language, framing and provenance. `public_excerpt_fact_schemas.py` closes
every nested config, rule, figure and cost field. The public renderer reads the
same result fact and display owners as the result card.

The calculation leaf is `{kind: "calculation", question, title, answer, rows,
inputs, notes, computed_at, owner_note, content_language, framing:
"calculation_not_advice", provenance_mark}` for one calculation. For an answer
that weighs options it carries `calculations: [{title, answer, rows, inputs,
notes}, ...]` in place of those five fields, one per card in order; every card
uses the closed public presentation, and a leaf frozen in the first shape
still renders. New leaves additionally retain the selected final answer text. The title and every label, unit,
`value_text` and note is `{locale_key, interpolation_args}`. A fact is `{label,
value, value_text, unit, source}`, where `source` is `{title, url, date}` and
exists only for a page. `inputs` holds explicitly public/page-sourced inputs and user-written inputs
selected through the owner preview. Hidden account or memory inputs are not
added. Raw card `arguments` and its visual never enter the payload. The receipt freezes those facts at creation
and never recomputes.

Every selected final answer independently passes the shared completion,
ownership and exact private Argus identifier audit at preview and creation.
Credential shape, missing sources, unlisted links, question/answer length,
degraded output and memory use are not refusal reasons. Confirmations and
clarifications are not sharing units. A refusal refuses the entire selection. The owner sees
the exact public rendering before creation; its digest must still match when
creation rechecks the sources. The preview bounds the accepted cross-turn
inference risk; it does not eliminate it.

Source conversation ids, route receipts, provider or model metadata, retry
payloads, unselected transcript content, broker or account data, and user-private
memory are never present. `argus.domain.public_excerpts.audit_public_excerpt_payload` audits
keys and values before any receipt is written and fails closed, so a payload that
cannot be proven clean is never stored.

### Version 1 display values remain unchanged

The version 1 backtest payload freezes typed facts rather than rendered labels.
`strategy_facts`, `assumptions`, and `metrics` are each a list of `{key, value}`
under a closed key enum (`StrategyFactKey`, `AssumptionKey`, `MetricKey`), where
`value` is the bare scalar the run reported, and `date_range` is `{start, end}` as
ISO dates. Labels, sentences, thousands separators, and date formats are all
composed by the client in the reader's language. There is deliberately no label
field, no rendered `display` string, and no free-text passthrough anywhere in the
list models.

`assumptions` keys are `long_only`, `equal_weight`, `no_costs`, `modeled_fee_bps`,
`modeled_slippage_bps`, `benchmark`, `benchmark_same_modeled_costs`,
`recurring_contribution`, `contribution_cadence`, `starting_principal`, and
`fractional_shares`. The four recurring keys are read together from the run's
declared capital plan, so the receipt states the same two money roles and the
same fill model the engine executed; `starting_principal` keeps its frozen
public name while the plan owns what that number is. Costs are read from the
frozen run config rather than through the live execution-realism flag, so a flag
flipped after the run cannot rewrite what the receipt says the run assumed.

`MetricKey` is `cash_value`, `total_return_pct`, `max_drawdown_pct`, `win_rate`,
`benchmark_return_pct`, and `delta_vs_benchmark_pct`. The first four are the result
card's own row keys. The card's `benchmark_delta` row is deliberately not carried
under its own key, because its value is a rendered sentence rather than a number;
the last two are read from the run's `metrics.aggregate.performance` instead, so
the comparison survives as figures the page can speak in either language. Values
are the run's own display strings, except `delta_vs_benchmark_pct`, which is a bare
signed number because its unit is percentage points and every way of writing that
unit is a word.

A metric key the projection does not know is refused, not dropped, and a payload
that names a `benchmark_symbol` must carry a benchmark figure. Dropping is how the
comparison could disappear from a receipt while the page went on naming a
benchmark. Likewise a run whose assumptions or tested window will not project is
refused rather than published with the prose the run happened to freeze.

### Reading a stored payload

The public read validates stored JSON against this model, and `extra="forbid"`
means a row written by a different shape raises rather than degrades. That path
answers `503` with `Retry-After`, which the viewer's page reads as temporarily
unavailable. It deliberately does not answer with the tombstone: the row is
intact, so saying the receipt is gone for good would be a permanent-sounding lie
about a live link. Owner-side reads are not wrapped this way; an owner's list is
the only place a receipt can be revoked, so a row it cannot parse should surface
loudly rather than vanish from that list.

Version 1 author text remains `idea_title` and `owner_note`. A research leaf also
carries its whitespace-normalized question (at most 500 characters) and answer
markdown (at most 4,000). A note is bounded at 280. Each field is audited and
refused with a named field if it contains an identifier, credential shape, private
id or never-expose marker. Answers with prose URLs absent verbatim from typed
sources are refused. No redaction or truncation repairs an ineligible answer.
`content_language` names the author's language; reader chrome remains live.

`visual` freezes the run's equity series, downsampled to at most 500 points with
the endpoints preserved. The public view renders it client side; nothing is
fetched at view time.

### Immutability and revocation

`prevent_public_excerpt_immutable_update` rejects any change to `id`,
`public_id`, `owner_id`, `title`, `payload`, `payload_digest`, or `created_at`,
and also freezes `kind`, `selection_key` and the private source arrays. It
rejects any change to the revocation columns once `revoked_at` is set.
Revocation is one way.

`enforce_public_excerpt_source_is_live` refuses an insert whose source conversation
is soft-deleted or gone. Revocation-on-delete only revokes snapshots that exist when
`deleted_at` changes, so without this a stale result card, or a create racing behind
the delete, could publish a page for a conversation the owner had already removed.
The trigger takes `FOR SHARE` on the conversation row, which is the part an
application check cannot do: a check-then-insert could pass and have the delete
commit before the insert lands, whereas the lock makes a concurrent soft delete block
the insert, which then reads the delete's result and refuses.

For selected turns, the same insert trigger locks and verifies every named
assistant message, run and artifact against the same owner and conversation.
It acquires source locks in deterministic order. No selected source can disappear
between an application check and publication without either refusing creation or
revoking the snapshot.

`revoke_public_excerpts_for_deleted_source` revokes a receipt when its source
goes away, so deleting a chat cannot leave a live public page behind:
- `conversations` soft delete (`deleted_at` null to not null)
- `conversations`, `messages`, `backtest_runs`, or `evidence_artifacts` hard delete;
  every selected source participates, not only the first turn

Every branch skips rows whose owner profile is already gone. Account deletion
cascades to conversations and fires the purge trigger while the profile no longer
exists; revoking there would fail the owner foreign key and take account deletion
with it. Those rows are cascade-deleted moments later, reaching the same outcome.

A partial unique index on `(owner_id, evidence_artifact_id) where revoked_at is
null` allows at most one live receipt per result, so re-sharing returns the
existing link instead of minting a second page the owner must revoke twice.
Revoked rows are excluded, so revoking does not forbid sharing that result again.
A second partial unique index on `(owner_id, selection_key)` gives all new
selections the same insert-race recovery. A new singleton backtest retains its
artifact identity too, so the compatibility endpoint and message selection return
the same live record. A different multi-turn selection is a different receipt.

Note a pre-existing constraint: a conversation with a captured idea spine cannot
be hard deleted at all, because `idea_versions.source_conversation_id` is
`ON DELETE SET NULL` while `prevent_idea_version_immutable_update` forbids
changing that column. Argus only soft deletes conversations, so this never
surfaces in the product; the purge triggers are a backstop, not the live path.

### RLS

Row level security is enabled and there is deliberately **no** policy and **no**
grant for `anon` or `authenticated`. Neither the public read nor the owner's list
goes through the browser: both are served by the backend, which is where the
audience split is enforced. The public read selects only
`public_id, payload, created_at, revoked_at`. A select policy without a matching
grant would be dead code that reads like protection, and adding the grant would
put the owner and source columns one PostgREST call away from the browser.

## 12.1.2 Memory Persistence Incubation

Memory is an isolated, no-consumer persistence checkpoint. It
does not change P2 recall, Omnisearch, canonical Ideas, EvidenceArtifacts,
DecisionNotes, conversations, backtests, LangGraph state, or ordinary Guest
chat. Product exposure, API wiring, runtime retrieval, Data Controls, providers,
analytics, and hosted-database application remain closed.

Memory is registered-account-only and off by absence. Supabase Auth and
`guest_workspaces` are the database-canonical eligibility boundary:

- `auth.users.is_anonymous` must be false;
- no same-identity Guest workspace may be `active` or `claiming`;
- browser/Data API roles (`PUBLIC`, `anon`, `authenticated`, and
  `service_role`) have no direct table or sequence privileges;
- a fixed-search-path private predicate is called by every memory-table insert
  and update trigger;
- owner identity is immutable; forged JWT claims cannot replace Auth/workspace
  truth.

All memory tables have RLS enabled and forced, with no client policies. The
private backend Postgres adapter is the only intended access path and must
still derive a registered owner from a verified request before entering the
store.

### Canonical and derivative tables

- `memory_settings`: one enabled category row per owner. No rows means memory is
  disabled. Categories are closed to personalization preference, workflow
  preference, explicit decision note, and past-session anchor.
- `memory_candidates`: bounded pending proposal content, trigger/context,
  exact opt-in scope, and sensitivity-policy digest. A candidate is not a
  durable memory.
- `memory_consent_actions`: immutable direct-enable or
  candidate-confirmation evidence with exact requested, granted, and effective
  scopes plus schema/policy versions and idempotency identity. Direct enable
  has no candidate and grants a non-empty scope. Confirmation requires an
  existing same-owner candidate whose category appears in the requested scope.
- `memory_records`: confirmed canonical label/value state. The owner, candidate,
  consent action, category, and creation identity are immutable. An edit may
  change only label/value with the next positive revision and a later
  `updated_at`.
- `memory_provenance`: immutable, ordered owner-scoped pointers attached to
  exactly one candidate or record. Source kinds are closed to Argus-owned
  EvidenceArtifact, DecisionNote, Idea, IdeaVersion, Conversation, and Message
  identities.
- `memory_prompt_history`: category-scoped proactive-prompt and decline
  timestamps used for durable cooldown/suppression decisions.
- `memory_reconciliations`: positive, ordered provider-projection work
  generations. Rows start pending, then move through an exact leased claim to
  running before reaching immutable succeeded/failed terminal state. The claim
  token, expiry, and attempt count make restart recovery inspectable: a live
  lease cannot be stolen, an expired lease may be reclaimed with a new token,
  and only the exact, unexpired current claim may commit a provider pointer or
  terminal outcome. Terminal rows erase the bearer token and lease. Lower
  unfinished generations cause a bounded, lock-free wait before later work for
  the same record, while other owners remain independent. Unfinished work
  restricts record deletion so derivative cleanup cannot disappear silently.
  Owner-wide reset uses the reserved `operation = reset`, `record_id = ''`
  sentinel. Record operations require a non-empty record id. Reset first
  removes canonical and user-visible memory, snapshots every provider pointer
  into cleanup, and retains one retryable reset generation. Failed attempts
  remain terminal evidence; a retry appends the next generation, while a crash
  before a terminal outcome reuses or reclaims the unfinished generation.
  While reset metadata remains unresolved, fresh canonical memory may be
  confirmed after a new opt-in but record-specific provider work cannot claim
  a lease. A later reset recognizes the existing owner-reset history and
  atomically supersedes that post-reset canonical work instead of waiting on
  its intentionally blocked provider reconciliation. The first reset still
  performs a bounded wait for genuine pre-reset provider work.
- `memory_provider_projections`: the current derivative provider pointer and
  positive generation for a canonical record. A provider pointer is unique per
  owner but may be reused independently by another owner. Replacements are
  atomic with a durable cleanup snapshot of the prior pointer.
- `memory_provider_cleanup`: durable, owner-scoped cleanup targets that survive
  canonical record deletion and process restarts. Rows begin pending, may move
  only once to resolved, and never reopen; a successful resolution also removes
  the matching same-record projection when it still exists. Bounded reads
  return at most 100 unique pending targets in deterministic newest-first
  order. Cleanup scheduling refuses a pointer currently projected by another
  record for the same owner, preventing deletion of live reused provider state.
  While any cleanup row remains pending, its `(owner_id, provider_ref)` is a
  fail-closed reservation: neither application code nor direct SQL may assign
  that pointer to a live projection. The reservation ends only when cleanup is
  resolved.
  Provider pointers are derivative identifiers, never canonical memory content.

An owner reset calls any derivative provider only after the canonical
transaction commits and only when cleanup exists. A synchronized provider
result may clear cleanup, projections, and reset metadata only with the exact
unexpired reset claim. Provider failure, malformed output, or
`not_applicable` retains cleanup for retry. Completion never deletes canonical
records created after the earlier reset.

Composite foreign keys include `owner_id` at every live relationship so a
candidate, consent action, record, provenance row, reconciliation, or provider
projection cannot cross owners. Candidate-confirmation receipts survive
candidate consumption; records link to the immutable receipt by owner,
candidate identity, and receipt identity. Account deletion cascades the full
owner state, including durable cleanup targets.

### Guest conversion zero state

Memory never enters the Guest transfer graph. A `BEFORE UPDATE` trigger on
`guest_workspaces` counts all nine memory tables when an `active`/`claiming`
workspace moves to `claimed`. Any row blocks both same-identity link and
existing-account handoff, and the surrounding conversion transaction rolls
back without transferring memory. A clean conversion carries zero memory,
performs no retrospective extraction, and leaves personalization disabled until
the registered user later completes a fresh scoped opt-in.

## 12.1.4 Financial accounts (first slice)

Registered-only, behind `ARGUS_FINANCIAL_ACCOUNTS_ENABLED`. Spec:
[`docs/specs/lanes/financial-accounts-first-slice.md`](specs/lanes/financial-accounts-first-slice.md).
Migration `20260928200000_financial_accounts_first_slice.sql`. Ownership is one
fact, `financial_accounts.user_id`; records and revisions carry a copy for
indexed RLS, and composite foreign keys `(account_id, user_id)` and
`(record_id, user_id)` force the copies to agree with the account.

### financial_accounts

| Field | Rule |
| --- | --- |
| `id` | uuid, server-assigned, stable across nickname, archive and edits |
| `user_id` | owner, `auth.users(id)` on delete cascade |
| `space_id` | text, default `personal`; household sharing uses explicit grants and does not rewrite this field |
| `type` | one of the nine account types; nature derives from it in code and is never stored |
| `currency` | ISO 4217 code, `^[A-Z]{3}$`; accepted set is the CLDR tender set in code |
| `nickname` | null or 1–60 characters, trimmed by the domain |
| `archived` | boolean, organizational only |
| `ownership_share_bps` | 1–10,000, default 10,000; never a permission |
| `version` | starts at 1; every account edit, opening write and correction increments it; the edit's compare-and-set key |
| `created_at`, `updated_at` | `set_updated_at()` trigger |

### financial_records

One row per confirmed record. This slice writes only `record_kind =
'opening_balance'`, at most one per account (partial unique index).
`current_revision` is the correction compare-and-set key.

### financial_record_revisions

Append-only. `(record_id, revision)` unique. Each row stores the owner-signed
`amount_minor` (bigint), `as_of` (timestamptz) with `as_of_zone` (IANA),
optional `reason` (1–200 characters; null on revision 1), `capture_method`
(`manual` only in this slice), `recorded_by` (`auth.users` on delete set null,
so history keeps its row when an author is later deleted) and `recorded_at`.
Balances are derived on read from the current revision; nothing derived is
stored.

### financial_account_idempotency

The create reservation, keyed `(user_id, operation_scope, idempotency_key)`
with `operation_scope = 'financial_accounts.create'`, `identity_hash` and the
`account_id` it produced. Same key and identity replays; a different identity
conflicts. Rows cascade with their account.

### Functions

- `create_financial_account(...)` writes the account, its opening record and
  revision 1, and the reservation in one transaction. A concurrent duplicate
  blocks on the reservation primary key and then re-reads to replay or
  conflict. It returns `registered_required` for an anonymous `auth.users` row.
- `write_financial_opening(...)` locks the account, compares the caller's
  `expected_version` (the account version the client saw when composing the
  write) and the caller's `expected_revision` (null when no opening exists) with
  the locked row, and either appends the next revision and bumps `version`
  or returns `stale` having written nothing.

Both are `security definer`, executable by `service_role` only. The API calls
them over `DATABASE_URL`; there is no client write path.

### Complete financial loop extension

Migration `20260929090000_financial_loop.sql` extends these same records with
`expense` and `balance_check`; it does not add a parallel ledger. The canonical
wire and review behavior is [the complete financial loop contract](API_CONTRACT.md#complete-financial-loop-authorized-september-29-2026).

`financial_record_revisions.details` holds typed kind-specific facts. Expense
revisions store optional note/category beside the existing signed amount/date,
reason, actor and timestamp. The domain exposes positive expense amounts while
the durable movement is negative. Check revisions store immutable confirmation
expected amount, difference, reviewed account version, source, kind and optional
note. The observed signed amount/date use the existing columns. Check sequence
is the strictly increasing reviewed account version; local-day admission prevents
backdated insertion in this build. Opening remains one stable record with revisions.

`financial_observation_coverage` binds exact observation and activity revisions.
Its composite keys enforce the same account and owner through both records and
revisions. Each row records an explicit `included` fact. Correction writes new
coverage rows beside the new revision, retaining earlier choices. New checks
capture the currently known eligible activity. Current balance and unexplained
residuals derive in `domain/recording/loop.py`; confirmation facts are not replaced
when later activity explains a difference. No recording-order timestamp substitutes
for a source financial date.

`financial_operation_receipts` binds owner/account/idempotency key to the accepted
record/revision and request hash. The Postgres repository locks the account,
checks registered ownership, replays an existing receipt before CAS, then appends
record/revision/coverage and receipt atomically. An exception rolls back every
write. All money decisions remain in the shared domain, not repeated in SQL.
Metadata edits bind validation and CAS to the same caller-visible version.
Read snapshots use repeatable-read transactions; mutations hydrate under their
account lock. Native clients have no write grant. Coverage has registered-owner
SELECT RLS; receipts have no client read policy or grant.

Home derives currency-separated personal-position subtotals from that same read.
Its aggregate minor units are exact decimal-integer strings; single-account
positions, activity totals and residuals are checked within Int64 before commit.
Unknown positions remain absent from known subtotals and explicitly counted.
Archived accounts retain their money in this projection.


## 12.1.5 Households (membership, invitations, grants)

The landed `20261001090000_household_membership.sql` is extended by
`20261001120000_household_consent_recovery.sql`, behind default-off
`ARGUS_HOUSEHOLDS_ENABLED`. These remain the only Household membership tables.
Financial ownership stays `financial_accounts.user_id`; no share changes
`space_id`, financial ownership, or the Personal owner-only RLS policies.

`households.version` is a positive CAS/authorization generation. Scoped commands
serialize under the household row lock; financial adapters then acquire the
existing Recording owner/account locks. `household_members.id` is the membership
incarnation: leave/removal sets `left_at`, and a fresh invite creates a new ID.
Members carry a user-supplied `display_name`; administrator authority remains
`households.admin_user_id`, not a second stored role.

`household_invitations` stores only a token hash and seven-day UTC expiry.
`accepted_membership_id` binds same-recipient retries to the original membership,
including after departure, closure and rejoin. Historical accepted memberships
are backfilled where the invitation acceptance timestamp identifies the row.
Unresolvable historical outcomes fail closed. Token plaintext is returned once.
The short typed code is not stored on this table: its keyed digest lives in
`argus_private.invite_code_digests` (below), and plaintext is returned once.

`argus_private.invite_code_digests` (migration
`20261003150100_invite_code_digests_private.sql`, #789) holds one row per typed
code: `digest` (primary key, `v2.<key id>.<HMAC-SHA-256 hex>` under
`ARGUS_INVITE_CODE_SECRET`, enforced by a check), exactly one of
`household_invitation_id` or `beta_invitation_id` (unique, cascading), `created_at`
and `rehashed_at` (set when a code found under the previous secret moves to the
current one). The schema is unreachable for anon and authenticated; the table has
RLS with no policy and no privilege for anon, authenticated or service_role.
Only the backend database owner reads it. The earlier `code_hash` columns on
`household_invitations` and `beta_invitations` are dropped.

`beta_invitations` holds beta invites (`kind='beta'`, `max_uses=1`) and founder
group links (`kind='group_link'`, a `source_label`, a cap in `max_uses`, an
expiry, `use_count` and `overflow_count`). Creation is idempotent on
`(created_by, idempotency_key)` with a request hash. `invite_referrals` is the
who-invited-whom record: one row per beta or household invitation and one row
per group-link redemption, with `kind`, `inviter_origin_id` (the row that
admitted the sender), a random `sender_ref`, and live `sender_user_id` and
`acceptor_user_id`. Live ids use `ON DELETE SET NULL`; the `invite_sender_refs`
mapping cascades, so after a deletion the row identifies nobody while counts
and the chain survive. `beta_admissions` has one row per admitted person
(`via` beta invitation, group link, household invitation, or an account that
existed when the migration ran) and cascades with the account.
`beta_invite_quota_grants` records founder grants above the 10 beta invites.
All five tables have RLS on, explicit per-command policies (owner-scoped
select, no client insert, update or delete) and every client privilege revoked;
only the API service reads and writes them.

Each active `household_account_grants` row binds `owner_membership_id` and
`recipient_membership_id` in the same household. The owner composite FK also
binds `owner_user_id`; the financial account composite FK preserves original
ownership. The unique active key is `(household_id,account_id,recipient_membership_id)`.
`permission` is the sole view/edit fact. There is no global editable permission
beside a recipient permission. Projections deduplicate these grant rows by
account. Departure revokes both directions of consent; closure revokes all.
All old unbound grant rows are preserved but revoked by the extension migration:
no migration invents named consent. Future sharing requires an explicit choice.

`household_command_receipts` has primary key `(actor_id,operation,idempotency_key)`
and stores canonical body hash, household ID, original membership ID and optional
invitation ID. It stores neither capabilities nor protected snapshots. Exact
retry returns only current state of that original outcome; invite replay returns
token-null metadata under current admin authorization. Financial receipts remain
Recording-owned, with actor/household/membership-qualified scope and live grant
checks before replay. Committed financial receipts replay before rejecting an
old Household generation; generation checks continue to protect new writes.
All Household authorization tables and receipts are
service-owned, RLS-enabled, with no direct anon/authenticated table grants.

Financial records and legitimate activity survive leave/removal/closure.
The forward `20261001130000_household_grant_deletion.sql` migration makes both
membership-bound grant FKs cascade on membership deletion. Leave, removal and
closure continue to preserve revoked grant rows; deleting an auth user removes
the authorization edges referencing their deleted membership. It never deletes
another owner's financial accounts or legitimate record history. Historical
identity FKs retain the landed deletion behavior. Closing a household
is explicit; an administrator transfers authority to a current member or closes
before leaving. API shapes and read redaction are owned by
[API_CONTRACT.md](API_CONTRACT.md#174-households-canonical-membership-and-financial-adapters).

## 12.2 backtest_jobs

Represents durable lifecycle state for a backtest execution job. Jobs bridge
the chat/API control plane to asynchronous Render Workflow execution and also
own the admitted synchronous direct compatibility path.

`backtest_jobs` is not the canonical result record. Successful jobs write a
canonical immutable `backtest_runs` row and reference it through
`result_run_id`.

### Fields
- `id`: `uuid` (Primary Key)
- `user_id`: `uuid` (References `profiles.id`)
- `conversation_id`: `uuid` (Null for direct `backtests.run` admission and for
  every `workflows.proof` row; otherwise references `conversations.id`)
- `request_message_id`: `uuid` (Nullable, references `messages.id`)
- `confirmation_message_id`: `uuid` (Required for `chat.run_backtest`, null for
  `backtests.run`; references the retained immutable confirmation `messages.id`)
- `operation_scope`: `text` (`chat.run_backtest`, `backtests.run`,
  `chat.research`, or `workflows.proof`)
- `idempotency_key`: `text` (Required for every current writer. Accepted jobs
  use the caller's 1-128 visible ASCII reservation key; terminal pre-start
  receipts use a distinct derived `rejection:<hash>` key. Legacy rows may be
  null.)
- `identity_hash`: `text` (`sha256:` plus 64 lowercase hex characters for the
  operation's canonical identity object)
- `payload_hash`: `text` (`sha256:` plus 64 lowercase hex characters for the
  full normalized `LaunchBacktestRequest` payload)
- `launch_payload`: `jsonb`
- `status`: `text`
- `priority`: `text` (Default: `'normal'`)
- `attempts`: `integer` (Default: `0`)
- `max_attempts`: `integer` (Default: `1`)
- `queued_at`: `timestamptz` (Required for chat jobs; null for conforming direct
  jobs that never enter `queued`)
- `started_at`: `timestamptz` (Nullable)
- `finished_at`: `timestamptz` (Nullable)
- `result_run_id`: `uuid` (Nullable, references `backtest_runs.id`)
- `failure_code`: `text` (Nullable)
- `failure_detail`: `text` (Nullable)
- `retryable`: `boolean` (Default: `false`)
- `execution_metadata`: `jsonb` (Default: `{}`)
- `created_at`: `timestamptz`
- `updated_at`: `timestamptz`

### Enums
- **status**: `queued`, `running`, `succeeded`, `failed`, `canceled`, `expired`
- **operation_scope**: `chat.run_backtest`, `backtests.run`, `chat.research`,
  `workflows.proof` (thorough research runs ride this same lifecycle; a
  succeeded research job keeps `result_run_id` null and references its answer
  message through `execution_metadata.research_result_message_id`. A
  `workflows.proof` row is the Render workflow runtime proof seeded by
  `workflows/proof.py` for the canary: it is not conversation work, carries no
  conversation, no request or confirmation message, and no run, and is never
  admitted through the API. Because every conversation activity reader joins
  jobs to a conversation, a proof row cannot project as activity; before this
  scope existed the seeder inherited the `chat.run_backtest` column default
  and each proof projected a conversation as `checking` forever.)
- **priority**: `normal` initially; future values may support admin or canary
  jobs.
- A new `chat.run_backtest` row starts `queued` with `queued_at` set and
  `started_at` null. Its `confirmation_message_id` is non-null and the linked
  message owns the confirmed `confirmation_id` and full `launch_payload_hash`
  for the job record's lifetime. A new `backtests.run` row starts `running` with
  `queued_at` and `confirmation_message_id` null and `started_at` set to the
  admission transaction timestamp.
- A refused chat attempt is inserted directly as `failed`, with
  a distinct `rejection:<hash>` idempotency key, `started_at` null, and
  `finished_at` set. Its
  `identity_hash`, `payload_hash`, and `launch_payload` describe the attempted
  run; `execution_metadata` records the rejected key and admission decision.
  It never owns the rejected confirmation's reservation, consumes allowance,
  or occupies capacity.

### Failure Semantics
Job lifecycle status is separate from engine/runtime failure semantics.

- `status` answers where the job is in its lifecycle.
- `failure_code` is a stable machine code such as `market_data_unavailable`,
  `invalid_date_range`, `unsupported_indicator`, `workflow_timeout`, or
  `idempotency_conflict`.
- `failure_detail` is a user-safe grouping such as `market_data_issue`,
  `invalid_date_window`, `unsupported_rule`, or `execution_failed`.
- `retryable` is computed from the failure category, failure code, attempts, and
  whether an intent-preserving corrected payload exists.
- `execution_metadata` may store private operational evidence such as workflow
  run id, cache hit/miss, provider fetch duration, compute duration, attempt
  count, and source error kind.
- `succeeded` is valid only after the job's result is readable in its
  conversation: for a backtest, `result_run_id` links to the fully finalized
  run/evidence tuple; for a `chat.research` job, which has no run by design,
  `execution_metadata.research_result_message_id` names the persisted
  assistant answer (written before the row flips). That rule has one owner,
  `argus.domain.job_settlement`, from which the SQL settle predicate
  `argus_private.backtest_job_result_hydrateable` is rendered; a succeeded row
  the rule cannot hydrate projects as `checking`, which clients treat as a
  working lock. A failed research row names its persisted failure note the
  same way. A recoverable persistence-side failure uses
  `status = failed`, `failure_code = finalization_failed`, and
  `retryable = true`; `result_run_id` remains null until retry finalizes the
  stable run identity. `finalization_failed` is a failure code, not a new job
  status.

Unknown failures default to `failed`, `failed_internal` semantics,
`retryable=false`, and a safe generic user message until a new stable
`failure_code` is intentionally added.

A direct `backtests.run` row becomes stale when it remains `running` through
`started_at + interval '15 minutes'`. Before new direct admission and before an
owner-scoped direct-job read, the database-owned recovery path checks the stable
job-derived identity for a fully finalized Run/evidence tuple. A complete tuple
reconciles the job to `succeeded`. With no complete tuple, the same transaction
sets `status = failed`, `failure_code = direct_execution_abandoned`,
`failure_detail = execution_interrupted`, and `retryable = true`. Both terminal
transitions release running capacity immediately. The finalizer and stale
reconciler serialize on the same locked job row; after the stale failure wins,
late finalization cannot create or attach a public Run or replace the terminal
outcome.

### Notes
- Jobs are idempotent at
  `UNIQUE(user_id, operation_scope, idempotency_key)`. Exact retries return the
  current row before capacity/usage checks; a different `identity_hash` is a
  collision and never returns the old row. All current jobs and pre-start
  failure receipts participate in this boundary; the SQL partial predicate
  excludes only legacy rows whose key is null.
- The reservation lasts for the durable job record's lifetime. A caller does
  not reuse the same key for a new execution after an elapsed retention window.
- Chat Run actions use `confirmation_id` as `idempotency_key`. Direct jobs may
  omit `conversation_id` so the existing direct request shape remains
  compatible, but they remain owner-scoped by `user_id`.
- Before a newly appended confirmation card is published, the server reads
  this reservation owner. A proposed `confirmation_id` that already owns a job
  is replaced across the payload, card, and artifact reference. The durable
  reservation is therefore the single owner of whether a confirmation identity
  is spent.
- `confirmation_message_id` is required for `chat.run_backtest` and the linked
  immutable confirmation artifact is retained for the job record's lifetime;
  direct `backtests.run` jobs keep this field null.
- For chat jobs, the confirmation artifact's `launch_payload_hash` is exactly
  the persisted `payload_hash`, not a shortened confirmation fingerprint.
- Direct admissions atomically start in `running` after both queued and running
  ceilings pass; new conforming direct jobs never enter `queued`.
- The UI must hydrate queued/running/succeeded/failed/canceled/expired state
  from durable rows, not frontend-invented state.
- The current private-alpha UI hydrates status through the API polling endpoint;
  Supabase Realtime remains the selected target transport once the workflow path
  is stable enough to add subscriptions.
- API SSE remains request-scoped and should not be used as a long-lived stream
  for workflow-duration jobs.

---

# 13. Backtest Metrics Shape

Backtest results use a standardized nested shape.

```json
{
  "aggregate": {
    "performance": {},
    "risk": {},
    "efficiency": {}
  },
  "by_symbol": {
    "AAPL": {
      "performance": {},
      "risk": {},
      "efficiency": {}
    }
  }
}
```

### Notes
- Multi-symbol aggregate metrics use equal weighting.
- `by_symbol` allows AI follow-ups like *"Why did the Tesla strategy underperform in 2023?"*
- Aggregate metrics for grouped symbols compare against the class benchmark:
  - Equity groups vs **SPY**
  - Crypto groups vs **BTC** (excluding stablecoins)
  - Currency-pair groups vs the tested pair itself
---

# 14. usage_counters

Tracks resource consumption for quotas and limits.

### Fields
- `id`: `uuid` (Primary Key)
- `user_id`: `uuid` (References `profiles.id`)
- `resource`: `text` (e.g., `backtest_runs`, `backtest_jobs`, `chat_messages`)
- `period`: `text` (e.g., `hour`, `day`, `guest_session`)
- `period_start`: `timestamptz`
- `period_end`: `timestamptz`
- `used_count`: `integer` (Default: `0`)
- `limit_count`: `integer`
- `updated_at`: `timestamptz`
- `created_at`: `timestamptz`

### Constraints & Indexes
- **Unique Logic**: `UNIQUE(user_id, resource, period, period_start)`
- **Lookup Index**: `(user_id, resource, period_start DESC)`
- **Cleanup Index**: `(period_end)`

### Alpha Enums
- **Resource**: `chat_messages`, `backtest_runs`, `backtest_jobs`, `feedback`,
  `discovery_searches` (account rows); `guest_compute_turns` lives only in
  `visitor_usage_counters`
- **Period**: `hour`, `day`, `guest_session`

### Discovery Search Accounting
- For registered accounts, `discovery_searches` counts grounded-discovery
  Search attempts in `usage_counters` (10/hour, 25/day defaults from
  `ARGUS_DISCOVERY_HOURLY_LIMIT` / `ARGUS_DISCOVERY_DAILY_LIMIT`).
- Guest discovery uses `visitor_usage_counters` instead. A guest workspace
  receives a fresh `user_id` when renewed, so an account-owned counter would
  incorrectly reset the allowance.
- Availability is read before the turn runs; the charge settles best-effort
  after the terminal assistant message commits, only when a Search call was
  actually attempted. This is an operational abuse guard with truthful attempt
  accounting, not billing truth; failed settlement never breaks the user turn.

### Notes
- Usage counters are operational safety data, not monetization data in Alpha.
- For `guest_session`, `period_start` equals `guest_workspaces.created_at` and
  `period_end` equals its fixed seven-day `expires_at`. Limits are two unique
  simulation admissions and five feedback submissions over the identity
  lifetime. Conversation is compute and is not metered: `chat_messages` rows
  are retired history that no product path writes.
- Registered users continue to use the existing UTC hour/day accounting.

---

## 14.1 visitor_usage_counters

Tracks visitor-scoped and shared provider allowances without inventing a
profile owner. This is intentionally separate from `usage_counters`, whose
`user_id` is a foreign key to `profiles.id`. It also holds the guest compute
anti-abuse ceiling (`guest_compute_turns`, one visitor-keyed row and one
`session:<guest user id>` row, claimed atomically at turn start) and the
signed-in compute ceiling (`account_compute_turns`, keyed on
`user:<account id>`), which are not allowances and are never projected by
`GET /me/usage`. Signed-in research uses the same `user:<account id>`
subject on `research_searches`.

### Fields
- `visitor_key`: `text` (opaque subject; never a raw address). `visitor:`
  keys are a keyed digest. `user:<account id>` and `session:<guest user id>`
  store the id as-is.
- `resource`: `text` (`discovery_searches`, `research_searches`,
  `guest_compute_turns`, `account_compute_turns`)
- `period`: `text` (`day`)
- `period_start`: `timestamptz`
- `period_end`: `timestamptz`
- `used_count`: `integer` (Default: `0`)
- `limit_count`: `integer`
- `created_at`: `timestamptz`
- `updated_at`: `timestamptz`

### Constraints, access, and retention
- **Primary key**:
  `(visitor_key, resource, period, period_start)`
- **Window lookup index**:
  `(visitor_key, resource, period_end)`
- RLS is enabled with no policies. Only `service_role` has table access and may
  execute `settle_visitor_usage`, `claim_research_usage`,
  `claim_guest_compute_usage`, `claim_registered_compute_usage`, or
  `purge_expired_visitor_usage`.
- Expired rows are disposable operational data, but `period_end` is not a timer
  and nothing in the database acts on it. The row has no owner to cascade from,
  so it is deleted only when a successful non-dry-run of the guest cleanup job
  reaches the purge: `purge_expired_visitor_usage` is registered in
  `argus.domain.guest_cleanup.EXPIRING_DATA_PURGES` and runs on every non-dry-run
  `scripts/ops/cleanup_expired_guest_workspaces.py`. Retention therefore holds
  exactly as often as an operator runs that job. It is not a deployed release
  surface. See the runbook's Operator-Run Maintenance section.

### Discovery policy
- A guest receives two grounded searches per visitor per day. Renewing the
  temporary workspace does not reset that allowance.
- The same table holds the global attempted-search bucket. Its daily ceiling is
  configured by `ARGUS_DISCOVERY_GLOBAL_DAILY_CEILING` and defaults to `500`
  when the value is blank or invalid.
- If counter truth cannot be read, admission currently fails closed into the
  existing `discovery_limit_reached` recovery. Issue #244 retains that
  user-facing truth limitation for follow-up.

### Research policy
- A guest receives three provider-backed research questions per visitor per
  UTC day. Renewing the temporary workspace does not reset that allowance.
- A signed-in account receives 15 provider-backed research questions per
  UTC day (`ARGUS_REGISTERED_DAILY_RESEARCH_CEILING`), keyed on
  `user:<account id>` in the same table. `GET /me/usage` does not project
  that row.
- Every signed-in or guest provider attempt also draws on the shared
  `global:research` daily row. Its ceiling is configured by
  `ARGUS_RESEARCH_GLOBAL_DAILY_CEILING` and defaults to `5000` when blank or
  invalid.
- `claim_research_usage` locks the shared row and optional per-account row in one
  transaction, checks both limits, and increments both or neither before
  provider work starts. This is the concurrency boundary: simultaneous turns
  from one account cannot both consume one remaining slot. An admitted claim
  returns the `period_start` it charged.
- When the provider work a claim admitted fails with no usable response, and
  the turn's charge does not already stand, the backend calls
  `release_research_usage` (service-role only, like the claim) with that
  `period_start`. It decrements only the account's own row for that day, never
  below zero, and never touches the shared row, which keeps the attempt. It
  returns `released`, and only a confirmed release lets a later provider path
  in the same turn claim again. The charge stands for the rest of the turn once
  provider work was served, was cancelled while it may still be billing, or
  could not be released (the function failed or matched no charge), so one
  turn never costs an account more than one question. Migration
  `20260913230000_release_research_guest_claim.sql` adds the release and the
  claim's `period_start`.
- Cache hits, ordinary chat turns, unconfigured-provider paths, and persisted
  thorough-job replays never call the claim. Claim failures degrade to the honest
  research-capacity response and do not enter the provider path.

### Guest compute policy
- A guest's ordinary chat turns claim one `guest_compute_turns` unit against
  the visitor digest and one unit against `session:<guest user id>` in the
  same transaction, at turn start. The guest hits whichever daily ceiling
  is lower. The visitor ceiling is 300. The session ceiling defaults to 100
  (`ARGUS_GUEST_SESSION_DAILY_TURN_CEILING`) so one workspace cannot reset
  the cap by changing IP. A claim that is admitted stands if the turn later
  errors; there is no release. A claim RPC error is not treated as
  exhaustion; the guest sees a short retry, not the daily-cap 429.
  Migration
  `20260925120000_claim_guest_compute_usage.sql` adds the claim. The visitor
  identity is the trusted client IP header (`CF-Connecting-IP` by default,
  `ARGUS_TRUSTED_CLIENT_IP_HEADER`), never the first `X-Forwarded-For` hop.
  IPv6 visitor keys group by `/64`.

### Signed-in compute policy
- A signed-in account's ordinary chat turns claim one
  `account_compute_turns` unit against `user:<account id>` at turn start.
  The daily ceiling defaults to 200 (`ARGUS_REGISTERED_DAILY_TURN_CEILING`).
  A claim that is admitted stands if the turn later errors; there is no
  release. A claim RPC error is not treated as exhaustion; the user sees a
  short retry, not the daily-cap 429. Migration
  `20260925140000_claim_registered_compute_usage.sql` adds the claim.
  `GET /me/usage` never projects this counter.

---

## 14.2 guest_funnel_milestones

Records that a guest funnel milestone has been reached, so it is emitted at most
once per subject. Milestone events are the acquisition funnel's numerator, and a
duplicate inflates conversion counts in one direction.

The subject is the same visitor key that meters guest allowances, not a
`user_id`: renewing a temporary workspace mints a fresh `user_id`, so a
user-keyed milestone would re-fire on every renewal. Like
`visitor_usage_counters` this table is deliberately not foreign-key bound.

### Fields
- `subject_key`: `text` (visitor key; falls back to a pseudonymous actor hash
  when no visitor key is bound to the request)
- `milestone`: `text` (guest funnel event kind)
- `recorded_at`: `timestamptz`
- `expires_at`: `timestamptz`

### Constraints, access, and retention
- **Primary key**: `(subject_key, milestone)`. The primary key is the
  idempotency guarantee. It holds across retries, restarts, concurrent
  requests, and multiple workers in a way application logic cannot.
- **Expiry index**: `(expires_at)`
- RLS is enabled with no policies. Only `service_role` has table access and may
  execute `claim_guest_funnel_milestone` or
  `purge_expired_guest_funnel_milestones`.
- Claims are marked expired 30 days after they are recorded, outliving the
  seven-day guest workspace with headroom. A visitor-keyed table with no expiry
  would become a durable visitor log.
- `expires_at` is not a timer, and nothing in the database acts on it. The row
  has no owner to cascade from, so the guest cleanup job is the only thing that
  deletes it: `purge_expired_guest_funnel_milestones` is registered
  in `argus.domain.guest_cleanup.EXPIRING_DATA_PURGES` and runs on every
  non-dry-run `scripts/ops/cleanup_expired_guest_workspaces.py`. A visitor who
  never returns is deleted by that job, not by the takeover path. Retention
  therefore holds exactly as often as an operator runs that job.
- `claim_guest_funnel_milestone` also takes over an already-expired claim in the
  same statement, so a returning visitor is correct even between purge runs.

### Milestone policy
- Milestone-class kinds are `first_useful_assistant_response_completed`,
  `first_simulation_admitted`, `first_result_completed`,
  `account_creation_completed`, `existing_account_sign_in_completed`, and
  `temporary_workspace_claimed`.
- Every other guest funnel kind is repeatable volume or step data and is not
  claimed. A guest reaches confirmation, sees a conversion prompt, hits a limit,
  and submits feedback as many times as they actually do.
- A duplicate claim is a silent no-op. A retried request must not fail because
  it already succeeded.
- A milestone whose claim cannot be resolved or persisted is suppressed rather
  than emitted, because duplicates bias the funnel in one direction.
- Visitor keys are IP-derived, so callers sharing one egress address share a
  subject and a second visitor's milestone can be suppressed. This is the same
  property guest allowance metering already accepts.

---

# 15. feedback

Stores user-submitted bug reports, feature requests, general feedback, and
private-alpha support requests such as account deletion requests.

### Fields
- `id`: `uuid` (Primary Key)
- `user_id`: `uuid` (Nullable, references `profiles.id`)
- `type`: `text` (e.g., `bug`, `feature`)
- `message`: `text`
- `context`: `jsonb` (Default: `{}`)
- `created_at`: `timestamptz`

### Enums
- **type**: `bug`, `feature`, `general`, `account_deletion_request`
---

# 16. Soft Delete & Archive Rules

### Soft Delete
Used for **conversations** and retained on legacy **strategies** and
**collections** rows. Legacy rows remain filtered/read-safe, but only
conversation recovery is exposed in the current product.

### Archive
Used specifically for **conversations** to hide them from the primary sidebar without deleting the data.

### Account deletion (Lane 6)
`POST /account/delete`, behind the default-off `ARGUS_ACCOUNT_DELETION_ENABLED`,
runs one deletion command for registered and guest accounts. The
[account deletion census](specs/lanes/account-deletion-fk-census.md) owns what
happens to each table. Rows other people still rely on, such as the person's
amounts in their plans and legs of shared activities, move to a nameless
placeholder, one per
[sharing scope](specs/lanes/account-deletion-fk-census.md#sharing-scopes-and-the-standalone-shared-group).
Everything else of the person's is deleted, their feedback loses its email and
user id, and the anonymous invite record stays.

Three `argus_private` tables hold identifying data only while a run is in
flight: `account_deletion_runs` (the user id and two hashes of it),
`account_deletion_placeholders` (the map from the run to its placeholders) and
`account_deletion_revocations` (each pending revocation with its encrypted
credential). The
[census](specs/lanes/account-deletion-fk-census.md#placeholders-one-per-sharing-scope-none-tied-to-the-person)
owns what the run keeps once it completes. The existing run's `steps` also owns
the Apple terminal receipt. After confirmed provider revocation, receipt creation
and removal of the exact stored Apple credential commit in one transaction,
fenced by the live run claim. A missing credential without a terminal receipt
keeps an Apple-linked pending run unresolved. No second deletion journal exists.
A run waiting on a third party keeps the account locked and its auth user in place. It finishes when the person
retries or an operator runs `scripts/ops/scheduled_maintenance.py`. Nothing runs
that sweep on a schedule, by the founder's decision of October 3, 2026, and no
cron is to be created for it. The
[launch runbook](PRIVATE_LAUNCH_RUNBOOK.md#account-deletion-runs-lane-6) owns
the cadence and the 7-day operator force; the
[API contract](API_CONTRACT.md#post-accountdelete) owns the route.

The personless analytics adapter stores `analytics_evidence` in the existing
run `steps`. It contains submission and request UUIDs, parsed provider status,
selected-event count, HTTP status and local outcome. The run UUID owns submission
identity, so retries do not create a separate identity store. Provider bodies,
queries, distinct IDs and credentials are excluded from this evidence. A selected
event count is not an independently verified deletion count. The
[API contract](API_CONTRACT.md#post-accountdelete) owns completion and retry behavior.

---

# 17. Recents / History Model

Recents is a mixed-type feed displaying activity across the platform.

### Supported Types
- `chat`
- `run`
- `strategy` (legacy read compatibility only)
- `collection` (legacy read compatibility only)

### Standard History Shape
```json
{
  "type": "chat",
  "id": "uuid",
  "title": "Tesla dip thread",
  "subtitle": "Last message or metric preview",
  "pinned": false,
  "created_at": "timestamp",
  "activity": {
    "operation": {"status": "idle", "kind": null, "updated_at": null},
    "attention": {"status": "none", "cursor": null}
  }
}
```

`activity` is projected on `chat` rows only and omitted from all other History
types. It is not stored on the conversation and does not affect History order.
---

# 18. Search Model

Alpha supports keyword-based search across core entities.

### Scope
- **Global Search**: Omni-search spanning current Conversation, Run, Idea,
  Evidence, and Decision artifacts.

### Future
Semantic search using embeddings is deferred until post-Alpha.
- Do not add embedding or pgvector tables for the production readiness chat/backtest branch.
- Use structured Supabase records, run metadata, Idea/Evidence/Decision
  artifacts, and keyword search until Argus needs semantic recall across large
  histories.

---

# 19. RLS Ownership Rules

Every user-owned table must enforce strict Row Level Security (RLS).

### Primary Rule
- Unless a table-specific rule below is stricter, users may only `SELECT`,
  `UPDATE`, or `DELETE` rows where `user_id = auth.uid()`. Server-owned or
  immutable tables may revoke some of those operations; this default never
  grants a client write that a table-specific rule forbids.
- RLS policies are not the only guard: client table, column and function
  privileges in `public` and `argus_private` are owned by
  `tests/test_client_grants_postgres.py`. The early tables `backtest_jobs`,
  `backtest_runs`, `collection_strategies`, `collections`, `context_packets`,
  `conversations`, `decision_notes`, `evidence_artifacts`, `feedback`,
  `idea_versions`, `ideas`, `messages`, `profiles`, `route_receipts`,
  `run_context_packets`, `strategies` and `usage_counters` carry no `anon` or
  `authenticated` privilege except `authenticated` `SELECT` on `backtest_jobs`
  and `SELECT (id, avatar_theme, country, currency_override, preferred_name)`
  plus `UPDATE (avatar_theme, country, currency_override, preferred_name)` on
  `profiles` (`20261005090000_explicit_client_grants.sql`). The backend writes
  these tables with the service role.

### Chat-turn lifecycle
- `chat_turn_lifecycles` grants authenticated owners `SELECT` only. No client
  role may insert, update, delete, or execute its server transition function;
  the server-side persistence boundary owns every write.

### Conversation read state
- `conversation_read_states` grants authenticated owners `SELECT` only.
  `PUBLIC`, `anon`, and `authenticated` cannot write or execute its mutation,
  read-source, reconciliation, or baseline functions; service-role persistence
  owns those operations.

### Financial accounts
- `financial_accounts`, `financial_records` and `financial_record_revisions`
  grant authenticated owners `SELECT` only, and only when the trusted
  `is_anonymous` JWT claim is not `true`, so a guest reads nothing even about
  rows carrying its own id. No client role may insert, update, delete, or
  execute the two write functions; `financial_account_idempotency` has no
  client policy at all. Proven by `tests/test_financial_accounts_postgres.py`.

### Tables Requiring RLS
- `private_alpha_allowlist`, `private_alpha_access_welcome_claims`,
  `private_alpha_access_welcome_deliveries`,
  `profiles`, `conversations`, `messages`,
  `chat_turn_lifecycles`, `conversation_read_states`, `strategies`, `collections`,
  `collection_strategies`, `backtest_jobs`, `backtest_runs`, `feedback`,
  `usage_counters`, `guest_workspaces`, `memory_settings`,
  `memory_candidates`, `memory_consent_actions`, `memory_records`,
  `memory_provenance`, `memory_prompt_history`, `memory_reconciliations`,
  `memory_provider_projections`, `memory_provider_cleanup`,
  `financial_accounts`, `financial_records`, `financial_record_revisions`,
  `financial_account_idempotency`.

### Guest ownership
- Supabase anonymous identities use the `authenticated` role, so every guest
  policy keeps `(select auth.uid()) = user_id`; role membership alone is never
  authorization.
- Expired guest identities cannot read or write product rows.
- Another guest and a permanent user see zero guest workspace rows.
- Guest memory state must be zero before either same-identity claim or
  existing-account handoff. Memory rows are rejected rather than transferred.
- `profiles.avatar_theme` is a registered-account preference. The database
  default keeps every row valid, but restrictive profile RLS policies use the
  trusted `is_anonymous` JWT claim so a guest cannot read or write it through
  the client role. The API omits the field from guest responses.

### Private Alpha Allowlist
- No `anon` or `authenticated` role access is required.
- All privileges remain revoked from `public`, `anon`, and `authenticated`;
  no client policy permits direct requested-row access.
- Backend service-role access owns request capture, welcome claim/completion,
  and access checks before auth signup/login. The claim and delivery tables
  have no client policies. Service role can select immutable delivery evidence
  and execute the guarded claim/completion RPCs, but it has no direct claim
  table access and cannot insert, update, or delete delivery records.

---

# 20. Indexing Requirements

### Critical Performance Indexes
- **private_alpha_allowlist**: `(email)` with active-row partial index
- **profiles**: `(id)`, `(username)`
- **conversations**: `(user_id, updated_at DESC)`, `(user_id, archived, deleted_at)`, `(user_id, pinned)`
- **messages**: `(conversation_id, created_at DESC)`
- **chat_turn_lifecycles**: `(conversation_id, status, updated_at)`,
  `(user_id, status, updated_at)`, unique `(assistant_message_id)` where not null
- **chat_turn_lifecycles activity reads**:
  `(user_id, conversation_id, status, updated_at DESC, turn_id DESC)` for active
  rows and `(user_id, conversation_id, status, terminal_at DESC, turn_id DESC)`
  for terminal rows
- **strategies**: `(user_id, updated_at DESC)`, `(user_id, pinned)`, `(user_id, deleted_at)`
- **strategies (gin)**: `USING gin(symbols)`
- **collections**: `(user_id, updated_at DESC)`, `(user_id, pinned)`, `(user_id, deleted_at)`
- **collection_strategies**: `(collection_id)`, `(strategy_id)`
- **backtest_jobs**: `(user_id, status, queued_at DESC)`, `(conversation_id, created_at DESC)`, `(result_run_id)`
- **backtest_jobs activity reads**:
  `(user_id, conversation_id, status, updated_at DESC, id DESC)` for active or
  checking rows and `(user_id, conversation_id, status, finished_at DESC, id DESC)`
  for terminal rows
- **backtest_jobs unique/idempotency**:
  `UNIQUE(user_id, operation_scope, idempotency_key)`
- **backtest_jobs payload lookup**: `(user_id, payload_hash, created_at DESC)`
- **backtest_jobs identity lookup**:
  `(user_id, operation_scope, identity_hash, created_at DESC)`
- **backtest_runs**: `(user_id, created_at DESC)`, `(conversation_id)`, `(strategy_id)`
- **backtest_runs (gin)**: `USING gin(symbols)`
- **feedback**: `(user_id, created_at DESC)`
- **usage_counters**: `(user_id, resource, period_start DESC)`
- **usage_counters**: `(period_end)`
- **usage_counters unique**: `(user_id, resource, period, period_start)`
- **memory_candidates**: `(owner_id, created_at, id)`
- **memory_consent_actions**: `(owner_id, recorded_at, id)`, unique confirmed
  `(owner_id, candidate_id)`
- **memory_records**: `(owner_id, created_at, id)`, covering
  `(owner_id, consent_action_id, candidate_id)`, unique
  `(owner_id, candidate_id)`
- **memory_provenance**: unique ordered candidate and record indexes on
  `(owner_id, parent_id, ordinal)`
- **memory_reconciliations**: partial pending/running index on
  `(owner_id, status, record_id, generation)`
- **memory_provider_cleanup**: partial pending index on
  `(owner_id, status, created_at, record_id)`
---

# 21. Naming & Title Defaults

AI-generated titles are the default for conversations. Historical Strategy and
Collection names are read-only compatibility data.

### Source Tracking
- `system_default`: The initial placeholder before AI processing.
- `ai_generated`: Set after the AI generates a context-aware title.
- `user_renamed`: Set if the user manually overrides the title.

*Note: AI must never overwrite a `user_renamed` entry.*

---

# 22. Usage Controls, Quotas, and Limits

Argus Alpha MVP implements three defensive layers to protect system stability and manage compute/LLM costs while maintaining a generous user experience. These are "fair use" guardrails, not monetization tiers.

### Layer 1: Engine Constraints
Hard-coded technical limits in the backtesting logic.
- **Symbols**: Max 5 symbols per run.
- **Timeframe**: 1h, 2h, 4h, 6h, 12h, 1D.
- **Provider windows**: Stored run configs must reflect provider-available history for the selected asset class and timeframe. Alpaca equity history starts in 2016 for the launch path; Kraken OHLC currency-pair windows are limited to the latest 720 candles for the requested interval.
- **Capital**: Min 10 / Max 100,000,000 (`MIN_STARTING_CAPITAL`, `MAX_STARTING_CAPITAL`). A recurring plan keeps its own seed and contribution rules.
- **Side**: Long-only.

### Layer 2: Rate Limits
Short-window protection against abuse or runaway UI loops.
- **Backtests**: Max 10 per hour.
- **Chat**: Max 60 messages per hour.
- **Feedback**: Max 20 submissions per hour.
- **Unauthenticated auth attempts**: Login max 8 attempts and signup max 5 attempts per 10 minutes, keyed by endpoint plus client IP/email. This is an alpha abuse guard before provider calls, not a replacement for Supabase Auth protections.
- **Mechanism**: Enforced via standard `Retry-After` headers.

### Layer 2.5: Backtest Concurrency
Durable job backpressure protects the chat API from compute spikes.
- **Per user**: 1 running backtest, 2 queued backtests.
- **Global**: 5 running backtests, 10 queued backtests.
- **Mechanism**: The database-owned admission operation resolves idempotency,
  checks both scopes, charges one unique admission, and inserts the job
  atomically. Chat admission inserts `queued`; the synchronous direct path
  checks both queued and running ceilings and inserts `running`. Per-user
  exhaustion is evaluated before global exhaustion and returns
  `429 backtest_capacity_exceeded`; global exhaustion returns
  `503 backtest_capacity_exceeded`; both include `Retry-After: 15`.

### Layer 3: Daily / Rolling Quotas
Generous usage boundaries tracked via the `usage_counters` table.
- **Backtest Runs**: 50 per day.
- **Chat Messages**: 200 per day.
- **Feedback**: 50 submissions per day.

---

# 23. Backend Enforcement Model

### Enforcement Flow
1. **Authenticate**: Resolve `user_id` from session.
2. **Hard Constraints**: Validate `backtest_run` inputs against Engine Constraints.
3. **Atomic Admission**: In one database operation, resolve exact replay versus
   identity collision, check the applicable usage period plus per-user/global
   queued/running capacity, charge one unique simulation, and insert the job.
   Chat admission starts `queued`; direct admission starts `running`. The exact
   order is replay/collision, usage allowance, per-user capacity, global
   capacity, then insert plus charge.
4. **Exceedance Policy**:
   - If rate limit exceeded: Return `429 Too Many Requests`.
   - If daily quota exhausted: Return `429` (Alpha policy).
   - If per-user capacity is exhausted: return
     `429 backtest_capacity_exceeded` with `Retry-After: 15`.
   - If global capacity is exhausted: return
     `503 backtest_capacity_exceeded` with `Retry-After: 15`.
   - If the same reservation key carries a different identity: return
     `409 idempotency_conflict` without returning the old job, and persist a
     separate failed receipt under a distinct derived `rejection:<hash>` key
     for the refused chat attempt.
5. **Execute**: Dispatch workflow execution, or run the admitted direct
   compatibility path synchronously, against the durable job.
6. **Response**: Return result or job state. Include rate-limit headers only
   when they are backed by an active limiter; do not emit placeholder quota
   values.

### Admin Bypass
Users with `profiles.is_admin = true` may have quota and rate-limit checks bypassed by backend logic.
- Ownership and privacy rules still apply.
- Engine safety constraints (e.g., symbol limits) may still apply.

---

# 24. Historical State & Reproducibility (SCD)

Full Slowly Changing Dimension (SCD) systems (e.g., Type 2 historical tracking) are **NOT required for Alpha MVP**.

### Historical Strategy
- **Overwrite (SCD Type 1)**: User profiles and metadata are updated in place.
- **Reproducibility**: Rather than tracking history in the `strategies` table, every `backtest_run` preserves the exact inputs in `config_snapshot`. This ensures a run's results are always tied to its execution-time state.
- **Future Growth**: If strategy versioning becomes central, a `strategy_versions` table can be added without breaking the core model.

### Product Philosophy
"Protect the system without making legitimate exploration feel constrained."
- Real users should comfortably test multiple ideas per session.
- Abusive loops and bot activity must be blocked.
- Limits are operational defaults, not permanent product promises.

---

# 25. Data Model Decision Filter

When adding or changing a table, ask:

> *Does this store durable truth, recovery state, or useful research memory without turning context into simulation truth?*

If no, it likely should wait for post-Alpha.

### Personal money activity extension (authorized September 29, 2026)

Additive migration retains financial_records/revisions and existing coverage foreign
keys. All activity uses current signed leg movements in the existing projection.
Kind, role, active and source/refund provenance live in revision details. Account
correction retires departed legs with new inactive zero revisions and creates/reuses
replacement records; immutable account_id and historical coverage remain.

financial_activity_groups owns stable identity, owner, immutable kind and current
revision. financial_activity_memberships binds each group revision to exact record
revisions and role using owner-qualified composite keys. Shared facts derive from
primary single/source leg, never a second stored amount. All existing expense IDs
and revisions backfill as groups with identical IDs. Refund provenance contains
stable purchase group and reviewed revision. Purchase category edits with linked
refunds fail explicitly, so copied historical category cannot silently drift.

financial_activity_receipts binds owner/key, request hash, accepted group/revision and
affected account IDs. Every canonical AND legacy activity writer takes one owner
transaction advisory lock before discovering dependencies, then the complete affected
account rows in UUID order. Replay precedes CAS. All revisions/membership/coverage,
versions and receipt commit atomically. Metadata/opening/check writers stay account-only;
none acquires owner lock after account lock. Reads use repeatable-read snapshots.
Money rules stay in domain code. Owner serialization protects refund/purchase races.
Group/membership SELECT RLS is registered-owner only, writes service-only; receipts
have no client grants. Home derives monthly totals from current logical activities
through the shared Recording spending reducer.

financial_activity_revisions is only the owner-qualified group revision identity;
it stores no duplicate money facts. Group current revision, memberships and receipts
reference it. Revision purchase_activity_id/purchase_revision are generated from
details and enforce an owner-qualified FK to the exact reviewed purchase revision.
This preserves one source for refund provenance while making cross-owner references
unrepresentable. The additive integrity migration is 20260929130000.

### Paired currency transfer facts (#820)

No schema or backfill is added. Each exact leg revision retains its own integer
`amount_minor`; the corresponding canonical account owns its immutable currency.
Group revisions, memberships, coverage and receipt transactions remain unchanged.
No rate, converted total or duplicate amount is stored. Per-leg read denomination
and formatted amount derive from that account and revision after visibility filtering.
A hidden source does not disclose its denomination through the legacy summary.

The destination input is included in request identity only when non-null. Existing
receipt and preview preimages remain identical when it is absent. Plan currency
stays fixed and current attribution rejects pairs with any different-currency leg.
The write flag and acceptance boundary live in the
[transfer contract](specs/lanes/cuadrao-cross-currency-transfers.md).

### Connected Plan storage

The additive connected Plan migration stores owner-scoped expectations with versioned
schedule segments, owner projection selection, occurrence-to-canonical-activity links,
and idempotency receipts. It stores no actual balance or parallel ledger. Expectations
contain only planned money; linked occurrence snapshots preserve the reviewed schedule
and amount while actual amounts always derive from the current canonical activity.
Owner-qualified foreign keys connect links to expectations and activity revisions.
RLS allows registered owners to read their rows; writes remain service-only and receipt
rows have no client grants. All Plan writes take the same financial activity owner lock
before account locks. Recording from Plan composes the existing Money planner/persist
inside that transaction. Read snapshots use repeatable read for planning and accounts.
Schedule edits cut over only after every previously fulfilled date, including future
prepayments. Amount/title edits retain occurrence identity and linked snapshots.

### Connected personal spending budgets

`financial_budgets` stores owner-scoped versioned definitions with stable IDs,
name, positive limit in integer minor units, currency, calendar month, explicit
account/category arrays, Uncategorized inclusion, and reversible archived state.
The shared Plan selection owns the reporting time zone. Budget rows contain no
actual totals. The account and category arrays are canonical sorted unique sets.
A partial unique storage index rejects duplicate active owner/month/currency/
account/category/Uncategorized scopes. Restoration observes the same constraint
and current account eligibility. Archiving retains ownership checks even if an
account no longer supports the definition's expense scope.

Registered owners may SELECT their budget rows. Writes are service-only, and the
existing financial_plan_receipts table retains exact accepted command results
without client grants. Budget commands use the existing owner advisory lock,
replay-before-version checks, account locks, and atomic transaction. Plan, Home,
budget detail, and Search read the same repeatable-read owner snapshot.

Recording's spending reducer derives full expense/refund amounts and loan interest/fee
costs from current logical activity. Principal, transfers and card payments contribute
zero. Linked refunds inherit scope from the current original purchase; linked payment
returns retain the original cost scope. Their actual received timestamp owns period
membership. Unlinked refunds use their recorded scope. Negative net spending is valid.
Home's compatibility recorded_spending_minor field remains lifetime gross active
expense activity only; monthly gross/net spending includes canonical loan costs.
Archived accounts remain explicit scope members. Definition changes never write
account records, cash forecasts, or bill-fulfillment links.

### Connected personal savings goals

`financial_goals` stores owner-qualified versioned definitions, immutable currency,
target, optional date/destination, explicit unlinked allocation residuals,
reversible archive state and contribution schedule segments. No saved total or
account balance is persisted. Current Recording position/activity and one shared
personal ownership rounding function supply actual money.

The additive goal migration extends `financial_plan_links` with stable claim_id,
nullable occurrence_id/expectation_id, goal_id and attribution. Existing expectation
identity/snapshot, unique owner/activity and owner-qualified exact activity-revision
foreign keys remain. A goal claim has attribution and/or its own occurrence;
released attribution persists explicitly and retains fulfillment. Ad hoc claims
cannot enter expectation-only readers. Accepted original personal amounts are
provenance, never current-value fallback. Goal rows use registered-owner SELECT
RLS and service-only writes. Existing Plan receipts, owner/account locks and
repeatable-read snapshots own goal writes/reads and atomic contribution posting.


## Connected debt intentions and dated payment returns

`financial_debt_plans(id,user_id,debt_account_id,body)` stores only versioned intentions and explicit scenario assumptions, with an owner-qualified account FK, registered-owner SELECT RLS and service-only writes. A partial unique index permits one active plan per debt account; restoration checks that constraint. Balances and cumulative payment/cost counters are never stored here.

`financial_plan_links.debt_plan_id` adds a mutually exclusive debt purpose to existing expectation/goal claims. Debt claims retain activity revision provenance and stable occurrence snapshots. Global owner/activity uniqueness remains. Non-debt occurrence uniqueness remains through a partial index; debt occurrences allow multiple payment claims. Extras have no occurrence. Every writer uses the existing Plan receipt, shared owner advisory lock, sorted account locks and current version checks.

Loan source record revisions retain total movement and `details.interest_minor`. Destination movement retains principal, including zero principal. Fees derive losslessly as source total minus principal minus interest through the single Recording payment decoder. There is no second payment ledger. Real `payment_reversal` activity revisions retain inverse signed cash/debt movements, the explicit returned split, and generated owner-qualified original activity/revision FKs. Both original and dated return remain canonical activities. Paired corrections append revisions atomically and preserve former observation coverage. Current linked caps and account/date/category guards prevent contradictory corrections.

Recording position and spending remain the actual owners. Loan interest and fees contribute once, scoped to funding account and selected/default existing category. Return costs reduce spending in the return period; principal and cards do not count. Debt progress, forecast remainders, recorded clear/reopening and savings backing concerns derive from current canonical revisions. Conditional payoff remains an explicit monthly model, separate from actual position and scheduled cash commitments.

Debt-plan archive preserves canonical payments and claimed occurrence snapshots. The shared occurrence projection marks retained archived intentions `plan_archived`, suppressing only residual forecast movement. Restore derives the same residual from current canonical activity.

## Shared Household planning storage sketch

**Status:** Worker storage contract for the [assigned shared planning lane](specs/argus-execution-board.md#connected-shared-household-planning-lane), October 1, 2026. Schema/cutover source is applied only to NEW disposable Postgres on port 59752. The connected native journey and focused independent review passed; exact publication gates are recorded on PR #773. No existing demo or hosted database is migrated. The [API contract](API_CONTRACT.md#shared-household-planning-contract-sketch) owns the scoped public wire and approved permission/departure rules.

The implemented design adds consent and responsibility references to existing
owner-qualified definitions. The alternative adds Household scope directly to
every canonical definition and replaces owner-qualified readers with scope
readers. References retain existing Personal ownership, identities, and
recurrence with fewer authorization changes. Neither candidate permits copied
definitions, shadow Personal goals, a second allocation engine, or stored
editable actual totals.

### Binding and participant records

The `household_plan_bindings` contains `id`, `household_id`,
`owner_membership_id`, `owner_user_id`, exactly one of `budget_id`,
`expectation_id`, `goal_id`, or `debt_plan_id`, and `revoked_at`.
The original definition ID remains its financial identity. Composite foreign
keys bind the selected definition to its original owner and the owner's current
membership to the same Household. Binding lifecycle also records owner-departure
archive, the retained authorized recipients and previously shared definition
revision. Read-only archived history grants no write or future projection. An
expectation binding admits bills, not
private expected income. A partial unique key permits one live, non-departed binding per
canonical definition; retained departed bindings preserve prior consent. There is no second plan amount, balance, name, schedule,
completion flag, or owner in a copied body.

The `household_plan_participants` contains `binding_id`,
`membership_id`, one permission `view|edit`, and revocation state. Owner powers
derive from original ownership; no stored owner role competes with that fact.
The participant membership FK binds the same Household incarnation. Joining or
rejoining cannot reactivate consent. The household row/version remains the
authorization lock and generation owner.

Responsibilities belong to the canonical definition's versioned state and name
participant membership, optional explicit minor-unit amount, and their
occurrence or period. They retain safe cutover and fulfilled snapshot rules.
They contain intentions, never receipts, editable progress, or account balance.
Every activity or definition edit retains the actual authenticated actor and
append-only correction history. View-only participants may record/link and
correct their own contributions, without definition editing or access to other
participants' private funding. These powers require distinct server checks.

### One canonical claim and allocation owner

`financial_plan_links` remains the activity-claim owner. The proposed extension
separates definition owner `user_id` from `activity_owner_id`, backfilled to the
same value for existing rows. Definition foreign keys continue to use
`user_id`. The exact activity-revision FK uses `activity_owner_id`. A unique
`(activity_owner_id,activity_id)` over active or occurrence-bound claims replaces
the existing same-owner uniqueness. Released unscheduled extras remain historical
rows without reserving the active slot. Personal and shared writers cannot
count one activity twice; scheduled claim lifecycle remains unchanged.

Shared claims add binding, contributor membership, explicit purpose, and an
optional budget purpose. Checks require one canonical definition purpose and
an owner-qualified binding. A goal claim may fulfill its own occurrence without
another attribution. Shared bills permit multiple independently claimed actual
payments on one occurrence; the existing single-claim rule remains for Personal
bill occurrences. Debt's existing multiple-payment rule remains. Budget
matching and explicit claims deduplicate by logical activity identity.
Funding transfers are attributed receipts, not spending or bill/debt fulfillment.

Goal claims and any explicit unlinked residual allocations identify the actual
destination account owner through owner-qualified account references. The
existing `goal_projection` pool reducer must load all Personal and shared claims
against that owner's account capacity. Claim creation, replacement, correction,
and release use the same owner serialization. There is one pool per original
account, regardless of which definition owner or Household uses it. Actual
account position, account ownership-share rounding, and current activity remain
Recording facts. Unshared private claims affect capacity validation internally
but never become shared contribution rows or shared totals.

No shared adapter calls a Personal projection and filters its output. Shared
responses select consented definition facts and claims before projection. Full
private pools, min(balance,claim) support, shortfall amounts, affected private
goals, funding accounts, notes, history, and copied Personal receipts cannot
enter the shared output. Fully supported public credit discloses the consented
claim amount; unresolved support stays null with a review state.

Private cross-owner attribution cannot remain directly readable through the
definition owner's `financial_plan_links.owner_read` policy. Shared claim rows
require service projection; existing same-owner Personal rows retain their read
policy. Private residual account references likewise cannot enter an owner-
readable goal body. The canonical `financial_goal_allocations` relation
stores `goal_id`, `goal_owner_id`, `account_id`, `account_owner_id`, and
`unlinked_minor`, with both owner-qualified FKs and a unique goal/account key.
Existing JSON residuals backfill into that relation and cease to be a second
authoritative allocation store. The Personal API's allocation shape remains
derived and compatible. Only the safe API exposes shared residuals; there is no
direct Household SELECT grant. This normalization is a required migration and
deployment-compatibility risk, not a second allocation reducer. Source changes
and backfill rehearsal are approved only for a new disposable local test
database. Validate every legacy allocation, exact amount, owner reference and
row count before removing JSON; update all readers/writers in the same cutover.
No incomplete migration fallback is permitted. Existing demos and hosted
databases remain untouched.

### Smallest multi-owner Money extension

The extended `financial_activity_memberships` retains one logical group
owner in `user_id` and adds `record_owner_id`, completely backfilled from
`user_id` for pre-extension rows. Group/revision FKs
keep `user_id`; record/revision FKs use `record_owner_id`. Each leg stays bound
to its original account and owner. Existing same-owner rows retain the same
identity, revision, money facts, and coverage.

The source account owner owns a paired transfer/payment group. Canonical
Recording persistence writes each leg, observation coverage, and account-version
update under that leg's actual owner. It derives amount and payment splits from
the same original signed leg revisions. It creates no parallel income, expense,
transaction copy, or saved aggregate. Current activity readers assemble the
complete logical group internally, then expose only independently authorized
legs and public consented contribution facts.

One Recording resolver loads the authoritative group `current_revision`, its
exact revision membership, and all original-owner leg records internally.
Every Personal and Household activity, balance-linked summary, spending,
refund/return cap, debt progress, and goal claim reader derives from that
resolver. `groups(load_owner(...))`, the first visible leg, and
`max(visible_history)` cannot choose the canonical revision or primary amount.
A destination-only loan view must not turn principal into the full payment.
An account removed from the current revision must not revive an earlier active
leg. Personal spending counts only the owned funding leg's canonical costs;
destination debt principal does not become spending. Transfers/card payments
remain zero spending in every scope.

Personal and Household disclosure are explicit projections over that complete
canonical fact. A source owner's private note, cost breakdown, source identity,
and history never copy into a foreign-owned destination revision or public
contribution. Destination revision details retain only facts necessary for that
owner's canonical movement and exact group linkage. They do not depend on
filtering a private note after raw table access has already exposed it.

Cross-owner payment returns require an explicit original group owner beside
the existing exact original activity/revision reference. A generated
`reversal_of_owner_id` derives from revision details, with same-owner fallback
only for pre-extension rows. Its composite FK preserves the original canonical
identity. Purchase refunds retain their existing owner-qualified boundary.
Neither a return nor a correction may create an unqualified foreign reference.

Membership SELECT RLS must not expose the other owner's record/account IDs
through the group-owner row. Existing Personal read access stays owner-scoped;
cross-owner metadata requires a safe service projection. New binding,
participant, and command receipt tables have RLS enabled and no direct
`anon` or `authenticated` grants. Shared claims do not widen direct Personal
table policies to Household members.

The group owner's existing membership SELECT policy cannot expose a foreign
leg merely because `user_id` matches. Direct membership reads require the
caller to own the leg as well. Account owners retain reads of their own
financial records; full cross-owner group assembly remains service-owned.

Consent history records `first_shared_revision` and each named recipient's
`granted_revision`. New consent cannot expose earlier private revisions.
Owner departure pins retained definition, claim, activity and allocation
**revision references**, not copied balances/totals/ledgers. Service-only
`household_plan_archived_*` relations and restrictive foreign keys preserve
those previously shared facts. Remaining readers still need their live granted
membership incarnation; archived plans provide no future projections or writes.
Private post-departure edits cannot enter retained history.

Contributor departure uses the same canonical retention owner even on an active
plan owned by someone else. The protected retention relations pin exact
original/related activity and allocation revision references to the ended
membership incarnation. `membership_ended_at` records that access boundary;
signed `last_applied_minor` and nonnegative `last_supported_minor` are immutable
last-authorized disclosure evidence, never editable current money or pool
totals. Current Goal backing is null/`needs_review` after that consent ends.
Remaining members' current activity continues through the ordinary canonical
reader. Distinct allocation revisions preserve history when fresh explicit
consent follows rejoining.

Migration `20261002050000` fails atomically if a legacy active binding already
contains a departed contributor without its authorized retention boundary.
Today's private state cannot safely backfill a past consent boundary. Recover
verified history before such a cutover; never invent a snapshot or hide the
gap through a fallback. Its rehearsal/application is limited to NEW local
Postgres59752, which retained seven account rows unchanged; it does not authorize
any existing demonstration, hosted or production migration.

### Transactions, receipts, and migration risks

Cross-owner groups cannot retain cascades that delete another account owner's
leg, claim, or payment-return history when the group owner is removed. The
migration must preserve surviving owners' financial history and reject an
unsafe destructive deletion. Owner departure archives their shared plans, retains the previously shared
history for remaining authorized members and suppresses future projections.
The retained view contains no private funding. Departure revokes the departing
member's household access; removal/revocation still ends a recipient's access.
Closure revokes household access while preserving owners' records and history.
These operations never delete financial activity or transfer ownership. This lane does not add account
deletion or define a new profile-erasure policy.

Shared mutations take the Household row lock, resolve the current binding and
membership, acquire all involved owner advisory locks in UUID order, then all
old/new/dependency account locks in UUID order. They never acquire a Household
lock after an owner/account lock. Plan and Recording commands share this owner
lock convention. Canonical activity correction must discover every claim owner
before acquiring locks; it cannot take a second owner lock after account locks.
Read projections use one coherent database snapshot and live scope checks.

Correction/return dependency discovery includes every old and new account leg,
every exact original/refund/return reference, and every Personal/shared claim
that can change backing or fulfillment. The transaction locks the complete
owner set before any account lock, revalidates the dependency set under those
locks, and rejects a changed set without posting. Partial correction of one
side is invalid. Activity authorship alone does not grant authority over another
owner's account. After an edit grant is withdrawn, a paired correction requiring
that account is denied; retained originals remain readable only through the
caller's currently authorized projection.

A service-owned scoped receipt binds actor, Household, original membership,
operation, key, normalized request hash, and accepted canonical identities.
It stores no protected result snapshot. Activity, leg revisions, coverage,
account versions, claim, plan version, and receipt commit or roll back together.
Replay uses live authorization before loading an accepted result. Existing
Personal receipt bodies and replay semantics remain compatible.

The migration risks are composite-FK replacement, direct SELECT leakage through
cross-owner memberships/claims, changed claim uniqueness, and multi-owner lock
ordering. Backfill and constraint validation must preserve all existing rows.
PG tests must exercise real concurrent claim/record/correction/revoke commands,
failure rollback, exact retries, owner-qualified malformed inserts, and direct
registered/anonymous RLS reads. Existing Personal goal pools, receipts, budgets,
debt returns, recurrence, and Household same-owner financial tests remain
regression coverage. This sketch is not permission to apply hosted migrations.


## Connected personal asset estimates and links

`financial_accounts` remains the asset identity and ownership-share owner.
Opening and value-update revisions remain the whole-estimate owner. Optional
`estimate_basis` lives in that exact revision's `details` object. Existing
revisions without it mean unspecified basis. A correction retains the record
identity and original observation order, appends one revision and hydrates only
one current observation for that identity. No attributed value or equity is stored.

`financial_asset_details` has one row per account/owner and one nullable
`related_debt_account_id`. Owner-qualified foreign keys bind both existing
accounts; type checks require an optional asset and a liability respectively.
`financial_asset_changes` retains the accepted account version, previous/new
ownership share, previous/new debt ID, actor, timestamp, idempotency key and
request hash. Details, account share/version and accepted change commit together.
Changes are append-only and unique by owner/account/key and account/version.
They are non-money receipts, never financial records. Registered-owner RLS
allows reads; only the service writes. Existing debt balances and plans remain
canonical and unchanged. Current details are a pointer, not a money allocation.

The existing record/revision receipt owns estimate retry identity. Details
changes replay their accepted version before stale-version validation. Account
metadata/link type validation is serialized with details writes. Existing
owner-scoped native financial journals persist pending account creation and
asset commands until an accepted response or explicit failure resolution.

## Apple sign-in credentials

`public.apple_sign_in_credentials`
(`supabase/migrations/20261003150000_apple_sign_in_credentials.sql`) holds one
row per person who signed in with Apple while
`ARGUS_APPLE_REVOCATION_CAPTURE_ENABLED` was on: `user_id` (primary key, the
verified session's user), `client_id` (the Apple client the token was issued
to, the bundle id for the native app), `secret_ciphertext` (Apple's refresh
token sealed with AES-256-GCM under `ARGUS_INGESTION_SECRET_KEY`, bound to
`apple_sign_in:<user_id>`), `captured_at`, `updated_at` and
`secret_key_fingerprint` and nullable `apple_subject`. A later sign-in replaces
the row.
`secret_key_fingerprint` (Lane 6, `20261004090000_account_deletion.sql`) names
the key that sealed the token without revealing it (`SecretBox.key_id`: 32 hex
characters of HMAC-SHA256 of a fixed label under the key); capture sets it, and
rows stored before Lane 6 have none. A token that doesn't open is discarded
only when its fingerprint is the running key's.

`apple_subject` (`20261005160000_apple_credential_subject_binding.sql`) records
the subject verified for that credential. `auth.identities` remains the owner
of the account's current linked identity. Existing rows stay NULL with no
backfill, so they remain unverified. A new capture compares the returned Apple
subject with the current identity, then repeats that check in the save
transaction. New deletion admission requires a readable credential bound to
that current subject before inserting its first run. Legacy unverified rows
require fresh authorization for new admission; their existing pending-run
revocation remains compatible.

The save transaction uses `READ COMMITTED`, locks the Auth user first, then
reads and locks all that user's identity rows in a separate statement. The
immediate identity-to-user foreign key blocks new identity inserts and inbound
moves while those locks are held. Identity row locks block edits and deletion.
The credential write also compares the pre-exchange ciphertext, so a stale
capture cannot overwrite or recreate a replaced or removed row. No transaction
stays open across Apple HTTP. Deletion admission shares this lock order and
locks the deletion run last. Ordinary capture refuses an active deletion run;
recovery capture requires its exact claim and checks expiry after acquiring the
run lock. These locks prove agreement at commit, not after later Auth changes.

The compatibility `upsert` clears `apple_subject` when it writes an unverified
credential. Older binaries do not know this column. Keep capture disabled
during their replacement, and do not run old capture writers alongside
binding-aware consumers.

RLS is on with no policy, and every client privilege is revoked: no client
role can read or write any column. The API's service role is the only writer.
No SECURITY DEFINER function is involved.

`user_id` references `auth.users` with `on delete restrict`. An auth user who
still has an unrevoked Apple token cannot be deleted, so no deletion path can
drop the token without revoking it at Apple. The account-deletion run revokes
first, then atomically removes the unchanged credential and records the terminal
receipt under its live claim before deleting the user. A failed local transaction
keeps the row for a retry, while a committed receipt explains an absent row.
The row is the pending revoke until then, which matches the contract that the
encrypted credential is kept only while a revoke is pending. Apple's
`invalid_grant` on revoke is classified as already revoked, so it also deletes
the row. This classification also applies during an App Store app transfer;
the service does not distinguish transferred credentials from revoked or
expired tokens. Transfer handling and the separate `invalid_request` pending
path remain operator/release concerns in #803.

If `ARGUS_INGESTION_SECRET_KEY` was rotated, the token can't be opened and so
can't be revoked, and the restrict key would keep that user undeletable
forever. The deletion run then calls `discard_unreadable`, which deletes the
row only while it still can't be opened and never logs a token. No route
exposes it. Apple's authorization stays until the person removes it in their
Apple ID settings.

Capture never writes a row for a code that belongs to another Apple ID: that is
`409 apple_identity_mismatch`, and the token is revoked at Apple instead.

## Connected financial sources

Default-off with `ARGUS_INGESTION_ENABLED`. Lane spec:
[financial-ingestion-connectors](specs/lanes/financial-ingestion-connectors.md).

`financial_source_connections` holds one row per person-authorized connection
(Plaid Item, Gmail mailbox, Shortcuts device). It owns status, last successful
and last attempted refresh, the last actionable error code, an attention warning
(`attention_code`, `attention_at`) that successful syncs do not clear, the provider sync
cursor, a short sync lease (`lease_holder`, `lease_until`) and the sealed
provider credential (`secret_ciphertext`, AES-256-GCM bound to
`source:id`, key `ARGUS_INGESTION_SECRET_KEY`). One live row per
`(source, external_ref)` across all people, so a Plaid Item or mailbox grant
never backs two people's connections; webhooks resolve by the same pair.
Cursor advances are compare-and-set under the lease; failures never clear
`last_success_at` or the cursor, and recording a failure releases the lease so
a sync already in flight cannot report success over it. A check constraint keeps disconnected rows free
of credential, cursor and lease. `secret_key_fingerprint` (Lane 6) names the
key that sealed `secret_ciphertext` (`SecretBox.key_id`, 32 hex characters,
non-secret); every sealing path sets it (Plaid link and update-mode reconnect,
Gmail connect and reconnect), it is null with no credential, and rows sealed
before Lane 6 have none. Account deletion gives up on a credential that does
not open only when its fingerprint is the running key's.

Registered owners may `SELECT` only the non-secret columns (column grant); no
client role can read `secret_ciphertext`, `sync_cursor` or the lease, or write
anything. Proven by `tests/test_ingestion_connections_postgres.py`.

These rows are connection state, never financial records. Imported evidence
and review state belong to reconciliation; canonical activity remains in the
existing activity tables written only through `MoneyService`.

### Gmail sender allowlist

`financial_source_gmail_senders` (migration
`20261002120100_financial_source_gmail_senders.sql`) holds the senders a person
chose for one Gmail connection: `(connection_id, sender)` primary key,
`user_id`, `created_at` and `backfilled_at` (when that sender's lookback window
was last searched; null means the next sync searches it). `sender` is a
lowercased address or domain name with no whitespace, quotes, parentheses,
commas or angle brackets, so it can never inject Gmail search operators. The
connector reads only messages whose authenticated `From` matches an entry.
Rows cascade with their connection and their user, and the Gmail adapter's
`forget` hook deletes them on disconnect. The server writes rows only through the owner's
live Gmail connection (checked in the same transaction). Registered owners may
`SELECT` their rows; no client role can write. Rows never hold message content.
Proven by `tests/test_ingestion_gmail_postgres.py`.

The cursor for a Gmail connection is the mailbox `historyId` in
`financial_source_connections.sync_cursor`; the sealed credential is the
Google refresh token. Access tokens are never stored.

`financial_shortcut_device_tokens` holds one row per Shortcuts connection:
`connection_id` (primary key, cascades from `financial_source_connections`),
`user_id`, `token_sha256` (32-byte SHA-256 digest of the device token; the
token itself is never stored) and `created_at`. Disconnect deletes the row, and
intake also requires the connection to be live. Enrollment counts a person's
live device digests and inserts the new one in a single transaction under a
per-person advisory lock, so the five-device limit holds under concurrency. Row level security is enabled
with no policies and every client grant revoked, so no client role can read or
write it. Proven by `tests/test_ingestion_shortcuts_postgres.py`.

WhatsApp receipt intake keeps three service-role-only tables (migration
`20261008130000_whatsapp_intake.sql`). Phone numbers, provider message ids and
link codes are stored only as HMAC-SHA256 digests under
`ARGUS_WHATSAPP_SENDER_KEY`. `destination_owner_id` references `auth.users`
and is the person today; it becomes the business principal if the Business
boundary proposal is approved.

- `whatsapp_link_codes`: `destination_owner_id`, `code_digest` (unique),
  `reply_language` (`es-419` or `en`, from the web app when the code was
  issued), `created_at`, `expires_at`, `consumed_at`. Single use; issuing a new code or
  revoking the link deletes the owner's unused ones.
- `whatsapp_sender_links`: `destination_owner_id`, `wa_id_hash`, `last4`,
  `reply_language` (copied from the redeemed code; replies use it, not
  `profiles.language`), `status` (`active` or `revoked`), `linked_at`, `revoked_at`. Partial unique
  indexes allow one active link per sender and one per destination; linking
  revokes whichever active link it replaces.
- `whatsapp_inbound_messages`: one row per provider message, unique on
  `provider_message_key`, with `sender_hash`, `destination_owner_id`,
  `status` (`received`, `linked`, `rejected`, `captured`, `failed`),
  `connection_id` (the captured document's statement connection), `error_code`,
  `claim_until`, `received_at` and `updated_at`. Linked, rejected and captured
  are final. A received row whose claim lapsed, or a failed row, is reclaimed by
  a redelivery of the same message. Settling requires the claim the worker
  took, so a worker whose claim lapsed cannot overwrite a newer one. A captured row's draft is owned by
  `financial_document_extractions`.

Row level security is enabled with no policies and every client grant revoked.
Proven by `tests/test_whatsapp_intake_postgres.py`.

## Import reconciliation

### Hosted Business contract foundation (October 10, 2026)

Migration `20261010223000_business_contract_foundation.sql` supplies storage
and constraints for the assigned first hosted flow. Domain schemas live in
`argus.domain.business.contracts`. Runtime adoption, live grants, model calls,
web/WhatsApp wiring and money behavior are separate implementation work.

`financial_import_events.resolution.business` is the sole current Business
resolution, `{schema_version: 1, facts: BusinessFacts}`. Existing event `version`,
`state`, `activity_id` and claim fields remain canonical. Typed facts preserve
known, unknown and owner-does-not-know states with provenance. The legacy scalar
projection is derived at adapters, including explicit nulls which mask prior
extraction. Apply this projection after extraction selection, not through the
legacy `event_facts.pick` fallback that treats null as absent. Unknown kind also
masks direction, so old outflow evidence cannot silently become expense again.
Never persist another current scalar draft, default an activity date
from upload time, or infer account/tax/funding from missing input. The only
default value is unverified DOP currency. Fiscal facts are evidence, not model
tax decisions. Income is a distinct draft kind; expense acceptance does not
establish delivery of all seven Business journeys.

| Table | Durable owner and invariants |
| --- | --- |
| `business_client_grants` | Explicit direct grant to a named `grantee_id` for exactly one `space_id`, issuer, capabilities (`read`, `prepare`, `approve`), creation/expiry/revocation times. No role-derived capabilities and no grant seed/backfill. First-flow service resolves active grants on each operation. Firm identity, firm delegation and issuer onboarding remain unimplemented. |
| `business_sources` | Stable source identity and idempotent `(space_id, source_key)` for one original message, attachment, agent proposal or human `web_action`. Web actions require channel `web` and retain immutable canonical submitted command text, with server-derived source key and actual `member_set` provenance. Direct source updates/deletes fail; owning connection/client deletion cascades through source links and answered questions under the existing deletion policy. Message/proposal/web-action text is immutable; attachment references the existing source connection rather than copying bytes or extraction. A composite FK prevents another space's connection. |
| `business_draft_sources` | Many-to-many source relationships pinned by composite FKs to the same client as the canonical candidate. No facts. |
| `business_draft_revisions` | Append-only `(draft_id, version)` before/after typed fact snapshots, actual actor and grant/issuer display provenance, source IDs, optional turn key and timestamp. Every source ID is checked and locked against the same client on insertion. They are readable history, never an alternative current draft. Updates and direct deletes fail; deletion of the owning candidate/space cascades. |
| `business_questions` | Stable field question, recipient, channel, prompt, allowed answer states and answer-source reference. An owner-does-not-know answer requires its source and moves recipient to accountant. It does not trigger another owner question. Composite FKs scope draft and answer source. Deleting the owning source cascades the answered question instead of clearing its provenance. |
| `business_sender_leases` | One durable holder, monotonic fence and expiry per `(space_id, sender_hash)`. Runtime acquisition/renewal/release must lock this row and check the fence before committing. |
| `business_turns` | Globally deduplicated provider turn key, scoped actual actor/sender, arrival order, phase, model state, immutable typed normalized plan, active lease fence and reply text. A completed model interpretation requires its plan and server-derived `plan_actor: ActorProvenance` snapshot, present together and immutable together, with matching actual actor ID; completion/reply phases require the plan. |
| `business_action_receipts` | Unique `(space_id, actor_id, idempotency_key)` and `(turn_key, action_index)`, canonical input hash, normalized command, immutable actual `actor: ActorProvenance` snapshot (including human commands without a turn), and typed result. Snapshot actor ID must match the receipt actor. Only human `review_draft`/`approve_expense` commands may omit a turn; agent commands require a persisted plan. Agent receipts require the matching action in an already persisted plan of the same client and actor, with identical plan-actor provenance. Identity/command/hash cannot mutate. A settled result cannot change; unknown results allow explicit reconciliation. This is action execution recovery, not another financial ledger. |

All new tables have RLS enabled and no client policies, with anon/authenticated
grants revoked. Only the server projects authorized dossiers and original
sources. The existing import event and observation SELECT policies now permit
only Personal rows. Business rows, including creator reads, use the server's live
grant boundary; Personal owner access is unchanged. Scope foreign keys prevent cross-client links even for service writes;
they do not replace live domain authorization. New records cascade with the
existing source/client lifecycle. Revision actor/grant snapshots remain stable
when a grant is revoked. No new retention exception or grant-issuance policy is
implied by the schema.

Every domain mutation rechecks the live grant and expected canonical version
inside its transaction, then atomically updates resolution, revision, affected
questions/source links and action receipt. Grants are never cached authority. A persisted provenance snapshot records the original grant; resume rechecks that same grant live and cannot substitute another grant or infer history from current grants.
The agent's actor kind only receives read/prepare even if the represented human
has approve. Approval must be a human command bound to the reviewed version.
For the existing reconciliation acceptance path, the permission/version check
and acceptance claim share a transaction; MoneyService runs after that claim
commits. The stored canonical request/key owns idempotent effect recovery, not
a claim of one cross-service SQL transaction. Owner funds creates one expense
without a Business bank debit and leaves capital/debt classification unresolved.
Post-recording correction is unsupported in this slice.

Worker recovery consumes the persisted plan and receipts rather than asking the
model to reinterpret a partially executed turn. Runtime compares normalized
input hashes on replay and rejects changed input. Sender order and lease fences
must be enforced by the worker/domain transaction; storage alone is not proof
of those implemented behaviors. Model or reply `unknown` outcomes require
reconciliation, never blind retry. Lease rows must retain their fence across
release so replacement workers cannot reuse an earlier fence.

### Existing ingestion persistence

`financial_document_extractions` owns the durable draft, the immutable preparation
delivery checkpoint and the reference to the retained source, keyed by the
existing statement connection. It is not a second ledger. `draft` stores source
metadata, consent, preparation status, version and destination
or split proposals. `batch` holds typed observations, receipt itemization,
projection issues and compatible canonical candidates. It may be null before
preparation. `preparation_job` names the current preparation attempt (number,
ID, the draft version it was dispatched for, dispatch time, when its provider
call started, and a retry request) when `ARGUS_DOCUMENT_JOBS_ENABLED` is on.
Only that attempt may claim the draft. The provider-call time is committed
under the attempt's live lease before the provider can be reached. The job is
replaced together with the draft only while no lease is live. Legacy rows can have a batch without retained source; a duplicate
upload can attach that source without changing the frozen batch.

**Retained source objects (#778, `20261008100000`).** The source file lives in
the private Storage bucket `financial-document-sources` at
`{user_id}/{connection_id}/{sha256}`: owner-scoped, unguessable through the
random connection id, and content-addressed, so a duplicate upload writes no
second object. The bucket is private and `storage.objects` has no client
policy, so only the service role reaches it. The row keeps `source_bucket`,
`source_path`, `source_media_type`, `source_size_bytes` (1 to 10 MiB) and
`source_sha256`, all set or all null; a check ties the path to the row's owner,
connection and digest. `source_bytes` is legacy: never written, refused beside a
reference, and still served for rows captured before the move until a later
migration drops it. A retained source always has its draft, and a row with
neither batch nor draft is refused. `argus.domain.ingestion.documents.objects`
owns the put/get/delete interface; memory mode uses an in-memory store behind it.

The October 2 founder clarification explicitly replaces this lane's former
transient-file policy. Source files remain until explicit disconnect/deletion;
rendered images and OCR intermediates stay transient. Row level security and
revoked client grants remain. Owner/live-connection checks protect all draft and
source reads. User/connection deletion cascades; disconnect removes source,
draft and preparation while accepted financial activity follows existing retention.

Capture writes the object first, then locks the live owner connection and
commits the draft and its reference before background dispatch. A crash in
between leaves an unreferenced object, never a row pointing at nothing; an
identical retry rewrites the same path and adopts it, and also restores an
object that went missing (the draft says `source_available=false` until then).
Capture refuses a person whose account deletion run is in flight and removes the
object it wrote. `SOURCE_MAX_BYTES` and `SOURCE_MEDIA_TYPES` in
`argus.domain.ingestion.documents.config` are the code's single copy of the
bucket's limits; a real-Postgres test holds the bucket to them. Disconnect deletes the
connection's prefix (orphans included) before the row, so a failed delete keeps
the row and the idempotent disconnect retry finishes it. Account deletion
deletes the person's prefix as its `storage` step, and once more right before
the auth delete. No
path deletes confirmed financial activity. Draft updates compare versions, and preparation completion
checks the connection lease. Duplicate capture cannot replace a source or reset
an attempt. A persisted in-flight state prevents automatic retry after uncertain
process loss. Queued work can resume explicitly; frozen candidate delivery can
repeat without another model request. The process background task is not the
source of durability.

Preparation status is `saved|queued|preparing|review_ready|needs_attention`.
Approval state remains in reconciliation events. Valid observations can project
independently while incompatible observations stay on the draft with issues.
Opening/running scopes and unknown scopes remain reviewable preparation evidence
without being relabeled into the narrower canonical candidate scope enum. Receipt
items, tax/service, tip and totals do not independently create financial records.
Destination/payer/participant/item assignments remain private proposals and grant
no access or sharing. Canonical Plan owns authorization and fixed currency;
MoneyService owns confirmed financial activity.

Default-off with `ARGUS_INGESTION_ENABLED`. Lane spec:
[financial-ingestion-connectors](specs/lanes/financial-ingestion-connectors.md).
None of these rows is a financial record or affects balances.

- `financial_import_observations`: one row per `(user_id, connection_id,
  external_id)`; the contract candidate JSON (bounded, inert text, attachment
  references only), its content fingerprint, revision count and `live` flag
  (false when the source removed it or a newer observation superseded it).
  Cascades with its connection and its event.
- `financial_import_events`: groups observations of one real-world fact; holds
  state, the person's `resolution`, attention, possible duplicates, the match
  anchor date, the accepting idempotency key and, once accepted, the recorded
  `activity_id`. A check ties `state='accepted'` to a non-null `activity_id`;
  a unique index allows one event per `(user_id, activity_id)`, so one purchase
  cannot be recorded or linked twice.
- `financial_import_account_links`: person-confirmed mapping from
  `(connection_id, account_key)` to an owned `financial_accounts` row
  (owner-qualified foreign key); deleted on disconnect.

All writes run in one per-person transaction under a transaction-scoped
advisory lock. Registered owners may `SELECT` Personal imports; Business import
events and observations are server-readable only. No client role writes. Proven
by `tests/test_ingestion_reconcile_postgres.py`. On disconnect, unreviewed
observations (and events left empty) are deleted; observations of accepted
events are reduced to provenance (source, connection, external id, dates,
status) and kept with the record.
