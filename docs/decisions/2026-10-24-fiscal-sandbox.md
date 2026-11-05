# Bounded Business fiscal sandbox

Decision at fetched parent `67eb3a82aa83c77fc4397d1afd59ec9043b27471`.
Independent architecture review selected one operational journal and one observation
inbox, with a pure projector. Implementation review and hosted activation are separate.

The existing Business authorization, PostgreSQL pool, API lifespan and audited custody
inventory are reused. Captured receipts represent existing documents. Financial imports
represent real money approval. Neither can safely represent an unsent external effect.
No receipt, sale, money entry, collection status or export eligibility is created here.

A protected operator manifest pins at most two synthetic E31/E32 cases: stable document
key, selected Business, account/company/issuer, fiscal number, fixture revision/hash and
canonical payload/hash. Preparation accepts `case_id` only. A different actor or HTTP key
cannot create another operation for that identity. The current human owner must still
hold live approve authority in the transaction that commits first contact. One committed
contact marker produces at most one local create call. Crash, timeout, cancellation,
HTTP 500 and missing identity require read-only reconciliation. They never reset contact
or release a number. This proves local at-most-one contact, not external exactly-once.

Immutable observations own processing, fiscal outcome, XML, PDF and diagnostic evidence.
One projector preserves the first terminal fiscal outcome and flags conflicting terminal
results. A PDF failure leaves acceptance intact. No delivery action is implemented;
`not_requested` is independent of fiscal status. Authenticated callbacks commit before
202, deduplicate semantic evidence, and match exact issuer/number/type on an already
contacted operation. They cannot choose a Business. Unknown/reception-only events remain
quarantined. The documented authenticated probe gets 200 and no fiscal evidence.

Bounded recovery runs within the existing API process. It uses existing provider IDs
only, persisted attempts and fenced leases. No-ID outcomes require an exact authenticated
callback or later separately approved operator evidence. The API proxies private artifact
bytes after live scoped authority checks; HTTPS host/path, public DNS pinning, no redirect,
size/time limits and separate bearer-free storage transport protect the download path.
XML must match immutable issuer and fiscal number at the signed ECF header paths.
PDF parsing proves basic structure only; it does not establish semantic invoice identity.
Future hosted proof must compare the PDF against the approved case. Neither parser
proves cryptographic signature validity.

Both `CUADRAO_FISCAL_SANDBOX_ENABLED` and
`CUADRAO_FISCAL_SANDBOX_CONTACT_ENABLED` default false. Required settings:
`BUSINESS_ID`, `MANIFEST_PATH`, `MANIFEST_SHA256`, `API_TOKEN`, `CALLBACK_SECRET`,
`STORAGE_HOST`, `STORAGE_PATH_PREFIX` with the same prefix. Poll settings are
`POLL_LIMIT` (1..10, default 5) and `POLL_SECONDS` (5..300, default 30).
The installed manifest SHA256 and canonical payload digest are the runtime trust boundary.
Fixture digest/revision are provenance, verified offline against the two preserved source
fixtures with `poetry run python scripts/qa/fiscal_sandbox_contract.py --help`. The harness
permits only the documented identity/date/number substitutions and preserves fixed totals
and fields; it performs no allocation, write, activation or network request.
The protected manifest and credentials are operator installations, never tracked files.
The fixed API origin is `https://sandbox.alanube.co/dom/v1`.

The forward migration is `20261024095154_business_fiscal_sandbox_operations.sql`.
It adds two server-only tables, composite scope, immutable evidence/contact guards,
Business purge cascades and audited provenance custody registration. No applied migration
is edited. Direct anonymous and signed-in database clients receive no table privileges.

## Release and held live proof

The release candidate requires local tests, independent exact-head review and CI.
Do not merge, deploy, apply a hosted migration, install credentials, configure a webhook,
or consume the held document slot under this implementation brief.

Before a separately approved staging activation: verify the exact merged SHA and migration
approval record; check `/usr/bin/curl -q --version` and `pdfinfo -v` on the existing API host;
apply the approved migration with the established migration tool; install only the approved
existing API credential and callback-secret access; install and hash the protected manifest;
read back both false gates and the selected Business/company/issuer. The observation-backed
storage rule is exact configured host plus `/users/`, scoped document path and provider-ID
filename. Keep the callback secret and every presigned query out of evidence and logs.

The future live proof package must bind one owner-approved fresh number, exact fixture
revision/hash and payload/hash, destination, remaining campaign capacity and exact activation
steps. Existing accepted qualification numbers and immutable evidence stay unchanged.
No active manifest or fresh number is supplied by this PR. An authenticated probe, local
fake workflow or HTTP success cannot substitute for hosted end-to-end acceptance.
Rollback disables contact first, then the surface. Retain contact markers and observations
for reconciliation. Never delete a contacted operation to retry issuance.
