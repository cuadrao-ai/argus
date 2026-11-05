# Atomic confirmed-deletion cleanup unit

Base: fetched integration `8146d16e90633eb543781f8882665482f0d5dca9`. Author owns only the existing session actor acknowledgment API, its executable callers/package tests, and bounded evidence. Candidate `f787ca63af9ba4e6355357ed5e1a8ead5a3dfb21` follows source `b77de5f6`; its test-fixture compile error is preserved.

The acknowledgment requires a synchronous throwing cleanup callback inside the actor, after current identity and completed-receipt validation and before journal removal. No suspension, unsafe overload, default no-op or second completion marker. Filesystem failure keeps the completed journal for cleanup-only retry. A stale receipt while another user owns the session must have no filesystem side effects.

Independent QA reproduced the old external cleanup-before-ack gap on unique temporary files. Final verification includes full package, six filesystem cases, affected deletion cases and a migrated actual synthetic SDK/API/Auth/Postgres case. Historical #875 evidence stays immutable. All file operations use unique temporary roots; actual Application Support and the app receipt store are untouched.

Root owns the Mac and PostgreSQL schedule. Final app adapter and receipt-store wiring remain separate and coordinated with Counsel. No provider/hosted/paid calls, activation or UI acceptance claim. Author stops after publication; independent QA cleans only its own fixtures/services and releases leases.
