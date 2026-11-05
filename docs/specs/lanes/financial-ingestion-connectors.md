# Connected-source ingestion: shared contract and ownership

**Status:** Active lane, October 1, 2026. Default-off behind
`ARGUS_INGESTION_ENABLED`, nested inside `ARGUS_FINANCIAL_ACCOUNTS_ENABLED`.
**Experience owner:** [MVEE §4.6, §4.7 and §5](../argus-minimum-viable-ecosystem-experience.md#4-information-ingestion-one-destination-several-entry-methods).
**Technical owners kept:** canonical activity remains `recording.money_service`
([API](../../API_CONTRACT.md#personal-money-activities-authorized-september-29-2026),
[data](../../DATA_MODEL.md#personal-money-activity-extension-authorized-september-29-2026)).
This lane adds observation and review in front of it, not a second ledger.

## Outcome

Reduce manual entry through three complementary sources that feed one reviewed
import flow:

| Source | Covers | Never claims |
| --- | --- | --- |
| Plaid | Supported foreign (non-Dominican) bank and card accounts | Dominican bank coverage; sandbox success as institution coverage |
| Gmail | Bank alerts, statement notices, due-date notices and attachments, including Dominican banks | That an alert is a full balance or a due notice is a payment |
| Apple Shortcuts | Wallet transaction automations and user-run captures on the person's iPhone | A universal Apple Pay feed or background tracking iOS does not provide |

A person may combine them: local accounts through email and documents, foreign
accounts through Plaid, card taps through Shortcuts. The same purchase seen by
several sources stays one financial event with traceable evidence.

## Decisions resolved inside existing authority

- **No unattended posting.** MVEE §4.7: "Begin with the same draft/review
  boundary. Any future automatic acceptance of trusted feeds requires an
  explicit policy." Every candidate is a draft until the person confirms it,
  individually or in a reviewed batch. Drafts never affect balances, budgets,
  goals, Home or alerts (MVEE §5 Drafts).
- **Gmail connects through Google OAuth** with `gmail.readonly`, the narrowest
  scope that reads message bodies and attachments. It is a Google *restricted*
  scope: production use beyond manually added test users requires Google OAuth
  verification and an annual third-party security assessment, which is a
  founder step. Forwarding is not a substitute for the connection.
- **Plaid is server-side only.** `PLAID_CLIENT_ID`/`PLAID_SECRET` and Item
  access tokens never reach a client, transcript, log or analytics event.
- **Connecting a source shares nothing.** New connections and imported drafts
  are personal. Household visibility continues to come only from explicit
  account grants (household permission policy). Accepting an import onto an
  account that is already shared shares that activity exactly as a manual
  entry on the same account would; review shows that scope before confirming.

## The import-candidate contract

Code: `src/argus/domain/ingestion/contract.py` (`ImportCandidate`). Every
connector emits only this, through `CandidateSink.submit`.

| Concern | Field(s) | Rule |
| --- | --- | --- |
| Source identity | `source.source`, `source.connection_id`, `source.external_id` | The triple names one observation; re-delivery of the triple is the same evidence |
| Provider change | `source.revision`, `source.replaces_external_id` | A newer observation of the same fact; Plaid posted rows name their pending row |
| Observation time | `source.observed_at` | When the source produced or Argus fetched it; excluded from the content fingerprint |
| Kind of evidence | `evidence` | `transaction`, `balance`, `statement_period`, `due_notice`, `payment_notice`, `unclassified` (something financial arrived; the person says what it is) |
| Lifecycle | `status` | `pending`, `posted`, `unknown`, `removed` |
| Account reference | `account.*` | External id, institution, name, last-four mask, currency, type hint. Never a Cuadrao account id |
| Dates | `occurred_on`, `occurred_at`, `posted_on`, `due_on`, `period_*` | Activity date, settlement date, due date and statement period stay separate (MVEE §5 Dates) |
| Money | `amount`, `currency`, `direction` | Positive decimal string plus direction; `currency=None` when the source does not say (no DOP/USD guess) |
| Meaning hint | `kind_hint` | `expense`, `income`, `transfer`, `card_payment`, `refund`, `fee`, `unknown`; a hint, not a decision |
| Display text | `merchant`, `description`, `excerpt`, `attachments[].filename` | Untrusted; normalized to inert, capped single-line text |
| Source files | `attachments[]` | Reference plus SHA-256 and size only; bytes are not in the candidate |
| Doubt | `uncertain` and `unresolved()` | Missing is `None`; doubtful is listed; both must be resolved by the person before acceptance |

Unknown fields are refused (`extra="forbid"`), so a connector cannot pass raw
email bodies or provider payloads through the contract.

## Ownership

| Responsibility | Owner | Not owned by |
| --- | --- | --- |
| Provider auth, fetch, pagination, provider retries, extraction | Each connector | Reconciliation |
| Stable `external_id`; same-source re-delivery, provider modifications and removals expressed as candidates | Each connector | Reconciliation (does not re-derive provider identity) |
| Connection status, freshness, attention warnings, cursor, sync lease, credential sealing, keyed identifier digests | `ingestion.connections` + `IngestionHub` (shared) | Connectors (they call it) |
| Evidence storage, cross-source matching, event grouping, review queue, reviewed batches | Reconciliation (`ingestion.reconcile`, single owner, wave 2) | Connectors |
| Account mapping (hint to `financial_accounts` row) | Reconciliation, confirmed by the person | Connectors |
| Corrections from sources after acceptance (amount changed, removed) | Reconciliation raises a review item; the person corrects through existing activity correction | Anyone silently editing canonical rows |
| Canonical writes, money rules, idempotency, household projection | `MoneyService` and existing recording owners | Ingestion |

### Deduplication rules (reconciliation)

1. Same `(source, connection_id, external_id)`: the same observation. Unchanged
   fingerprint is a no-op; a changed fingerprint is a new revision of it.
2. `replaces_external_id`: the new observation supersedes the named one inside
   the same event (pending to posted), even when the amount changed.
3. Different sources join one event automatically only on a *strong* match:
   equal amount, known and equal currency, dates within five days, both sides
   on the same person-confirmed account, and no contradiction in direction or
   card mask. An event holds at most one live observation per source; two
   different observations from the same source are two different purchases
   unless rule 2 links them.
4. Equal amount and date alone never merge anything. When more than one event
   could match, nothing is linked automatically; the person decides.
5. Statements match against accepted events and open drafts the same way and
   never add a second copy of activity already recorded. Activity recorded by
   other means (manual, voice) is offered as `existing_activity_matches` for
   the person to link instead of recording again.
6. A reviewed batch records only items with no open question (nothing
   unresolved, no duplicate flag, no balance-coverage question, unchanged
   since review); every other item stays for individual review.

## Evidence is not a conclusion

- A due-date notice can inform a Plan reminder; it never marks anything paid.
- An alert's "available balance" is partial evidence (`balance_scope`), not a
  reconciled account balance; at most it proposes a balance check for review.
- A payment-received notice is evidence that may match a recorded payment; it
  does not create one by itself.
- A device notification or pending row is not proof of settlement.

## Disconnect, retention and credentials

- **Disconnect** (`POST /api/v1/financial-connections/{id}/disconnect`) tries
  provider revocation (Plaid `/item/remove`, Google token revocation), then
  always deletes the stored credential, cursor and lease, then deletes
  unreviewed drafts from that connection. Confirmed activity is the person's
  record and stays, with minimal provenance (source kind, dates, external id).
  A failed provider revocation is reported so the person can revoke there too.
- **Retention:** candidates keep extracted fields, a capped excerpt and
  attachment references, never full email bodies or provider payloads.
- **Credentials** are sealed with AES-256-GCM under `ARGUS_INGESTION_SECRET_KEY`,
  bound to `source:connection_id`. Without the key, credential-storing
  connectors stay off.
- **Untrusted content:** email bodies, attachments and notification text are
  data. No model or rule executes them; extraction outputs only contract fields.

## Delivery waves

| Wave | Branch | Base | Depends on |
| --- | --- | --- | --- |
| 0 Contract and connection state | `claude/ingestion-contract` | `15e57931584b21dd7f9e453dbeb9127fc4b8cff3` | none |
| 1A Plaid | `claude/ingestion-plaid` | fresh integration | wave 0 (one-way merge) |
| 1B Gmail | `claude/ingestion-gmail` | fresh integration | wave 0 (one-way merge) |
| 1C Apple Shortcuts | `claude/ingestion-shortcuts` | fresh integration | wave 0 (one-way merge) |
| 2 Reconciliation and review | `claude/ingestion-reconciliation` | fresh integration | waves 0, 1A-C |

Each worker branch starts from freshly fetched `codex/private-alpha-next`,
records its base and merges unmerged dependencies one way. No branch is rebased.

## Verification levels

Evidence is labeled with the level it actually reached:

- **Sandbox:** Plaid Sandbox through server-side credentials.
- **Mocked provider:** Gmail API and OAuth replayed from recorded,
  synthetic fixtures until a Google Cloud OAuth client and an explicitly
  authorized test inbox exist.
- **Physical device:** Shortcuts behavior on a real iPhone. Simulator or VM
  runs cannot prove Wallet or notification automation.

## Open founder decisions

- Automatic acceptance policy for any feed (not authorized; drafts only).
- Google OAuth verification and security assessment for Gmail production.
- Plaid production access, pricing and institution coverage beyond Sandbox.
- Native review presentation adoption with the iPhone delivery owner.
