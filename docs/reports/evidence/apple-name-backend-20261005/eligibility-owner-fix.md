# Name eligibility has one owner

October 5, 2026. CI at initial PR #869 head `175982863` reported one failing
static privacy guard, 10,284 passing tests, 1,169 skips and five warnings.
`tests/test_preferred_name.py::test_nothing_infers_a_preferred_name_from_conversation`
rejects any runtime reference outside the profile schema owner. The initializer
duplicated a preferred-name absence read. This was an introduced failure, not
a baseline defect. The canonical guard is unchanged, with no new allowlist.

At reconciled head `97f948020aab0aff899d1ccc3d4522a903a40ad1`, the exact case
reproduced as **one failed**, zero skips, in **1.54s**. The captain independently
ran it against source matching integration `7c2522fb7`: **one passed**, zero
failures/skips, in **1.93s**. That baseline used the documentation housekeeping
checkout, whose entire `src` tree and guard file matched `7c2522fb7`; it was not
a claim of a clean detached checkout. No database/provider variables or network
calls were used for that baseline case.

The fix removes both duplicated name-absence reads. The locked database
`name_initialization_closed` marker is the sole eligibility fact. The existing
triggers make open eligibility imply both name columns are absent. Historical
rows start closed; named inserts close it; any explicit update to either name
column closes it even for NULL-to-NULL or same-value writes. A closed marker
cannot be reopened by an ordinary update. No migration or request/response
shape changed and no preferred name is inferred or written by the initializer.

The actual isolated table has only the two eligibility triggers and the existing
verified-Auth-identity trigger. Repository search found no competing profile
name mutation trigger. Four new real-Postgres cases attempt to write either
name column plus `name_initialization_closed=false` in the same statement,
including NULL clears. All finish closed and preserve the explicit choice.
The existing eight name-edit race cases now include that same reopening attempt
in both writer orderings. Direct authenticated updates and client marker
privilege denials remain covered. The real migration proof now tests explicit
false eligibility on inserts with display name, preferred name, or both; all
named rows are closed. Only a new unnamed row remains open.

The exact static guard is now **one passed**, zero failures/skips, in **1.37s**.
The focused API/contract cohort plus the entire preferred-name suite is
**123 passed**, zero failures/skips, in **7.63s**. This includes the previous
104 API checks plus 19 preferred-name checks.
The real isolated Postgres/Auth/name/deletion cohort is **81 passed**, zero
failures/skips, in **8.47s**, with **27** existing pool-default deprecation
warnings. The four added invariant cases increase the prior 77-case cohort;
its four actual parent-lock deletion races and signed Auth no-dispatch proof
still pass. All own synthetic fixtures clean successfully.

The final fetch still resolves to `7c2522fb7d08f183bb1b07cd9b4aabe829089dc0`.
The original integration base remains `2b2d0d9e8`; normal reconciliation merge
remains `5412f94cdc`. Ruff and whitespace pass, generated OpenAPI produces no
diff, and the combined modularity budget has zero violations. No provider,
hosted, native, Mac or flag-activation work occurred. Independent fix review and
exact-head CI remain required. The PG lease is released without stopping the
root-owned stack.

Model the Domain shaped the fix by deriving eligibility from the one durable
marker rather than repeating name facts in Python. Sequence Work into Verifiable
Units shaped the red/green case and the bounded invariant regression checks.
