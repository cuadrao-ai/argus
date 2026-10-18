# Browser account transition verification

Integration base is `8941c3365e2bd83e1947bcaa9ed1d41709593c5c`.

The local browser reproduction on that base expected `read-new` after a signup confirmation redirect and received `["read-old", "read-old"]`. Recovery had disabled automatic URL detection, and the landing page read the old session without consuming the signup fragment. The fix explicitly ends this browser's previous session, clears API cookies, and passes the signup tokens to the provider SDK for verification before the account probe. Password recovery remains on its separate page.

Business grant storage now includes its owner. A different account and an unowned legacy value resolve to the new person's own Business. Supabase owns identity. Same-account token refresh preserves the choice. The Business app remounts its workspace on account changes, so old panels and drafts cannot survive into the new account. The API transport rejects responses whose auth generation changed and cannot use API cookies when the SDK has no session.

Captures wait for the existing Business bootstrap in the workspace's list effect. Raw record adapters still never bootstrap. Recents use the existing backend-owned `chatAvailable` state. They wait for the workspace and remain closed for accountant context. Genuine forbidden responses still reject with the original status and code. No backend permission, schema, prompt, or provider setting changes.

Local evidence uses invented identities and local HTTP fixtures. It does not prove hosted email delivery or hosted account acceptance. The founder's clean-browser retest remains a separate staging check.

## Checks

- Browser reproduction is committed before the fix in `8624a9b70`.
- Five Playwright cases pass. They cover signup verification with an existing session and a clean browser, reload persistence, invalid verification, failed API-cookie clearing, and a fresh account's own Business startup with persisted old-account context.
- Real Supabase SDK tests pause its user-verification request during session installation. A concurrent local logout leaves both the SDK session and persisted SDK cookies absent for login and verification. The SDK's serialized auth lock provides this ordering. No additional lock was added. A separate reproduced window, logout while verification was clearing old API cookies, previously returned `verified` after the newer logout. A logout-intent revision now cancels that installation; this counter does not change on token refresh. Late SDK completion also cannot restore Business owner metadata or receipt claims after logout.
- Controlled tests cover delayed login/signup responses, delayed session lookup, stale workspace/conversation responses, same-owner refresh, Business remount and a late initial session, and preserved real 403 responses.
- Final full frontend suite: 2,624 passed, zero failed across 268 files (19,353 assertions).
- Production build passes with synthetic local public configuration. Lint has zero errors and eight unchanged warnings in StrategyConfirmationCard and ChatSidebar. Modularity budget and git diff checks pass.
- Integration was fetched again before freeze and remained `8941c3365e2bd83e1947bcaa9ed1d41709593c5c`; no merge was needed. Exact-head CI and independent review are separate release gates.
- The legal-links DOM fixture previously depended on an uncontrolled profile network request and five microtasks. It now uses a deterministic unavailable-profile response, waits for the actual front door, and always unmounts. All seven original assertions are retained.

## Ownership and tradeoff

The coordinator granted only the auth session methods, account-bound Business grant, transport generation checks, BusinessApp outer identity boundary, BusinessWorkspace captures-loading effect, ChatInterface's Recents option, and useRecentConversations availability guard. Receipt field review and focus methods remain unchanged. The legal fixture grant is limited to mount and teardown.

Legacy Business choices are intentionally forgotten because they have no provable owner. Failed verification ends the prior local session and shows the existing generic auth error. A failed cookie-clear response cannot claim a successful logout. Stale request rejection is an explicit `Browser session changed` error. These signals distinguish an account change from a genuine backend authorization refusal.

## Narrow grants

- LandingPage initial auth effect and new auth-verification helper.
- Supabase client identity listener; dependency-free auth-generation helper.
- API login/signup response persistence, session persistence, and current-browser logout; logout-flow result condition.
- Business grant storage owner and authenticated-header lookup; API transport generation checks around header lookup and responses.
- BusinessApp outer auth-owner boundary only; BusinessWorkspace captures-loading effect only; business-data bootstrap ownership.
- ChatInterface Recents option and useRecentConversations enabled guard and invalidation.
- Direct behavior tests and legal-links DOM fixture setup/teardown only.

No ReceiptReviewPanel or receipt-review-page DOM changes. No backend gates, prompts, schemas, production state, hosted configuration, or real email changed. This is local synthetic evidence, with no model calls. The main detection signals are no old bearer/grant after account change, no Business calls before bootstrap, no owner recents for accountant context, and no session/cookies after logout. Genuine authorization errors retain their status and code.
