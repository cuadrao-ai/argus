# Candidate B: paired actual amounts for cross-currency transfers

Grounded at `875de09ac2115acec42e09060b92878aa5f18eff`. This is a source-only design candidate for #820. It proposes no runtime write, provider call, conversion, rate, or combined-currency total.

## Problem and caller usage

A transfer between a DOP account and a USD account has two actual bank amounts. The current `MoneyRequest.amount` supplies one amount, and `money_plan.plan` rejects accounts with different currencies before it creates legs. The accepted revision format already stores an amount on each account leg. Preserve that single logical activity and its atomic correction, preview, and receipt rules.

The caller reviews and confirms the same command. `amount` remains the source amount for a transfer. A cross-currency transfer also requires `destination_amount`. Currencies come from the selected canonical accounts. For example:

```json
{
  "kind": "transfer",
  "source_account_id": "<DOP account>",
  "destination_account_id": "<USD account>",
  "amount": "6000.00",
  "destination_amount": "100.00",
  "occurred_at": "2026-10-05T12:00:00-04:00",
  "expected_versions": {},
  "coverage": []
}
```

`POST /financial-activities/preview` returns both account effects and a `reviewed_request` containing both entered amounts. Confirmation sends that exact reviewed command, its `preview_token`, and an `Idempotency-Key`. A read returns the existing top-level `amount=6000.00, currency=DOP` for a reader authorized for the source, plus a destination leg with `amount=100.00, currency=USD`. The source movement is negative 600000 DOP minor units and the destination movement is positive 10000 USD minor units. No numerical relation between those values is inferred or checked.

An existing same-currency caller may keep sending only `amount`; the destination amount is then exactly equal to it. A caller may send the second amount explicitly for a same-currency transfer, but it must equal `amount` exactly in minor units. A correction involving different currencies must supply both actual amounts again. Neither omission nor a correction can copy an old source amount across currencies.

## Shape and signatures

Keep the transport DTO additive and build a stricter domain shape at the Recording boundary. The role-specific pair exists once inside planning. This gives callers a small compatible interface and keeps invalid cross-currency postings out of the core.

```python
# money_schemas.py, external command
class MoneyRequest(BaseModel):
    kind: ActivityKind
    amount: str                         # existing field; source amount for transfers
    destination_amount: str | None = None  # transfer only
    # existing fields unchanged

# money_plan.py or a small recording-owned amount module, internal only
@dataclass(frozen=True)
class TransferAmounts:
    source_minor: int
    destination_minor: int

    def for_role(self, role: Literal["source", "destination"]) -> int: ...

def transfer_amounts(
    request: MoneyRequest,
    source: StoredAccount,
    destination: StoredAccount,
) -> TransferAmounts: ...
```

`transfer_amounts` parses each decimal with `currency.parse_minor_units` using its account currency, checks both are positive, and requires `destination_amount` when currencies differ. The same-currency one-amount case copies the parsed integer as an explicit compatibility rule. It rejects a second amount on every non-transfer kind and an unequal second amount on same-currency transfers. It never accepts a client-provided currency or exchange rate. Name stable errors such as `destination_amount_required`, `destination_amount_invalid`, and `field_not_applicable` in the API contract; reuse existing precision/range error behavior where possible.

`money_plan.plan` keeps the current selected-account, eligibility, version, date, coverage, and correction machinery. Restrict its same-currency guard to kinds whose current contracts require it. For `transfer`, call `transfer_amounts` and create source and destination `ExpenseRevision.amount_minor` independently. For single activities and card/debt/payment-return kinds, keep the existing `payments.validate` path and its same-currency/split rules. Do not make `payments.Payment.principal` carry a transfer's received amount, because principal and actual destination amount are different concepts.

`money_reads.render_activity` derives each visible leg's `currency`, `currency_fraction_digits`, positive `amount_minor`, and formatted `amount` from that leg's stored account and revision. Its existing top-level amount/currency remain the source-side compatibility view when authorized. `MoneyLegResponse` gains these additive fields. This is a read projection, not a second stored amount. `visible_activity` must redact top-level source amount **and source currency/fraction digits** when the source leg is hidden; those top-level fields then become nullable in `MoneyActivityResponse`. The authorized destination leg still states its own actual amount and currency. This avoids leaking a private funding currency through a destination-only Household read.

The exact persisted pair is already present in the two `ExpenseRevision.amount_minor` values and corresponding `financial_record_revisions.amount_minor` movements. `financial_activity_groups`, exact revision memberships, account versions, and receipts keep one logical activity ID and one activity revision. Inspect SQL constraints and loaders during implementation, but do not add a JSON pair, mutable currency column, rate column, or separate transfer table. Account currency is the denomination owner; leg amount is the movement owner. This follows the repo's split-brain rule and the Model the Domain, Type System Discipline, and Boundary Discipline principles.

## Behavior contract

| Case | Required result |
| --- | --- |
| Same-currency legacy transfer with only `amount` | Same payload, posting, IDs, preview, and read semantics as today. |
| Cross-currency transfer with two explicit amounts | One activity revision; exact source debit and destination credit in their own minor units; neither rate nor combined amount. |
| Cross-currency missing or invalid destination amount | Refuse before preview readiness or persistence. Never infer from source. |
| Same-currency unequal explicit pair | Refuse. There is no approved loss, fee, or gain posting for the difference. |
| Card/debt/payment return with a destination amount | Refuse as inapplicable. Existing same-currency requirement and payment component caps remain. |
| Correction or moved account | Recalculate both legs from the new complete command, retire old legs, retain logical ID, append revision, and include old/new account versions and coverage in one atomic plan. |
| Retry after response loss | Same idempotency key and identical full command replay the recorded revision; changed second amount conflicts. |
| Source-hidden read | Show only authorized destination leg; no private source amount, currency, ID, notes, or costs. |
| Home/summary | Transfer stays zero income and zero spending; each account position moves only in its own denomination. |

`request_identity` hashes the JSON form of `MoneyRequest`. Adding an optional field would otherwise change every old hash by adding `destination_amount:null`. Its hash projection must omit `destination_amount` when null, preserving old preview tokens and stored receipt replay, and include it when supplied. The existing refund omitted-link special case remains intact. Confirm must still compare the complete expected-version set, current revision, and preview token under owner/account locks. A failed validation or stale confirmation changes neither leg, account version, receipt, nor Plan claim. A correction may change source and destination amounts independently only through an explicitly reviewed revision.

## Plan boundary and sequence

Plan's currency remains fixed. Initial Recording delivery enables a standalone cross-currency transfer while current Goal linking keeps refusing it. That refusal is important until Goal's full destination-amount contract is ready: `goal_commands.attach`, `goal_model.transfer_matches`, `goal_projection.contribution_minor`, and `GoalService.candidates` currently assume source and destination have the goal currency and credit `actual["amount_minor"]`, which is the source amount. A partial change there would over-credit a USD goal funded from DOP.

The next bounded Plan unit can consume the **destination leg's** amount and canonical currency as the actual contribution in the goal currency, while accepting a source account in another currency. A scheduled goal transfer remains an intention expressed in the goal currency; recording it asks for the actual source and destination bank amounts. The original transfer remains the only Recording fact, and the goal claim remains a link to its current exact revision. Correction, relink, pool backing, inclusion, and `needs_review` must all recalculate from that destination leg. No plan total, schedule, target, or stored attribution changes currency. Debt and card cross-currency payments remain rejected until their own component/cap contract is designed.

## Ownership and migration

| Owner | Change |
| --- | --- |
| `docs/API_CONTRACT.md`, `docs/DATA_MODEL.md` | Define amount roles, explicit-pair requirement, leg response, privacy/nullability, retry and correction rules first. |
| `money_schemas.py`, `money_plan.py` | Add one optional wire field and one transfer-only typed pair parser; preserve other kind contracts. |
| `money_reads.py`, `money_responses.py` | Derive per-leg amount/currency and redact hidden source fields. |
| `money_storage.py`, `money_postgres.py`, `canonical_groups.py` | Verify existing atomic per-leg writes and exact group resolution; change only if a proved invariant assumes equal leg amounts. |
| API/native/Household clients | Show two labeled actual amounts for mixed currency; render each leg using its own currency; reuse reviewed_request for confirm. |
| Plan goal modules | Separate follow-on adaptation with destination-denominated credit and its own acceptance evidence. |

No data backfill should be needed for existing equal-currency revisions. Readers derive a new per-leg amount from existing records. Roll out server response additions before native clients require them. Old clients cannot create mixed-currency transfers because they cannot send `destination_amount`; they retain their same-currency path. If an old client sees a new mixed-currency activity, per-leg response fields allow a new client to render it correctly, while old clients need a release/compatibility check for top-level nullability and correction editing. Do not enable cross-currency creation until all active readers can show both bank amounts without presenting a false equal-amount transfer.

## Tests and evidence to ask of implementation

Use hermetic unit/API and both memory/Postgres atomicity tests, then connected client QA. Cover DOP to USD and reverse direction, zero- and three-decimal currencies, exact precision/range, missing/zero/negative destination amount, same-currency compatibility, same-currency unequal pair, and every non-transfer kind with a supplied second amount. Confirm both leg positions, coverage questions, exact history, account versions, Home zero-spending treatment, and visible-leg privacy. Exercise correction that changes either amount or account currency through account replacement, stale preview, same-key replay, same-key different-pair conflict, and rollback after a late write failure. Preserve legacy receipt/hash fixtures for old requests. Once Plan is explicitly in scope, test destination-denominated goal credit, correction, included allocation, schedule fulfillment, release/relink, retry, and no double claim.

## Alternatives and synthesis judgment

| Shape | Strength | Why it loses or wins |
| --- | --- | --- |
| **B, additive wire field plus internal `TransferAmounts` pair** | Small external change; explicit role-specific internal state; reuses exact leg storage. | **Recommended base.** One parser owns currency and pair rules. The external DTO remains weak until account-aware validation, which is unavoidable because account currencies are stored facts. |
| Minimal additive scalar only, branch on `destination_amount` throughout current code | Fewest edits initially. | Loses on repeated optional-field checks in planner, reader, and Plan. It leaks the pair invariant across modules and invites `amount or destination_amount` fallbacks. |
| New discriminated request union with `{kind:"transfer", amounts:{source,destination}}` | Strongest wire type and clearest caller labels. | Loses now because every existing endpoint, nested Plan/Household/import request, generated schema, and native caller expects one `MoneyRequest` with required `amount`. A parallel legacy/new transfer variant creates a larger migration surface for the same posting rule. This may become attractive at a deliberate API version boundary. |
| Store rate or converted aggregate beside transfer | Could support derived views. | Rejected by the founder's no-conversion lock and would create a second mutable money truth. |

Red-flag screen: The typed pair hides parsing and currency policy behind one transfer-specific interface, so it is not a shallow module. It never exports storage or HTTP types as its domain API. `money_plan` stays the single operation owner, so no load/validate/save pipeline is added. Do not add a forwarding service or duplicate transfer planner. The most serious review risk is allowing `money_reads` or Goal to continue interpreting the source top-level amount as the destination amount.

The first implementation step would be to revise the API/data contract and add failing tests for exact two-leg posting, refusal and replay at the current Recording boundary. This design stops before implementation and leaves Plan expansion as a separate explicit contract decision.
