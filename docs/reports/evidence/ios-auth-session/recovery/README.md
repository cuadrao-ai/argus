# Same-browser recovery proof

Local unchanged web at http://127.0.0.1:3001; lane Supabase 58401,
mail 58403 and Argus 58400. Source HEAD 661318138d53882b5280685a39a0e6b9a1c46385.
The five web owner files in source-manifest.json had no worktree changes.
The reproducible helper is an uncommitted lane addition; hash recorded separately.

A recovery-only admin-created synthetic account was used. Native fixture users
were not touched. A dedicated nonpersistent Playwright CLI browser session
`ios-auth-recovery` requested recovery, followed its local email link in that
same context, exchanged the code, submitted a new password and displayed:
“Your password is updated. Sign in again on every browser.”

Results (also result.json): baseline Argus password login 200; after reset old
access /me 401 and old refresh grant 400; fresh Argus login with new password
200; /me identity matched this recovery-only user (200). Exactly two Argus
login attempts total. The new verification session was revoked afterward.
The old access JWT's configured lifetime was 60 seconds and may have elapsed;
its 401 alone is not proof of revocation. Old refresh rejection and the browser
successful global-revocation result supply the relevant additional evidence.

## Test boundary

The unchanged web development build selects canonical LOCAL_QA_CAPTCHA_TOKEN
(`argus-local-browser-qa`). This does not prove web production CAPTCHA behavior.
Local Supabase CAPTCHA remained enabled with Cloudflare's public always-pass
test secret. No hosted settings, provider turns, native callbacks or native
password recovery were exercised. Native WK real-test-widget proof is separate.

## Commands

Run from the assigned worktree, with the authorized isolated stack already up.
Open the CLI in ios/.build/auth-local/recovery-browser (private/headless default):

```sh
/Users/garces/.codex/skills/playwright/scripts/playwright_cli.sh --session ios-auth-recovery open http://127.0.0.1:3001/auth/forgot-password
/Users/garces/.codex/skills/playwright/scripts/playwright_cli.sh --session ios-auth-recovery snapshot
python3 ios/scripts/auth/recovery-browser.py seed
python3 ios/scripts/auth/recovery-browser.py submit --email-ref e19 --button-ref e20
python3 ios/scripts/auth/recovery-browser.py mail
/Users/garces/.codex/skills/playwright/scripts/playwright_cli.sh --session ios-auth-recovery snapshot
python3 ios/scripts/auth/recovery-browser.py reset
/Users/garces/.codex/skills/playwright/scripts/playwright_cli.sh --session ios-auth-recovery snapshot
python3 ios/scripts/auth/recovery-browser.py verify
/Users/garces/.codex/skills/playwright/scripts/playwright_cli.sh --session ios-auth-recovery close
```

Refs are examples from this captured snapshot; obtain fresh refs on rerun.
The helper refuses duplicate fixture creation. Coordinate rate limits before
another proof. Recovery secrets and email verification URL remain only in the
ignored mode-0600 private-fixture.json. Do not promote that fixture, browser
cache, or console/network logs. A content scan found no passwords or session
tokens in other recovery artifact files. Promote only this report, result.json,
source-manifest.json, recovery-ready.png and recovery-complete.png.

## Cleanup

Only the owned browser was closed. The fresh proof session was revoked.
The recovery-only synthetic user remains in the lane-owned local stack until
its owner tears down that stack. No other browser, simulator or service stopped.

After capture the helper received Ruff formatting/import ordering only. Browser-owned web source remains unchanged; source hashes are retained.
