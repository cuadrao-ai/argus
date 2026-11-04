# Stored Business notifications backend

Goal: preserve each recipient's notification history and read state across requests.
The explicit job 16 brief and issue #1684 scope comment authorize this backend slice.
The product remains the Business receipt workflow in docs/PRODUCT.md.

## Locked decisions

- Base and target: codex/private-alpha-next, fetched at 0d131c55a5ad21e7f36ad88b15cc1c11c6dc1428.
- One default-false server setting owns workspace availability, route refusal and writers.
- Store invitation_received and new_sender_waiting only. No message delivery or copy.
- Recipients read and mark only their own rows, filtered by Business.
- Unresolved items plus items resolved within 30 days list newest first. Unread counts only unresolved unread items.
- An unresolved event identity is unique. Resolution ends that identity's active lifecycle.
- Writes run within a savepoint and log failure without failing the source action.

## Reserved scope

The web bell, founder mock, other events, hosted configuration changes and migration
application remain outside this PR. No files under web except contract types change.

## Contract gates

Update API_CONTRACT.md, api/openapi.yaml, DATA_MODEL.md and all four hosted-setting
manifests. Prove ownership and uniqueness on isolated disposable Postgres, plus
memory parity, writer idempotence, disabled behavior and request-persistent reads.

## Execution contract

One PR. Tests precede each behavior. Run every AGENTS.md check, the hermetic chat
sweep and merged-tree modularity check. Stop at PR, without merge or hosted access.

## Stop conditions

Stop before PR if the diff exceeds about 800 non-test lines. Report unavailable
checks. Invitation decline has no existing membership action; clarification is
pending before implementing that action. Lead-only approvals remain with the lead.
