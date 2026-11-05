# Candidate A. One additive destination amount

Design-only candidate for #820. Sources inspected at `/private/tmp/cuadrao-trust-20261005`, HEAD `875de09ac2115acec42e09060b92878aa5f18eff`. No runtime edits, builds, model calls, providers, or hosted access. The parent owns synthesis and any implementation authorization.

## Usage, written before the shape

A user records what left one account and what arrived in the other. For example, USD 100 left checking and DOP 6,050 arrived in savings. The service records both facts without deriving an exchange rate or converting either amount.

```python
request = MoneyRequest(
    kind="transfer",
    source_account_id=usd_checking_id,
    destination_account_id=dop_savings_id,
    amount="100.00",                 # source amount, preserving existing meaning
    destination_amount="6050.00",   # actual destination amount supplied by user
    occurred_at=when,
)
preview = service.preview(user_id=actor, request=request)
# User answers existing per-account coverage questions and reviews both effects.
reviewed = MoneyRequest.model_validate(preview["reviewed_request"])
confirmed = reviewed.model_copy(update={"preview_token": preview["preview_token"]})
receipt = service.write(user_id=actor, request=confirmed, idempotency_key=key)
```

Existing same-currency callers still send only `amount`. Their request, preview, confirm, retry, and correction semantics remain the same. A cross-currency correction supplies both amounts again, the existing activity ID, current expected revision, reason, and all affected account versions. It replaces the whole paired revision atomically. It never patches one leg independently.

The reader consumes each visible leg independently.

```json
{
  "kind": "transfer",
  "amount": "100.00",
  "amount_minor": 10000,
  "currency": "USD",
  "currency_fraction_digits": 2,
  "legs": [
    {"role":"source", "amount":"100.00", "amount_minor":10000,
     "currency":"USD", "currency_fraction_digits":2,
     "balance_movement_minor":-10000},
    {"role":"destination", "amount":"6050.00", "amount_minor":605000,
     "currency":"DOP", "currency_fraction_digits":2,
     "balance_movement_minor":605000}
  ]
}
```

IDs, revisions, coverage, and the other existing response fields are omitted from this example only for readability. Top-level amount/currency remains the primary source-leg summary for a fully visible transfer, never a total, destination amount, or conversion. Cross-currency presentation uses both legs.

## Problem and existing ownership

`money_plan.py` already owns one pure plan containing both account mutations, coverage questions, expected versions, and the preview token. `money_storage.py` and `money_postgres.py` commit that plan with its receipt. Each stored `ExpenseRevision` already owns its own integer `amount_minor`; no new amount storage is necessary. `accounts.py` locks account currency after records exist. These facts make account-derived historical leg currency sound.

The blocker is `money_plan.py`'s universal same-currency guard and its use of `Payment.leg(role)` for every paired kind. Reads also have a single activity currency and no per-leg currency. Extending the payment split model to interpret unlike currencies would be incorrect because `payments.breakdown` subtracts principal and interest from total in one unit.

## Type and signature sketch

```python
class MoneyRequest(BaseModel):
    # All current fields remain.
    amount: str
    destination_amount: str | None = Field(default=None, max_length=40)

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        # Sketch. Preserve every existing serialized field and omission rule.
        # Omit only the new field when absent/null, including nested models.
        ...

@dataclass(frozen=True)
class TransferAmounts:
    source_minor: int
    destination_minor: int

# Private helper in money_plan.py unless actual size justifies a domain module.
def transfer_amounts(
    request: MoneyRequest,
    source: StoredAccount,
    destination: StoredAccount,
) -> TransferAmounts:
    ...

class MoneyLegResponse(BaseModel):
    # Existing identifiers, role, coverage, and signed movement remain.
    amount_minor: int
    amount: str
    currency: str
    currency_fraction_digits: int

# Public service, transaction, MoneyPlan, activity IDs and correction signatures stay.
```

The helper parses each amount using its account currency and the existing exact `parse_minor_units`. It returns positive integer amounts. It performs no conversion, floating-point arithmetic, cross-unit subtraction, fee inference, or stored currency copying. The planner uses source/destination amounts only for transfers. Existing payment validation continues rejecting irrelevant principal/interest/fees/reversal fields and retains its same-currency rule. Avoid making `Payment` represent an FX transfer.

Boundary Discipline places account-dependent amount validation in the existing planner boundary. Laziness Protocol keeps the transaction API and stored records intact. Make Operations Idempotent requires preserving old hash preimages and including the new actual amount when present.

## Behavior contract

| Case | Outcome |
|---|---|
| Transfer, equal currencies, no destination amount | Preserve equal-leg behavior. |
| Transfer, equal currencies, explicit destination amount | Require equal parsed amounts. Unequal amounts introduce a fee/loss contract outside this slice. |
| Transfer, unequal currencies, explicit destination amount | Parse each under its own account currency, require both positive, record the two exact facts. |
| Transfer, unequal currencies, missing destination amount | Refuse with a specific missing-destination-amount error. Never copy the source numeric value. |
| Non-transfer, non-null destination amount | Refuse `field_not_applicable`. |
| Card/debt payment or payment reversal, unequal currencies | Preserve `currency_mismatch`; do not enter split arithmetic. |
| Invalid precision, overflow, zero/negative amount | Existing parser/positive-amount refusal, independently for each leg. |
| Missing or unauthorized account | Existing authorization refusal before any protected effects. |
| Stale revision, account version, coverage or token | Existing refusal with no records, receipts, claims, versions, or balances changed. |
| Identical accepted key and request | Replay exact accepted revision once through existing receipt contract. |
| Same key, changed destination amount | Idempotency conflict, no effects. |

Corrections retain logical activity identity, append-only revision history, and existing record ID behavior. Correcting either account includes all previous and replacement accounts in affected versions. Retired legs receive inactive zero revisions as today. The current group and historical accepted receipt resolve to their respective exact revisions. Coverage and unknown-balance behavior stay per-account.

Plan currency stays fixed. This slice must not silently admit cross-currency contributions through existing same-currency matchers. All Plan transfer eligibility/matching must verify both leg currencies against the Plan currency. `goal_model.transfer_matches` currently checks only the activity summary; `household/planning_contributions.py` also checks that summary at lines 58 and 236. These checks become unsafe if left untouched. No contribution amount is inferred from a source summary. Existing correction/invalidation policy remains in charge; a corrected transfer that ceases to match must become unsupported under that policy, without rewriting Plan currency or silently relinking. Broad cross-currency Plan contribution support requires a separate explicit contract.

## Response privacy and client migration

Every response leg derives currency, digits, and unsigned amount directly from its stored account/revision. Do not add mutable currencies to revision details, an exchange-rate column, or a second balance ledger.

Partial visibility needs special care. `money_reads.visible_activity` and `household/projection.activity` both mask a hidden primary amount today but retain its currency. A cross-currency record would newly disclose a hidden source currency and label destination movements incorrectly. Preserve null top-level amount and existing redactions. Derive legacy top-level currency/digits from the first remaining visible leg when the primary is hidden. This makes the required legacy fields safe display context, not facts about the hidden source. All new displays use leg fields. Keep the existing private-counterpart/editability policy.

Native request encoding adds optional destination amount and omits it when absent. The reviewed command and persisted retry journal retain its exact value. Correction editors hydrate source and destination values from their corresponding legs. Mixed-currency transfer editors expose two explicitly labeled amounts and account currencies; changing accounts invalidates review and clears/revalidates incompatible inputs. Same-currency and Plan/debt-constrained flows keep existing behavior. Update `FinancialActivityTypes.swift`, personal and household transfer editors, details/history/recent rows, and `HouseholdViews.swift:192`, which currently formats a visible leg using activity currency.

Old saved same-currency native records may lack new leg fields. If the client persists such records, its decoder should use a documented legacy decode path that derives leg denomination from the old enclosing activity currency. New response generation always includes leg denominations. Never fill a missing destination amount from the source on a newly received mixed-currency record. Evidence must establish the actual local persistence format before choosing a decode implementation.

## Compatibility and migration

No ledger backfill or schema migration is expected because amounts already live on individual revisions and accounts own immutable currencies. Verify repository constraints before claiming this in implementation.

Hash compatibility is a release-critical detail. Adding a default-null Pydantic field changes `model_dump` output and thus old receipt hashes and preview tokens. Omitting this one new field when null must occur at `MoneyRequest` serialization so nested personal/household Plan request hashes remain stable too. Changing only `money_plan.identity` misses `household/planning.py`'s `canonical_hash(body.model_dump(...))`. Do not globally switch to `exclude_none`; existing explicit nulls encode unlink semantics. Golden fixtures must prove old request preimages are identical, including nested requests and refund omission/null cases. A supplied destination amount participates in both preview and operation identities.

Additive responses allow older decoders to ignore new fields, but old UIs cannot correctly present or correct mixed-currency transfers. Coordinate this first supported native release and do not claim semantic compatibility from JSON decoding alone. A stale client attempting a cross-currency correction without the destination amount is refused, protecting the record. If multiple active client versions must read these records, the parent must decide the bounded capability gate before enabling creation.

## Module responsibilities

- `money_schemas.py` owns the additive field and stable serialization, including nested use.
- `money_plan.py` owns account-bound validation and choosing transfer leg amounts while preserving preview and revision planning.
- `currency.py` remains the sole decimal/minor-unit owner.
- `payments.py` retains same-currency loan/card arithmetic. No mixed-unit extension.
- `money_reads.py` and `money_responses.py` own canonical leg readback; household projections apply existing visibility policy with currency-safe summaries.
- Existing storage modules retain atomic transactions, original owners, locks, and receipt replay.
- Plan matchers enforce their existing same-currency contract using complete leg facts. No conversion or Plan-currency edits.
- Native transfer command/edit/read surfaces own user entry and display; they do not compute exchange rates or reconstruct ledger facts.

## Tests required before implementation acceptance

1. Existing same-currency commands and nested request serializations preserve exact old identities. Old accepted receipts replay after the schema addition; changing destination amount conflicts.
2. USD/DOP, JPY/USD, and a supported three-decimal pair record exact independently parsed amounts. Check positive, precision, overflow, and invalid-text refusal on each side.
3. Preview and confirm show correct per-account currency and movement. Unknown balances remain unknown. Backdated coverage is independent per account.
4. Same-currency explicit equal destination succeeds; unequal destination refuses. Non-transfer destination fields and mixed-currency debt/card/reversal requests refuse before effects.
5. Correct amount, replace either account, change from equal to mixed and back, retry after simulated lost response, and reopen history. Verify IDs, revision order, old receipt replay, retired legs, current balances, and all affected versions.
6. Force transaction failure between leg writes and before receipt insertion. Verify complete rollback. Test stale-account/revision and same-key concurrency with existing repository harnesses.
7. Read source-only, destination-only, full and revoked household visibility. No hidden amount, currency, metadata, account ID, author or linked facts leak. Destination uses its own denomination.
8. Existing same-currency Plan contributions still work. Mixed-currency recording, matching, linking, and linked-activity correction cannot create unsupported Plan progress or alter Plan currency. Test personal and household matching paths.
9. Native fixtures cover old same-currency decoding, paired readback, correction hydration, reviewed-command re-encoding, pending retry recovery, and both localized labels. Run physical-device journey only under the parent's existing authorization.

## Alternatives considered

A structurally distinct dedicated `TransferRequest` with `source={account_id,amount}` and `destination={account_id,amount}` is clearer for a greenfield API. It makes two equal-status amounts explicit and avoids overloading `amount`. It loses here because existing preview/confirm/journal/Plan envelopes all consume `MoneyRequest`, so it requires a new endpoint or union plus adapters and hash migration. It hides more policy per type but exposes a larger migration surface. Prefer it if this slice must also generalize fees, multiple legs, or payment allocation; those are outside the assigned transfer scope.

Adding `source_amount` and `destination_amount` beside existing `amount` was rejected because it creates two source-amount owners and precedence/conflict rules. Persisting an exchange rate was rejected because a derived ratio is not an authoritative conversion fact and the founder forbids conversion.

## Red-flag screen and synthesis status

No new public planner/storage wrapper or staged prepare/save API is proposed. Callers still make one reviewed command. Currency stays with accounts and amounts stay with leg revisions. The small private `TransferAmounts` shape prevents payment split logic from owning cross-currency math without creating a general movement framework. The unavoidable flat-request optionality is validated once at the planner boundary.

This is candidate A only. Parent synthesis is pending. No implementation deviations exist. First implementation step, after selection, is to update the API contract and add frozen pre-change request-identity fixtures plus paired-currency planner tests.
