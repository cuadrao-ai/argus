# Disposable local sharing walk, 2026-09-17

Result: migration rehearsal passes; sharing publication and signed-out viewing pass; follow-up opens a new guest chat but fails to preserve calculation intent. No production access, schema change, main promotion, or deployment was performed. Canary step 13 was skipped as directed.

## Build and isolation

- Exact clean source: `cfc1988dd80ca1a8007b8f336c107700dd57e009`, detached worktree `/private/tmp/argus-share-walk-7e84`; no tracked source edits before or after the walk.
- Supabase CLI 2.109.0, Docker project `argus-share-walk-7e84`; API `127.0.0.1:57331`, PostgreSQL `127.0.0.1:57332`. Fresh local database, real local Auth and Postgres persistence/checkpointer, no production data.
- Next.js production build passed, served on `127.0.0.1:3138`; Python API served on `127.0.0.1:8138`. Both used the disposable database. API and web ran on the host; Supabase ran in Docker.
- Both sharing flags explicitly `true` through runtime/build environment overrides. Candidate release profile otherwise supplied model/feature settings. Local deviations: development provider credential routing, loopback origins and database/auth credentials, workflow dispatch/shadow/execution disabled, local CAPTCHA token with CAPTCHA disabled only in disposable Auth, telemetry credentials omitted. No hosted Workflow service was exercised.
- `runtime-launcher.py` records the precise configuration setup without credential values. Native SciPy and scipy.linalg import passed at locked 1.15.3.
- Two user questions total, no manual model retries. 13 provider route receipts, all with reported cost, totaling $0.04288399. These are reported receipt costs, not a provider billing assertion.

## Migration readback

Started with 75 earlier migrations. Before readback identified exactly the four candidate migrations as missing. Applied each once, in order, using `supabase migration up --local`:

1. `20260912190000_share_calculation_receipts`
2. `20260913213100_admit_readout_route_receipt_tier`
3. `20260913230000_release_research_guest_claim`
4. `20260914120000_share_plain_answer_receipts`

After readback: 79/79 match, zero missing, unexpected, name or content drift. `public_excerpt_snapshots_kind_check` allows backtest/research_answer/calculation/answer/mixed; `route_receipts_tier_check` allows utility/chat/structured/context/readout. Claim and release functions are SECURITY DEFINER; service_role can execute, anon and authenticated cannot. See `migrations-before.json`, `migrations-after.json`, and `objects-after.json`.

## One browser walk

1. Asked: “I have $1,200 saved. If I save another $300 each month with no interest, how many months until I reach $3,000?” Answer: “You reach $3,000 after 6 months.” The calculation card showed six months. **Pass.**
2. Guest UI has no sharing control. Converted the disposable guest through the normal local signup flow, reopened the preserved conversation, selected its question/answer, previewed, and clicked “Make the link.” **Pass.** No external email delivery; local Auth confirmations are disabled.
3. Opened `/r/<redacted-receipt-slug>` in a separate browser session. Before follow-up, readback confirmed zero cookies and no auth-token storage keys. The public page showed the original question, six-month answer, $1,200 starting balance, $300 contribution and $3,000 target. **Pass.** Link was loopback-only and ceased to exist after teardown.
4. Submitted from that public page: “What if I save $450 per month instead?” It opened a distinct guest conversation with the original shared question and answer visibly attached. **Navigation/context display pass; answer continuity fail.** Actual reply: “Which asset or assets would you invest in monthly with that $450, and over what time period would you like to test it?” Expected arithmetic from the displayed context: four months. No second attempt or product fix was made. This new failure is separate from the two previously accepted promotion-eval failures and has not been waived.
5. A third empty browser session requested the same public link with `Accept-Language: es-419,es;q=0.9`. Labels, date, calculation units, disclaimer and follow-up composer rendered in Spanish (“6 meses”, “Continúa en tu propio chat”). The immutable authored question/answer remained English. **Spanish page pass.**

## Console and failures

- Initial signed-out owner chat: four 401 resource errors (`me` twice, conversations, memory availability), then successful guest creation and answer; four font preload warnings over the initial session/signup.
- Reloaded signed-in owner/share page: zero errors, four unused Space Grotesk preload warnings.
- Signed-out public English page before follow-up: zero errors, one font preload warning. During transition to the guest follow-up chat: three 401 resource errors (conversations, me, memory availability); guest creation and answer still completed. Final reader console: three errors, two font warnings.
- Spanish public page: zero errors, one font preload warning.
- No uncaught JavaScript exception appeared in the retained console logs. Console was not clean because of the above HTTP errors/warnings.
- Build passed with Node `module.register()` deprecation warning. CLI startup first required network access outside the sandbox; one browser run-code syntax error was corrected before signup, without repeating either model question.
- The material product failure is the follow-up's investing clarification instead of savings recalculation. This run does not establish root cause or recurrence rate.

Screenshots: `01-money-answer.png`, `02-link-created.png` (receipt slug
redacted to `/r/<redacted-receipt-slug>`), `03-signed-out-english.png`,
`04-follow-up-failure.png`, `05-signed-out-spanish.png`. Full browser
transcript dumps and accessibility-tree YAML captures are not retained;
privacy-safe aggregates are `link-created-aggregate.txt`,
`english-public-aggregate.txt`, `follow-up-aggregate.txt`, and
`spanish-aggregate.txt`. Console logs beside them keep only aggregate
HTTP/font noise. No tokens, cookies, auth storage, local passwords,
provider keys, Auth UUIDs, or raw receipt slugs are included.

Cleanup confirmation is recorded in `cleanup.json`. Production remains unchanged and promotion is stopped per the latest founder instruction.
