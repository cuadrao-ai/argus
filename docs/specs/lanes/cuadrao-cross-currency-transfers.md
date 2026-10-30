# Actual paired transfer amounts

Accepted technical contract for the first #820 Recording slice, October 5, 2026.
Integration base is `875de09ac2115acec42e09060b92878aa5f18eff`. The founder's
[no-conversion rule](../argus-minimum-viable-ecosystem-experience.md#currency-rule)
remains the product owner. This contract adds no Plan or debt-payment conversion.

## Recorded facts and commands

`MoneyRequest.amount` remains the source amount. Add `destination_amount` for
the actual amount received. Mixed currencies require both positive amounts.
Parse each with the selected account's canonical currency and exact minor-unit
parser. Same-currency omission retains equal amounts. Explicit same-currency
amounts must agree. Card/debt payments and reversals remain same-currency.
Non-transfer commands refuse a non-null destination amount.

`TransferAmounts(source_minor, destination_minor)` is the internal complete pair.
Amounts remain on existing leg revisions and currencies remain on accounts.
No new ledger, stored rate, conversion or blended total is introduced.
Correction replaces one complete logical activity revision, with all previous
and replacement account versions, coverage, preview and receipt checks preserved.
An identical retry replays its exact accepted revision. A changed destination
amount under the same key conflicts. A late transaction failure commits no pair.

## Compatibility and privacy

At `MoneyRequest` serialization, omit only the new field when null, including
nested envelopes. Preserve all other explicit null semantics and old hashes.
Each visible leg adds `amount_minor`, `amount`, `currency` and
`currency_fraction_digits`, derived from its account and exact revision.
If the source is hidden, retain null top-level amounts and existing redactions.
Required top-level currency fields derive from the first visible leg.
Both personal canonical-group reads and Household grants enforce this rule.

Current Goal matching, shared Plan candidates, attachment and credited readback
derive `money_reads.activity_in_currency`. It requires the complete expected
role set and exact leg count before checking the Plan currency. Empty or partial
visible pairs cannot qualify. A mixed-currency original or
correction cannot receive credit from its source summary. Destination-credit
Plan support is a separate bounded contract.

## Selection and sequence

Candidate A is the accepted base. Its serializer-level omission protects nested
hashes, and visible-leg denomination retains non-null compatibility fields.
Candidate B adds the explicit internal pair, named refusal codes and strict Plan
boundary. Nullable top-level currency was rejected because it would break current
native contracts without improving privacy. A new request union was rejected
because it would replace every existing command and retry envelope.

Model the Domain keeps the transfer pair out of loan split arithmetic.
Make Operations Idempotent preserves the existing transaction and receipt owner.
Sequence Work into Verifiable Units separates this server slice from native entry,
read/history/correction/retry adaptation, then acceptance and activation.

## Default-off activation boundary

`CUADRAO_CROSS_CURRENCY_TRANSFERS_ENABLED=false` is declared in the existing template
and Render blueprint. The common planner refuses mixed-currency preview and new
confirmation while off; read projection remains available and old accepted receipt
replay retains its contract. This slice changes no native files or hosted flags.

Activation requires accepted native two-amount entry and review, both-denomination
read/history, corrections and persistent retry recovery across supported readers.
Physical-phone and hosted gates remain open. No provider, model or customer calls,
hosted migration, account deletion or deployment are authorized by this slice.
