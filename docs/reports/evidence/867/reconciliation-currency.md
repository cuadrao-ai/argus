# Integration reconciliation after PR #853

The published observer head before this reconciliation was
`84bd432696ecc791c34dcf6bfd2db01084687126`. Its original integration base remains
`7018e0edebbc370b999005a857230bf3c3a1ad8b`. Newly fetched integration is
`2b2d0d9e8ed311c11b7585fbd757fb37f915e12f`, with parent
`d08a133a4e81082ffb3f2738dae92f544cba055a`. Normal merge
`ced29082be4851a6b855df23922d5e7c062cd806` preserves the evidenced history.

PR #853 adds native primary-currency mutation and changes profile updates to
write only explicitly requested fields, then read the authoritative profile.
Its gateway change is confined to `SupabaseGateway.update_user`. The Apple
observer exercises the separate credential repository against `auth.users` and
`auth.identities`, not the profile router or this gateway method. No migration
was added. Apple identity, credential repository, secret handling, test support,
and all three previously tested identity/credential modules are byte-identical
to the prior published head. Native session changes do not participate in this
backend observer test. Thus the prior 12-case PostgreSQL module and 25-case
identity/credential proof remain applicable. This is source-based evidence
retention, not a claim that those database tests were rerun.

The actual identity parser boundary passed [all 11 cases](reconcile-currency-identity.txt)
with zero failures and zero skips in 0.90 seconds. The isolated Python command
used `env -i`, `PYTHONPATH=web:src:.`, and no database or provider credentials.
The [combined modularity check](reconcile-currency-budget.txt) reported zero
violations. The preceding reconciled 23-case canary proof remains applicable
because PR #853 does not change its fixture or production canary scripts.
`git diff --check` passed. No PostgreSQL or Mac resource was acquired. No hosted
changes occurred. Final independent context review and exact published-head CI
remain required before merge.
