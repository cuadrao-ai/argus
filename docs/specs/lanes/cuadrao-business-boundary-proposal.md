# Cuadrao Business pilot: ownership boundary proposal

Status: **accepted**, October 8, 2026. The founder approved separate Personal
and Business spaces. The [slice plan](cuadrao-business-space-slice-plan.md)
is the detailed contract, and it wins wherever the two differ. This proposal
belongs to the [Business owner pilot](https://github.com/lagarcess/argus/pull/900).

## Original recommendation

Build the **smallest additive slice of #819**: a Business space owned by the
person, with an explicit space on each root record in the accepted plan. Do not build a
separate business principal identity (option A).

The October 8 proposal records two independent reviews against the original
code base `92599473a`. The evidence pointers below retain that historical
reasoning; their line numbers are not current-code locations.

## Why not option A (business principal)

| Problem | Evidence |
| --- | --- |
| It can't be created as designed. `refuse_placeholder_email` refuses every `@cuadrao.invalid` user that isn't a registered placeholder. Registering one makes Lane 6 refuse to delete it. | `20261004090000_account_deletion.sql:384-404`, `src/argus/domain/account_deletion/service.py:527-531` |
| One missed check exposes another person's data. A principal id and a person id have the same type, so a route that trusts a client-supplied business id can read anyone's Personal ledger. | services take a bare `user_id`, e.g. `recording/postgres_repository.py:93-96` |
| Deleting the person orphans the principal's data. Lane 6 deletes and revokes only `user_id = person`, so the principal's receipts, Storage files and sealed provider tokens would stay unrevoked. | `account_deletion/service.py:731-747` |
| It is not a simple backfill into #819. #819 step 3 makes `user_id` mean `created_by`, a person, so every principal-owned row would have to be re-keyed. | `docs/specs/cuadrao-master-plan.md` §B2.3 |
| Activity would be attributed to the principal instead of the person who acted. | `20260928200000_financial_accounts_first_slice.sql:63-66` (`recorded_by`) |

## Accepted contract and superseded alternatives

The [accepted slice plan](cuadrao-business-space-slice-plan.md#design) owns the technical contract. Its four roots are accounts, connections, import events, and conversations. Children inherit their root's space. The import-event trigger forces the stored event space to agree with the connection space.

The initial proposal used two roots, an owner-membership row, an observation-based event filter, and a `business_conversations` join table. Those alternatives were superseded by the accepted plan. The founder deferred memberships in Q5. `spaces.created_by` owns the sole-owner fact, and `conversations.owner_space_id` owns the conversation's space.

The [original proposal at the published PR head](https://github.com/lagarcess/argus/blob/c7fbd77a231df40f09d1118640dc3a707eca43e0/docs/specs/lanes/cuadrao-business-boundary-proposal.md) preserves those alternatives and their initial reader inventory. It is historical reasoning, not another implementation contract.

The accepted plan records the [migration](cuadrao-business-space-slice-plan.md#1-migration), [reader and writer changes](cuadrao-business-space-slice-plan.md#2-readers-and-writers), and [chat separation](cuadrao-business-space-slice-plan.md#3-separate-chat-histories-and-finance-only-business-chat). Its [deletion and export section](cuadrao-business-space-slice-plan.md#4-deletion-and-export) retains the proposed S5 behavior. That proposal does not establish completed export or deletion-dialog acceptance.

## Delivery boundary, October 10

The default-off foundation has landed. The [slice delivery table](cuadrao-business-space-slice-plan.md#6-sequencing) separates those merged changes from the model-facing work in [#925](https://github.com/lagarcess/argus/pull/925), which is excluded from this documentation landing. Business chat remains off.

The [October 9 handoff](../../handoffs/cuadrao-business-lane.md) records evidence and the pause at that time. Later founder instructions resumed local sandbox capture work. The [current scope reconciliation in #900](https://github.com/lagarcess/argus/pull/900) records that continuation and its limits. The local sandbox checkpoint `df208f7ec2379cd84efd55eea0deb685d67c5360` is unpublished history, outside this PR. Its work is not imported or accepted here.

The [core-flow tracker](https://github.com/lagarcess/argus/issues/942) tracks the broader outcome. Merging this document does not close capture, hosted delivery, extraction, accountant readiness, or a model scorecard. It authorizes no runtime changes, activation, live calls, or hosted actions.
