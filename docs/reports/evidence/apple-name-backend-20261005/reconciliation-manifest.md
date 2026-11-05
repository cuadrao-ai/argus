# Native manifest context reconciliation

October 5, 2026. Fetched current integration is
`5861a8f1b11cfa053e99e2280ddfcfa264abfd66`, the #849 manifest landing after
`7c2522fb7`. Normal merge into the evidenced #869 branch is
`a30004fb4513600847b61d357570054cd8a24aa1`. No rebase occurred.
The original integration base remains `2b2d0d9e8`.

The integration delta adds only `ios/ArgusFoundation/PrivacyInfo.xcprivacy` and
its required-reason evidence. It changes no name, profile, session, deletion,
database, API, OpenAPI, environment or test owner. Complete `src`, `tests` and
`supabase` Git trees match independently reviewed `8a285f08f`. The API/data and
generated OpenAPI files also have no diff. The accepted **123 API/contract** and
**81 real Postgres/Auth** passes and their four parent-lock deletion races are
retained; this reconciliation does not claim they were re-executed.

The unchanged preferred-name static guard was executed after the merge and
passed once with zero failures/skips. The combined modularity budget has zero
violations; whitespace passes. No PostgreSQL lease, Mac, provider or hosted
operation was used. Independent context review and exact-head CI are the
captain's remaining gates. Native name adoption, phone, provider authorization,
hosted migration/readback and activation remain open.
