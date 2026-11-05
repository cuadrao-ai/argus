# Recovery trusted-header verification

Issue #676, bounded implementation support for #832. No provider requests were made.

## Result

At integration base `7018e0edebbc370b999005a857230bf3c3a1ad8b`, a fixed trusted address with varied first XFF hops and emails reached the synthetic sender 6 times in 6 requests. Fixed XFF reached it 5 times and returned 429 on request 6. The email limiter and global cap already worked.

The new regression tests were committed before the fix as `07731fc65`. The initial run had 1 pass and 10 failures. The fixed candidate has 51 passing tests, no failures and no skips across the focused recovery and account security suites. This closes the address-source bypass, not the process-local counter limitation in #671.

## Design

The route passes `ARGUS_TRUSTED_CLIENT_IP_HEADER` through its existing dependency object. The helper reads only that selected header. Absent or blank configuration uses the existing `CF-Connecting-IP` compatibility contract. Missing or blank trusted values use a stable `unknown` bucket because a web Request has no socket peer. Malformed trusted addresses retain the web route's 400 rejection. No API normalization or IPv6 bucket policy was copied or changed.

The API declaration in `render.yaml` owns the production header value through a YAML anchor. Web derives its value through that anchor, so these declarations cannot be edited independently. Python and TypeScript retain their existing boundary compatibility behavior when no deployment setting is provided. Actual hosted environment values and edge sanitization are not established by this source change.

The design comparison considered helper-owned environment access and a route-supplied dependency. The latter matches existing origin/environment ownership and keeps tests isolated. Type System Discipline and Model the Domain kept the existing typed dependency object and private address selector instead of adding a second configuration layer.

## Checks

Run from repository root:

```sh
bun test web/__tests__/auth-security.test.ts web/__tests__/recovery-client-ip.test.ts
python3 scripts/check_modularity_budget.py
```

Run from `web`:

```sh
./node_modules/.bin/eslint lib/recovery-request.ts app/api/auth/recovery/route.ts __tests__/recovery-client-ip.test.ts __tests__/auth-security.test.ts
./node_modules/.bin/tsc --noEmit --incremental false
```

Focused tests and ESLint pass. The modularity budget passes on the combined tree because the refreshed integration remains the original base. TypeScript is not green. Baseline and candidate each report 8,030 existing diagnostics with identical normalized output. The new tests use Node strict assertions because the repository's Bun expectation declaration produces TS2349 across existing tests. No suppressions were added.

The first focused run could not import i18next in the empty worktree. Reusing the existing installed dependencies resolved that setup failure. An initial ESLint invocation at repository root had no config; running from web passed.

PyYAML resolved both `argus-api` and `argus-app` to `CF-Connecting-IP`. The focused tests cover default, blank and custom settings, varied forwarding headers, unknown fallback, malformed trusted values, malformed untrusted values, same-email throttling and the 100-request global cap. Existing tests retain origin, body, CAPTCHA, generic response and tracked-key cap checks.

## Review and limits

Independent code review found no actionable correctness or security findings. Independent no-comments review found zero deletions, zero MUST KILL findings and zero added suppressions. It retained two configuration-documentation comment lines.

Hosted trusted-header overwrite on each ingress path remains unverified under #694/#832. Actual worker counts, deployment overlap, restarts and effective fleet limits remain open under #671/#832. No live email, model, provider, browser or physical-device run was needed or performed. No hosted setting was changed. No merge or deployment is authorized by this report.
