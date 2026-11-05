# Issue 804 local verification

Original integration base: `dd04130e8aa174db3de6139541d3b2e0f36868d0`.
Current integration: `ce7c7350af9a75019a622016ce3a65dbd17e1cc8`.
Normal reconciliation merge: `0338fe3b0073b998102d63fb9cd0799907e2d8aa`. This source diff has no runtime API/data,
migration, or UI behavior change. Render/release-profile defaults overlap the
shared configuration surface; the root release captain owns sequencing #865
before #804 and must revalidate that merged surface.

Baseline invite units: 35 passed. Current logs cover 61 unit/config checks,
272 mocked eval checks, 9 real PostgreSQL invite checks, and 3 census checks.
The mutation logs deliberately fail: removing only the 96-bit floor defeats
the skewed-secret test; restoring the broad observer mistakes an unrelated
owned advisory-lock waiter for the idle target.

PostgreSQL used the root-leased local synthetic database on port 60332.
Fixtures were created by existing test factories and cleaned by their teardown;
the census DDL probe rolls back. Observer probes use autocommit and exact
worker backend IDs. No hosted data or configuration was inspected or changed.
The existing census ConnectionPool deprecation warning remains.

An initial sandboxed PostgreSQL attempt could not connect and was interrupted.
A combined authorized run passed all 9 invite checks, then was interrupted
before the census finished. Separate complete logs supersede those attempts.
The first observer mutation patched a different module import and did not
exercise the mutation; the recorded mutation uses pytest collection hooks.

Ruff, diff checks, and modularity budgets passed. The reconciled branch is
the would-be merged tree. Existing release-profile test formatting was retained
to avoid unrelated changes.
Independent review and terminal exact-head CI remain the release captain's
next gates; this document is local evidence, not a terminal READY audit.

The integration overlap is deployment configuration: #865 derives both API and
WEB environment arrays from the canonical profile and adds a shared YAML anchor
for the trusted client-IP header. This slice adds two default-off API flags to
that same profile and blueprint. The normal merge preserved both derivations,
their fatal failure handling, and the anchor. The reconciliation loader proof
passed 17 boundary checks. Reconciled focused config tests are recorded in
`reconcile-config.txt`. PostgreSQL code, test and migration fingerprints match
the previously evidenced source exactly, so no PostgreSQL rerun is needed.
