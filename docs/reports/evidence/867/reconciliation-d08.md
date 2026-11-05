# Integration reconciliation after PR #863

PR #868 remains a test-only repair for issue #867. Its original integration base
was `7018e0edebbc370b999005a857230bf3c3a1ad8b`. The fetched integration head is
`d08a133a4e81082ffb3f2738dae92f544cba055a`. A normal merge preserved the published
history at `d79e9b1be1cbfb8138c123bcc9dba2c7114735dd`.

The intervening integration change adds issue #861 evidence and repairs the
synthetic canary fixture in `tests/test_private_alpha_canary_split.py`. It does
not change the Apple observer, identity or credential tests, runtime code,
authentication owner, data contracts, migrations, environment variables, or UI.
There is no shared behavioral owner changed by these two test repairs. The
previous 12-case PostgreSQL module and 25-case identity/credential proof remain
applicable because their tested sources are byte-identical to the reviewed head
`511660c642b6208de46bf1bd3990f9c70b756517`. The prior 272-case mocked proof also
remains applicable because its runtime and harness sources are unchanged.

The reconciled canary fixture file passed all 23 cases, with zero failures and
zero skips, in 8.99 seconds. See [the result](reconcile-canary.txt). The command
used the existing isolated Python 3.11.15 environment and Bun 1.3.14. An explicit
`env -i` environment excluded provider keys and selected `PYTHONPATH=web:src:.`.
Only synthetic ephemeral localhost HTTP servers ran. No database, simulator,
hosted service, or real provider was used.

The first invocation ran inside the filesystem sandbox and could not bind
localhost sockets. It produced 12 passes and 11 setup failures, all
`PermissionError: [Errno 1] Operation not permitted`. Its [separate log](reconcile-sandbox-bind-denied.txt)
is retained. The authorized invocation with local socket access produced the
23-case passing result above. This setup failure is not attributed to product
code and is not concealed as a passing run.

The [combined-tree modularity check](reconcile-budget.txt) reported zero budget
violations. `git diff --check` passed. Deslop inspection found no added runtime
code or unnecessary machinery. Exact published-head CI and independent final
context review remain the release captain's gates. This report does not claim
provider authorization, device acceptance, hosted activation, or completed CI.
