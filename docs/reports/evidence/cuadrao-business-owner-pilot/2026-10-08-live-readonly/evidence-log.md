# Live read-only check: configuration and record counts

October 8, 2026. The founder authorized this check: read-only, with no receipt contents, personal details or secret values. It replaces any inference from `render.yaml` or default flag values.

## Method

**Render.**
- Calls: the Render API's service list, then the environment variables of `argus-api` (`srv-d78tanmuk2gs73e17nn0`) and `argus-app` (`srv-d7ap6bmslomc73eqp8m0`), then the environment groups.
- Printed: only feature-flag keys and their values, plus whether each Supabase URL contains the production project ref. No secret value was printed.

**Production Postgres.**
- Target: project `lgdhvepyrzbnscqssgqq`. Both Render services point at this ref.
- Access: the session pooler, inside a transaction with `set transaction read only`, which the server confirmed as on.
- Read: only table existence, row counts and Storage object counts per bucket. No rows, names, file contents or personal data.

## Live configuration

- **argus-api:** 67 service variables; `ARGUS_PERSISTENCE_MODE=supabase`.
- **argus-app:** 13 service variables.
- **Environment groups:** none.
- **Not set on either service, so off by default:**
  - `ARGUS_FINANCIAL_ACCOUNTS_ENABLED`
  - `ARGUS_INGESTION_ENABLED`
  - `ARGUS_DOCUMENT_EXTRACTION_ENABLED`
  - `ARGUS_BUSINESS_PILOT_ENABLED`
  - `ARGUS_WHATSAPP_INTAKE_ENABLED`
  - `NEXT_PUBLIC_BUSINESS_PILOT_ENABLED`

## Production records

| Check | Result |
| --- | --- |
| Migration ledger | 81 rows, head `20260914120000` |
| `financial_accounts`, `financial_source_connections`, `financial_document_extractions`, `financial_import_events`, `financial_import_observations`, `financial_activities` | tables do not exist |
| `spaces`, `whatsapp_sender_links`, `whatsapp_inbound_messages`, `whatsapp_link_codes` | tables do not exist |
| `conversations` | exists, 676 rows |
| Storage buckets | none |
| Storage objects | none |

## What this establishes

- Production has never stored a financial record, a document source, a Storage object, a Business row or a WhatsApp link.
- No hosted data yet constrains a code rollback for C1 or B1 to B4.
- The minimum compatible code version starts the first time new-format data is written in hosted. Each enable request will name that version.
- Migration B4 adds a nullable `owner_space_id` to the 676 existing conversations. Every existing conversation stays Personal.
