# Business country plan

Status: plan, October 21, 2026. PR 1 is built with this document. PR 2 onward
wait for #1222 (close and ownership transfer) and the Transacciones stack
(#1343, #1344, #1346) as each section says. The design lane's proposal
(`argus-design/temp/pais/proposal.md`, sections 1, 2 and 10) is the product
source for the fields below.

A Business gets a country (`DO`, `US`, `CA`) and a currency (`DOP`, `USD`,
`CAD`), set when the Business starts. The country selects the fiscal rules the
server applies to that Business. Today every Business rule assumes the
Dominican Republic. A person can own several Businesses, each with its own
country, switched from the sidebar Business card. Cuadrao for Cuadrao is the
first US Business, in English and USD, with the bank provider. Lucas creates
that Business in production himself.

## Invariants

These hold for every PR in this plan. A PR that breaks one is wrong.

1. The Business's `country` is the only input to Business fiscal rules. The
   person's `home_country` on their profile never decides a Business's fiscal
   fields, defaults or gates. PR 1 proves it with a test.
2. The server owns the per-country fiscal schema: which identifier fields, tax
   lines, document proof, checks, month-close gates, marks, filings and
   exports apply. One registry, `argus.domain.business.country`, holds every
   per-country fact. The server sends the schema on the workspace and the web
   renders it. The web keeps no per-country table and no literal `"DO"`,
   `"DOP"`, `"RNC"`, `"NCF"`, `"ITBIS"`, `"606"` or `"607"` outside locale
   files and fixtures. Once the schema exists, no DR rule stays hardcoded in a
   second place. The table at the end names every current DR-only check and
   the PR that moves it under the registry.
3. Provider lines (US and CA) and DR statement-import lines land in the same
   `business_bank_lines` store and the same `GET /bank/movements` read, with
   the same states, suggestions and igualar actions. No second table and no
   second read. Any client that reads that route sees provider movements the
   same way.
4. Multi-currency, as iOS already does. Every document, row, movement and
   total keeps its own currency. The Business currency is only the default
   for a new record. The server returns totals per currency and never sums
   across currencies. There are no exchange rate fields, conversions or
   "equivalent" amounts anywhere. The DGII export keeps excluding non-DOP
   records with a reason. PR 1's Business currency never forces a document's
   currency.
5. Every field goes in as an additive, backward-compatible field on the
   existing shared endpoints. No web-only endpoints or variants. No rename or
   removal of a field a shipped iOS build reads. `ios/` holds no caller of a
   Business route today (`grep -rn "/business/" ios` finds none), and every PR
   repeats that check in its body. The bank provider connect flow is a web
   feature: its routes are Business routes any client may call, and iOS gets
   no connect UI and no iOS-specific provider route.
6. Bank connect, reconnect and disconnect are the owner's. A member with
   Editar may igualar and may not link a bank. The server says so through
   `capabilities` on the Business; the web never decides from a role name.

## Data model

`public.spaces` (kind `business`) gains two columns in PR 1:

| Column | Type | Rule |
| --- | --- | --- |
| `country` | `text not null default 'DO'` | One of the registry's codes. A DB check mirrors the registry and a test keeps the two equal. A trigger refuses a change once the row exists. Both apply to `kind = 'business'` rows only, so a later Personal or Household space row carries no fiscal country. |
| `currency` | `text not null default 'DOP'` | ISO 4217, three upper-case letters. Set from the country's registry entry at creation. No edit path in PR 1. |

Existing Businesses take the defaults, so every row today is `DO` and `DOP`.
The fiscal profile columns `business_rnc` and `business_tax_id_type` stay.
PR 3 adds `region` and widens `business_tax_id_type` for the other countries
without a rename.

The country is immutable in PR 1 because it selects the regime that approved
records were validated under. PR 3 replaces the trigger with the design's
rule: a `PATCH /business/space {country}` is allowed while the Business has
no record and answers 409 `business_country_fixed` after.

## The one rule owner

`src/argus/domain/business/country.py` is the registry. PR 1 ships it with the
two facts PR 1 needs and the shape later PRs fill:

```python
@dataclass(frozen=True)
class BusinessCountry:
    code: str        # ISO 3166-1 alpha-2
    currency: str    # ISO 4217 default for new records

COUNTRIES: Mapping[str, BusinessCountry]   # DO, US, CA
DEFAULT_COUNTRY = "DO"
def business_country(code: str) -> BusinessCountry
```

PR 3 adds the fiscal schema to the same dataclass, in the shape the design
proposal names (`FiscalSchema`): `version`, `regions`, `business_tax_ids`
(`rnc` and `cedula` for DO; `ein` and `state_sales_tax_account` for US; `bn`
and `gst_hst_account` for CA), `profile_questions` (US: "do you collect
sales tax?"), `document_fields`, `receipt_states`, `declaration` (DO's
`dgii_606_607`, null elsewhere), `document_checks` (DO's `ecf_qr`),
`ledger_column`, `no_receipt_reasons`, `marks`, `tax_figure` (DO `itbis_owed`,
US `sales_tax_collected`, CA `gst_hst_owed`), `filings`, `exports` (DO `606`
and `607`, none for US and CA in v1) and `bank_sources` (DO
`statement_import`; US and CA `provider` and `statement_import`). Labels are
`label_key`s into the locale files, never raw text. The exporter, the month
close and the schema read take their fields from the same entry. A contract
test reads every country's schema and fails when a `label_key` is missing from
`es-419` or `en`.

## PR sequence

Each PR is one change with its own tests. Base and target are
`codex/private-alpha-next`. Every field is additive on a shared route.

### PR 1. Business country and currency (this PR)

- Migration `20261021020000_business_country.sql`: the two columns, the
  check constraints, the immutability trigger, scoped to `kind = 'business'`.
- `country.py` registry with code and currency.
- `Space` carries `country` and `currency`. Both stores read and write them.
  `create` takes the country and sets the currency from the registry.
- `POST /business/space` accepts `country` (default `DO`). `BusinessSpaceInfo`
  returns `country` and `currency`, so `GET /space`, `PATCH /space` and the
  naming routes carry them too. `GET /business/workspace` and
  `GET /business/overview` return the same two fields.
- Web types in `web/lib/business-api.ts` and the preview fixtures carry the
  fields. No rendering: the design lane owns where the country shows.
- Tests over HTTP in memory and on Postgres, a migration test, and the
  `home_country` test for invariant 1.

### PR 2. Several Businesses per person

Lucas runs DR clients and Cuadrao (US) from one account. Waits for #1222,
which re-keys the one-Business rule on `current_owner_id` and rewrites
`spaces.py` and `scope.py`.

- The limit today: `supabase/migrations/20261008140000_business_spaces.sql:25-28`
  (`spaces_one_open_business_idx`, one open Business per `created_by`),
  `:31-42` (`business_space_of` returns that one row; seven SQL callers in
  the same file, the WhatsApp sender-link trigger at `:125` among them),
  `src/argus/domain/business/spaces.py:100` (`on conflict (created_by)` in
  `create`), and `src/argus/api/routers/business.py:245-305` (`get_space`,
  naming and rename read `open_space(person_id)` and ignore the grant
  header). #1222 moves the index and the function onto `current_owner_id`.
- Migration: drop the unique index. `business_space_of` returns the oldest
  open Business as the primary, used only where no grant header exists: the
  sender-link trigger and `POST /business/space` idempotency.
- `POST /business/spaces` (new shared route) starts another Business with
  `{name, country}` and returns its `GrantedSpaceInfo`. The owner grant is
  born with it as today. `GET /business/spaces` gains `country` and
  `currency` per entry, so the sidebar card switches between them with the
  existing `X-Business-Grant` header.
- `get_space`, `rename_space` and the naming routes resolve through
  `working_scope`, so an owner grant on a second Business reaches it.
- iOS assumes nothing: `ios/ArgusFoundation/Connected/ConnectedSpacesPolicy.swift:29`
  says Business spaces have no backend. The web `BusinessSwitcher` already
  lists grants.
- PR 1's shape holds: `country` is per `spaces` row and `business_identity`
  reads by space id.

### PR 3. Fiscal schema and capabilities served by the registry

- Registry gains the `FiscalSchema` fields above. `GET /business/workspace`
  gains `fiscal_schema` with a `version` the web caches by, and
  `capabilities: {edit_profile, connect_bank, import_statement, igualar}`
  (invariant 6).
- Migration: `spaces.region` (`US-CO`, `CA-ON`, null for DO), nullable;
  `business_tax_id_type` check widens to `rnc`, `cedula`, `ein`, `bn`,
  `gst_hst_account`, `state_sales_tax_account` with a shape per kind; the PR 1
  trigger becomes the records check behind 409 `business_country_fixed`.
- `POST /business/space` and `POST /business/spaces` accept `region`, 422 when
  it does not belong to the country. `PATCH /business/space` accepts
  `country` and `region` under the rule above.
- `GET /business/fiscal-profile` gains `country`, `region`, `currency`,
  `tax_ids: {key: value}` and `answers: {question: code}`; `PATCH` accepts
  them. `GET /business/fiscal-profile/fields` keeps its shape and returns the
  country's forms, empty for US and CA. `fiscal_identity.py` and
  `fiscal_profile.py` validate through the registry.
- Dossiers, Bandeja rows, search results and movements gain `marks: [{code}]`
  so the web stops computing "Falta NCF" (`business-ui.tsx:189-192`).
- The web renders `fiscal_schema` and drops its own literals:
  `BusinessFiscalProfile.tsx:16-27` (lengths and the rnc or cedula select),
  `lib/rnc-status.ts:5-17`, `FiscalDeclarationEditor.tsx:17,68` (606 or 607
  choice), `ReceiptRecordFacts.tsx:13` and `receipt-fact-rows.ts:101` (fixed
  fiscal rows). A web guard test fails on the literals invariant 2 names.
- US v1 is light: the sales-tax profile question, a `sales_tax` money field
  on each document, no document number, no filing file. Canada v1: Ontario
  (HST) and the GST-only provinces, English copy. Quebec, QST and French come
  later. Copy comes through the release copy approval, Spanish first.

### PR 4. Business currency as the only default, and complete per-currency reads

- Draft defaults read `Space.currency` instead of the literal `"DOP"`:
  `domain/business/actions/captures.py:55`, `actions/facts.py:34`,
  `contracts/facts.py:223-224` (only DOP may default) and
  `actions/mutations.py:816-821` (a read may override only a DOP default).
  The Business currency becomes the only default.
- The draft read gains `currency_options: [{code}]` and `currency_default`
  (the Business currency, or the one the read found). Changing the currency
  never changes the number.
- Period reads order currencies with the Business currency first and carry
  `fraction_digits` per block: `currencies[]` on the month close, `totals[]`
  on open items and movements. Every block is complete for every currency.
  `tax_figure` sits inside each currency block, or null where it does not
  apply.
- DGII checks bind to the registry's `declaration`: `dgii_validation.py:79-80`
  (`fiscal_conversion_required`) and `dgii_export.py:238-244` run only for a
  DO Business and only on DOP documents; non-DOP DO documents stay excluded
  with the reason. `month_close.py:145-161` (`in_606`, `in_607`) checks the
  currency too, so a USD receipt with an NCF never counts in the 606 figures.
- Export: a per-currency totals block in the manifest, one summary table per
  currency, a currency column in the records file, no rate field anywhere.
- The web drops its DOP-only readers (`lib/business-month-close.ts:51,235,288-332,576-614,897,940`,
  `BusinessMonthClosePanel.tsx:805`, `transacciones-parts.tsx:76`,
  `transacciones-model.ts:216` which sums rows) and renders the server's
  blocks with the design's currency menu.
- Waits for the Transacciones stack: it changes `month_close_store.py` and
  the movements read.

### PR 5. Month close, marks, filings and exports follow the registry

- `month_close.py:311-334` reads `marks` with `blocks_close` from the
  registry. `GET /business/month-close` gains `close_steps: [{code, count,
  blocks_close, target}]` and `next_filing: {code, due_on}`. A US Business
  has no `missing_rnc` or `missing_ncf` step. The web stops turning reason
  codes into steps (`common.json:2891-2915`, `business-month-close.ts:405-412`).
- `tax_figure` is served by key: DO `itbis_owed`, US `sales_tax_collected`
  (the "collected" figure), CA `gst_hst_owed`.
- `dgii_export.py` and `export.py:403` produce only the exports the registry
  lists; the manifest names what the sheet shows as "Incluye".
  `decide_606` (`actions/service.py:427-455`) answers
  `business_606_not_applicable` where the registry lists no 606.
- `PUT /movements/{line_id}/disposition` takes its `no_receipt_reasons`
  codes from the schema per country.
- Waits for the Transacciones stack and PR 4.

### PR 6. Several bank accounts per Business, with a movement source

- Today `business_bank_accounts` is `unique (space_id)`
  (`supabase/migrations/20261018180000_business_bank_matching.sql:14`), one
  account per Business. A provider brings several accounts.
- Migration: drop the unique constraint; accounts gain `name` and `mask`
  (last four). Each movement item gains `source: "provider" |
  "statement_import"` and `arrived_on`; `accounts[].covered_through` on the
  movements read says "Banco al día hasta".
- Waits for the Transacciones stack: it changes `bank/store_postgres.py`,
  `bank/model.py` and `routers/business_bank.py`.

### PR 7. Bank provider for US and CA Businesses, web only, behind a switch

- Sandbox calls are approved with the existing local sandbox keys only. Never
  production keys. Never print keys. New setting
  `CUADRAO_BUSINESS_PLAID_ENABLED`, default off, declared in `.env.example`,
  `render.yaml`, the release profile and `scripts/ops/staging_env_manifest.json`.
  Routes answer 404 while it is off.
- Today the provider is Personal only: `domain/ingestion/plaid/connector.py:44`,
  `plaid/link.py:123,131,202` and `plaid/sync.py:132` hardcode `PERSONAL`;
  `api/routers/financial_connections.py:32,48` too. Transactions become
  `financial_import_events` through the Personal reconcile path, never
  `business_bank_lines`. The web has no provider connect UI and iOS has no
  provider code.
- Business-scoped shared routes, owner only (invariant 6):
  `POST /business/bank/connections/link-token` (country code from the
  Business, refused when `PLAID_COUNTRY_CODES` lacks it),
  `POST /business/bank/connections {public_token}` returning the connection
  and its accounts, `PUT /business/bank/connections/{id}/accounts
  {account_ids, start_on}`, `GET /business/bank/connections` with `status`
  (`syncing`, `active`, `needs_reauth`, `error`, `disconnected`),
  `POST /{id}/link-token` and `/reconnected` for re-auth,
  `POST /{id}/disconnect` (lines and matches stay). A bank sign-in already
  live elsewhere gets a named refusal code.
- Sync writes `business_bank_lines` through the matching service and runs the
  same suggestions. `business_bank_imports.reader_id` admits `provider`; one
  synthetic import row per sync batch with a nullable `source_connection_id`;
  a line's `line_hash` is the provider transaction id so a replay returns the
  existing row. `GET /business/bank/movements` serves them beside the
  imported ones (invariant 3).
- `PLAID_COUNTRY_CODES` becomes `US,CA` on staging once a Canadian Business
  exists. Production keys need provider approval and cost; open with Lucas.
- The web gets the connect sheet (design section 7). iOS gets nothing.
- Waits for PR 6.

### PR 8. Cuadrao for Cuadrao

No code. Lucas starts the Business in production with `country: "US"` once
PR 2 is live (as a second Business beside his DR one), and connects the bank
once PR 7 is on. This plan records the steps; it does not run them.

## DR-only checks today and where each moves

Kinds: (a) fiscal identity, (b) document proof, (c) tax line, (d) month-close
gate, (e) export, (f) currency default, (g) web rendering, (h) model-facing
text. Paths are under `src/argus/` unless they start with `web/`.

| Where | What | Kind | Moves in |
| --- | --- | --- | --- |
| `domain/business/fiscal_identity.py:3-7,14-41,44-74` | RNC 9 digits, cédula 11, mod-11 and Luhn check digits, error codes | a | PR 3, registry `business_tax_ids` with a validator per key |
| `domain/business/fiscal_profile.py:15-21,43,57-68` | `set_business_rnc` accepts only `rnc` or `cedula` | a | PR 3 |
| `domain/business/contracts/dgii.py:117` and `contracts/facts.py:41-54,157` | `TaxId.type` literal, `Rnc` type | a | PR 3 |
| `domain/business/dgii_validation.py:168-203` and `dgii_line.py:99-124` | per id-type length, check digit, passport rule, `fiscal_b01_rnc_required` | a | PR 3, runs only where the schema lists the key |
| `domain/business/rnc_registry.py:9,72-79` and `export.py:713` | DGII registry lookup, the only mode | a | PR 3, `document_fields[].registry_check` |
| `domain/business/document_type.py:34-72` and `actions/mutations.py:538-606` | Venta detected by matching the issuer RNC to the Business RNC | a | PR 3, compares the Business tax id of any key |
| `supabase/migrations/20261019070000_business_fiscal_profile.sql:4-33` | `business_tax_id_pair` check: rnc 9, cedula 11 | a | PR 3 migration widens the check |
| `domain/business/fiscal_identity.py:77-92` | NCF `B` plus 10 or `E` plus 12, document identity keyed by NCF | b | PR 3, `document_fields` |
| `domain/business/dgii_validation.py:38-49,85-113,154-160,195-267` | NCF series sets, credit notes, B02 rule, 607 e-CF exclusion | b | PR 5, runs only where `declaration` is `dgii_606_607` |
| `domain/business/actions/fiscal.py:21-84` | e-CF from an `E` prefix, duplicate document, refund reference | b | PR 3 |
| `domain/business/contracts/checks.py:27-109` and `domain/ingestion/documents/dgii_qr.py`, `ecf_checks.py` | DGII hosts, QR and e-CF signature checks | b | PR 3, listed under DO `document_checks` only |
| `domain/business/contracts/dgii.py:19,36,47-83` and `dgii_validation.py:123-127,189-211,291-331` | ITBIS fields, totals and limits | c | PR 5, `tax_figure` and `document_fields` |
| `domain/business/month_close.py:110-128,164-217,268-294,380-411` | ITBIS before, charged, paid, owed | c | PR 5 |
| `domain/business/month_close.py:145-161` | `in_606`, `in_607` ignore the document currency | c, f | PR 4 |
| `domain/business/month_close.py:311-334,415-419` and `api/business_month_close_schemas.py:72,109-110` | gates `missing_rnc`, `missing_ncf`, skip for `sin_comprobante` | d | PR 5, `marks` with `blocks_close` |
| `web/lib/business-month-close.ts:157-174,229-281,405-412,489-507,918-931` | client gate union, NCF regexes, `rncPresent`, client fallback blockers | d, g | PR 5, deleted; the server's steps render |
| `domain/business/dgii_columns.py`, `dgii_form.py`, `dgii_export.py:46-411` | 606 and 607 formats, workbook, manifest | e | PR 5, produced only where `exports` lists them |
| `domain/business/actions/service.py:427-455`, `actions/marks.py:19-61`, `api/routers/business_drafts.py:147-157` | `decide_606`, `include_606` marks | e | PR 5, refused with `business_606_not_applicable` where 606 is absent |
| `api/routers/business_fiscal.py:28-31` | `/fiscal-profile/fields` returns 606 and 607 field lists | e | PR 3, returns the country's forms |
| `domain/business/contracts/facts.py:223-224`, `actions/facts.py:34`, `actions/captures.py:55`, `actions/mutations.py:816-821` | only DOP may default, and only a DOP default may be overridden | f | PR 4, `Space.currency` is the only default |
| `domain/business/dgii_validation.py:79-80` and `dgii_export.py:238-244,382` | non-DOP needs conversion, `totals_dop` | f | PR 4, bound to the DO declaration and DOP documents |
| `domain/ingestion/documents/tabular.py:137-196`, `shortcuts/amounts.py:7-37` | e-CF forced to DOP, `RD$` means DOP | f | stays, these read a Dominican document and name it |
| `web/lib/business-month-close.ts:51,235,288-332,530,576-614,829-940` and `transacciones-model.ts:216` | month close is DOP only, two decimals assumed, rows summed on the web | f, g | PR 4 |
| `web/components/business-app/BusinessMonthClosePanel.tsx:805` and `transacciones/transacciones-parts.tsx:76` | `DOP` fallback for headline money | f, g | PR 1 types land, PR 4 reads the Business currency |
| `web/lib/money-entry.ts:55,62` | `RD$` and DOP fallbacks in money entry | f, g | PR 4 |
| `web/lib/business-dgii.ts:5-12`, `business-dossier.ts:20-29`, `rnc-status.ts:5-17` | DR-shaped wire types and client RNC rule | g | PR 3 |
| `web/components/business-app/BusinessFiscalProfile.tsx:16-31,39-144` | rnc or cedula select, 9 and 11 lengths, "606 / 607" text | g | PR 3 |
| `web/components/business-app/FiscalDeclarationEditor.tsx:17-77` | 606 or 607 choice, rnc, ncf, itbis mapping, 606-only refund block, raw server labels | g | PR 3 |
| `web/components/business-app/ReceiptRecordFacts.tsx:13,114-118`, `receipt-fact-rows.ts:101`, `ReceiptReadingState.tsx:26-27` | fixed fiscal rows rnc, ncf, ecf, itbis | g | PR 3 |
| `web/components/business-app/business-ui.tsx:189-208` and `BusinessInboxPanel.tsx:71` | `sin_comprobante` and `missing_ncf` chips computed on the web | g | PR 3, server `marks` |
| `web/components/business-app/ExportRecordsPanel.tsx:70-77,223-228` | one calendar month, "606 and 607 for the DGII" | g | PR 5 |
| `domain/ingestion/documents/extractor.py:58-88` and `models.py:81-104` | reader prompt and field descriptions name RNC, NCF, e-CF, ITBIS | h | scorecard item, see below |
| `agent_runtime/business/interpretation.py:80-96,179` | "the domain alone supplies its unverified default currency", "never add fiscal facts" | h | PR 4 reads the Business currency without touching the text; a change needs a scorecard |

Not DR-specific, left alone: `domain/business/bank/service.py:296` reuses the
`sin_comprobante` word as a bank-line state. `domain/recording/currency.py`
already validates against the CLDR tender set and assumes no country.

## Model-facing text

No PR in this plan changes model-facing text. If the reader must read an EIN
or a sales-tax line from a US document, that is a change to
`domain/ingestion/documents/extractor.py:58-88` and the `Field(description=...)`
at `models.py:81-104`. Both are fingerprinted. That work is a scorecard item
with a live run under `docs/reports/evidence/` and needs Lucas's go. Until
then a US receipt's tax is the generic `tax` fact the reader already returns.

## Decided by Lucas, October 21

1. Several Businesses per person, in this lane (PR 2). Each has its own
   country and currency, switched from the sidebar Business card.
2. US sales tax v1 is light: one profile question, a tax amount on each
   document, a "collected" figure. No filing file (PR 3 and PR 5).
3. Bank connect, reconnect and disconnect are owner only. Editar members may
   igualar and may not link banks (invariant 6, PR 3 and PR 7).
4. Canada v1: Ontario (HST) and the GST-only provinces, in English. Quebec,
   QST and French later (PR 3).
5. Bank provider sandbox calls approved, local sandbox keys only, web only,
   switch default off (PR 7).

## Open with Lucas, not decided here

- ITBIS in US$ for a DR month.
- Cuadrao LLC's state and member count.
- Provider production keys.
- The NCF column in the DR table.
- The Canadian date format.
- Transacciones filtering by the chosen currency.
- Whether the currency choice is per session or on the profile.
- A one-time country correction: PR 3 ships the design's rule (allowed while
  the Business has no record). Say so if a different rule is wanted.

## Risks

- `routers/business.py`, `business_schemas.py` and `business_drafts.py` are in
  the Transacciones stack's diff, and #1222 rewrites `spaces.py` and
  `scope.py`. PR 1 touches the first two in four short hunks and `spaces.py`
  in the selects and `create`. The merges are textual, not semantic.
- The DB check on `country` and the registry's keys are two copies. A test
  compares them so a new country fails until both change.
- A Business created before PR 1 by a Colorado pilot is `DO`. Until PR 3
  lands the correction rule, that pilot waits or starts a second Business
  after PR 2.
