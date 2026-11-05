# Core simulator continuation, October 11, 2026

This continuation completed four selected tests. Two passed and two failed,
with no skips. It does not establish complete Core or Full-tier acceptance.

| Selected test | Terminal result | What ran |
| --- | --- | --- |
| Money replacement with empty, grouped and zero amounts | PASS | Entered 200, 1100, 0.00 and 250; checked displayed values; canceled the editor |
| Retained Home after reopening | PASS | Relaunched the app and checked the same Home balance |
| Account archive and restore | FAIL | Fresh sign-in did not reach Home; account creation, archive and restore did not start |
| Search editors and origin | FAIL | Fresh sign-in did not reach Home; Search, account editing and transaction correction did not start |

The passing pair ran from 20:00:23.527 to 20:04:48.235 UTC. The failing pair ran
from 20:08:24.821 to 20:10:39.048 UTC. Preparation started at 19:58:52 UTC.
The terminal summaries are retained alongside this file.

The executable was built from `40ff4967040c854ca5dd0764115227544011a6e2`.
Current Consumer head `4a24d159391bb858e04479d85a3e2bf513498e7c` has no iOS
source difference from that build. Version is 0.1.0, build 1, Release, bundle
`local.argus.consumer.staging`. The simulator is iPhone 18 Pro on iOS 27.0,
`C85CDCF9-E5DB-4A86-97FB-65C46B349B35`. `source.json` records the executable
hash and environment. The API is `https://cuadrao-api-staging.onrender.com`.
The assigned backend pin remains `cad1cbe1ec27ff89c08eadbec31718a0e627383c`;
this continuation did not obtain a fresh hosted SHA readback or change it.

Both failures are at `FinancialLoopUITests.swift:468`, waiting for
`header.profile` after submitting sign-in. The first test signed out the
retained session. The configured CAPTCHA URL is
`http://127.0.0.1:59485/captcha.html`. The initial sandbox probe was denied;
the subsequent permitted loopback probe failed with connection refused.
The local CAPTCHA server was not listening. This is a confirmed missing test
setup dependency, not evidence of an Account or Search financial defect.

The existing `ios/scripts/auth/bridge.py` serves `captcha.html`, which uses
Cloudflare public test keys. It was left stopped under the current auth limits.
No key switch, session injection, hosted auth change or alternate bridge was
used. A later ordinary app launch showed the signed-out welcome, captured in
`signed-out-after-run.jpg`. The retained Home capture shows DOP 26,518.50 and
five unknown balances. Both screenshots were visually inspected.

Budget, Goal, new financial writes, and fault/retry cases did not run in this
continuation. Earlier Budget and Goal passes retain the sources and times in
the [parent checkpoint](../README.md). Retry tests require a fault-proxy build;
this direct-staging build has no proxy opt-in. The existing fault helper only
forwards to a local API, so setting a runner flag would not establish coverage.

The test identity was the existing synthetic signed-in Free account. Shared
manual flows apply to both tiers, but no trusted Full identity was exercised.
No provider call, product edit, hosted mutation, phone action or receipt
extraction ran. Credentials, raw sign-in logs and private runner configuration
remain outside Git. Local result bundles remain under
`temp/consumer-core-continuation-20261011/`.
