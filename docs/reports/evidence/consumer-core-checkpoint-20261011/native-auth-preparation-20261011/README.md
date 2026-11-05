# Native authentication preparation and handoff stop

The Consumer lane stopped after preparing a configuration-only simulator build.
The candidate has not been installed or launched. No real challenge, login, or
financial check ran with it. The final Search test remains failed at sign-in,
before its financial steps. Earlier money results keep their own source and time.

## Closed preparation

The build uses source `09a179f00b89968921d9a8f997eee53d19879f5a` on
`codex/consumer-free-tier-completion`. Product source still matches
`40ff4967040c854ca5dd0764115227544011a6e2`. The Search and Budget test repairs
are local commit `f9dae47a562e0c660d5c60d67506d0903ac02fea`.

The retained test app used `http://127.0.0.1:59485/captcha.html` and Cloudflare's
public always-pass test sitekey. The fixture forwards the widget callback.
It does not fabricate a token in its page. [Cloudflare's testing reference](https://developers.cloudflare.com/turnstile/troubleshooting/testing/)
states that test keys produce dummy tokens which real server secrets reject.
That fixture is incompatible with the real staging verifier reported by the
coordinator. The failed login's provider code was not captured, so this does not
establish its exclusive cause.

The prepared override changes only `ARGUS_CAPTCHA_URL` to the existing
`https://cuadrao-web-staging.onrender.com/auth/native-captcha` page.
`ARGUS_API_URL` stays `https://cuadrao-api-staging.onrender.com`.
`ARGUS_WEB_URL` stays loopback. Password recovery is outside this preparation.
The private Supabase configuration and native origin checks remain unchanged.

The bounded receipts establish these results:

- [Public route readback](public-route-readback.json) records HTTP 200 without a
  redirect at 22:25:50 UTC on October 11. The response has `no-store`,
  `no-referrer`, and `DENY` headers. Same-origin static assets contain the native
  handler and approved staging public key. No JavaScript or challenge executed.
- [Mocked adapter tests](offline-adapter-check.json) record four passes, zero
  failures, and six expectations. Callback delivery, error detail suppression,
  and late callback cancellation are covered.
- [Candidate readback](candidate-readback.json) records a passing Release build.
  Packaged Info.plist comparison found only `ARGUS_CAPTCHA_URL` changed.
  Independent review found no blocker within that configuration-only scope.

Cloudflare hostname acceptance, a challenge inside WKWebView, and successful
native login remain unverified. The signed-in Free identity has no Full grant.
This preparation enables no paid or agentic feature.

## Preserved local artifacts

Paths below are relative to
`/Users/garces/.codex/worktrees/4a54/private-alpha-next` unless marked absolute.
Private configuration and credential values are excluded from this record.

| Artifact | Retained path |
| --- | --- |
| One-setting override | `temp/consumer-native-auth-preparation-20261011/StagingNativeCaptcha.xcconfig` |
| Original private configuration | `ios/.build/consumer-staging/StagingConfigured.xcconfig` |
| Existing build cache | `ios/.build/consumer-staging/core-final-20261011-build2/DerivedData` |
| Prepared candidate | `ios/.build/consumer-staging/core-native-captcha-20261011/Candidate.xctestproducts` |
| Prepared build log | `ios/.build/consumer-staging/core-native-captcha-20261011/build.log` |
| Previous test candidate | `ios/.build/consumer-staging/core-search-dismissal-20261011-build2/Candidate.xctestproducts` |
| Final Search failure | `temp/consumer-core-continuation-20261011/search-dismissal-verified/result.xcresult` |
| Private synthetic login | `/private/tmp/cuadrao-consumer-staging-test-login.json` |
| Frozen transfer record | `/private/tmp/cuadrao-consumer-native-auth-frozen-20261011.json` |
| Original preparation scripts and manifest | `temp/consumer-native-auth-preparation-20261011/` |

The existing simulator is `Cuadrao Consumer checkpoint 937`, ID
`C85CDCF9-E5DB-4A86-97FB-65C46B349B35`, iPhone 18 Pro, iOS 27.0.
The app bundle is `local.argus.consumer.staging`. It is signed out and stopped.

The original preparation manifest SHA256 is
`743777910161ec90069630e18907f876b54b24c1fd5c59d09eebc3ce99dfecd5`.
The candidate executable SHA256 is
`00b33dfcde5d600dccd6a8dbcaf4e5e42758f639230f4bc72b1fd6113a04b03b`.
The three auth receipts here are byte copies from that frozen folder.
The original scripts, build logs, candidates, and result bundles remain in place.

Recorded offline commands are below. The completed build's output directory is
immutable. Its retained `build_candidate.py` records the exact command and refuses
to overwrite that output. These commands describe prior checks, not a new run.

```sh
cd web
bun test __tests__/native-captcha.test.ts
```

```sh
xcodebuild build-for-testing -project ios/ArgusFoundation.xcodeproj \
  -scheme ArgusFoundation -configuration Release \
  -destination 'platform=iOS Simulator,id=C85CDCF9-E5DB-4A86-97FB-65C46B349B35' \
  -derivedDataPath "$PWD/ios/.build/consumer-staging/core-final-20261011-build2/DerivedData" \
  -testProductsPath "$PWD/ios/.build/consumer-staging/core-native-captcha-20261011/Candidate.xctestproducts" \
  -xcconfig "$PWD/temp/consumer-native-auth-preparation-20261011/StagingNativeCaptcha.xcconfig" \
  ONLY_ACTIVE_ARCH=YES
```

## Integration and cleanup limits

The [integration preflight](integration-preflight.json) records a conflict-free
calculated tree against `53d2a234bf9e73537537c24a8d35ba1e537827c1`.
It is not a branch merge or current-tip verification. The coordinator later
reported C0 landing at `a6f1f4b3171837d50c82268effa7a12a83df590e`.
The Consumer lane has not reconciled or tested that newer integration state.

The [local inventory](local-handoff-inventory.json) preserves branch heads and
unfinished files. Fixture session `30222` stopped normally with exit 130 at
22:07 UTC. Its PID was not retained. The final process check found no native app,
UI test runner, or `xcodebuild` job. The XcodeBuildMCP processes were left alone.
Port 59485 had no listener. Consumer has no dependency on root session `90751`
or ports 56500 through 56502; no listener appeared in the final check.

No files were deleted. No generated artifact was established as disposable, so
the deletion candidate list is empty. Worktrees, refs, private settings,
credentials, simulator data, builds, and unique results remain preserved.

## Next owner and approval boundary

Consumer owns the local override and build. The web owner owns the existing
native adapter. Lucas and the coordinator own the hosted verifier and hostname
configuration. The assigned backend pin remains
`cad1cbe1ec27ff89c08eadbec31718a0e627383c`; this record makes no new hosted
version claim and authorizes no hosted change.

Lucas requested a Claude handoff after the nearest closed loop. No further
challenge, login, fixture, financial, or implementation phase is active.
On a later approved resumption, the first gate is action-time confirmation for
the normal native challenge and login, plus confirmation of the approved backend
before financial tests. A human challenge belongs to Lucas. The final Search
journey can run only after those gates. Full access, phone work, TestFlight,
guest work, and hosted changes remain outside this handoff.
