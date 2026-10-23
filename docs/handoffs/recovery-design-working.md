# Recovery and account security design checkpoint

## Approval and ownership

Founder approved this checkpoint for commit, push, and direct orchestrator handoff on 2026-10-23. Design freezes the checkpoint files at handoff. The orchestrator takes integration ownership after acknowledging receipt. Design resumes only after integration is complete, the integration SHA is supplied, and ownership is explicitly returned.

Branch: `codex/frontend-design-after-auth-20261022`.
Base and freshly fetched integration head: `38bb36620d8480c9c08d2a9503f6a37455416381`.
The exact checkpoint SHA and changed-file list travel with the handoff message.

This approval covers the presented design. It does not certify backend behavior, bypass CI or independent Eval, or authorize deployment. Material changes to the approved experience return to the founder.

## Included experience

- Forgotten-password request, conditional inbox acknowledgment, resend wait, and “Corregir correo” / “Edit email”. Sign-in carries the entered email once in memory, without adding it to a new URL.
- Recovery-link checking, new password, expired or reused link, success, and separate warnings for incomplete session revocation or cookie cleanup.
- Signed-in Account security with current and new password, and the existing local, other, and global session actions and confirmations.
- Approved cream/pine themes, desktop split recovery shell, mobile layout, persistent labels, muted placeholders, eyelash toggle, on-focus password coaching, inline errors, first-invalid focus, and stable button placement.
- Compact session rows with quiet actions, an outlined global action, and wrapping on small screens.
- A narrow shared PasswordField correction prevents an untouched empty field from expanding its on-focus coach just because submission produces an error. Signup/sign-in regression tests cover the shared dependency.
- A persistent polite status region announces accepted recovery sends. Countdown seconds are not live announcements. Scoped wrapping supports enlarged text.

Production routes are `/auth/forgot-password`, `/auth/recovery`, and `/account/security`. Existing auth action defaults remain in use. There are no backend, provider, or service-contract edits.

## Preview boundary

The local review route at `http://127.0.0.1:4387/design-recovery` injects synthetic actions. Choose `screen=request`, `screen=reset`, or `screen=account`. It sends no real email and changes no real password or session.

`web/app/design-recovery/` contains disposable untracked symlinks into `temp/recovery-design/`. These routes and all scratch files are excluded from the commit but retained locally so the founder can review the frozen preview. They must not be copied into integration or deployed.

The account preview language footer now shares the page background. Review navigation appears only with `tools=1`. These surrounding controls and the development indicator are not part of the production account page. The production account view retains its signed-in navigation context.

## Verification

The final focused run passed 82 tests across eight files, with zero failures and 306 assertions:

```sh
cd web
bun test __tests__/recovery-design.dom.test.tsx __tests__/account-security-page.dom.test.tsx __tests__/auth-recovery-page.dom.test.tsx __tests__/auth-security.test.ts __tests__/auth-field-states.dom.test.tsx __tests__/password-field.dom.test.tsx __tests__/auth-form-copy.test.tsx __tests__/auth-email-first.dom.test.tsx
```

Focused ESLint passed for all changed TS/TSX files. Application-source TypeScript passed with `bunx tsc --noEmit -p ../temp/frontend-preview/tsconfig.json`. That temporary config extends the web config, includes app/components/hooks/lib/proxy, and excludes tests/e2e. Full-repository TypeScript is not claimed clean; an earlier full run reported existing Bun test declaration errors. Diff whitespace checks passed.

Local browser checks covered desktop at about 1440 x 900, 390px mobile in both themes, 320px account and expired-link layouts, and a 320 x 360 constrained recovery viewport. Both languages were reviewed. Synthetic rate-limit and partial-revocation states and a successful retry were exercised.

Keyboard checks covered submit, first-invalid focus, error descriptions, inbox heading focus, password eye activation with Space, and confirmation-dialog Tab containment plus Escape returning focus to its opener. Labels, autocomplete, language metadata, and live-region structure were inspected.

A disposable large-text mode doubled computed font sizes and line heights. It exposed heading/action overflow at 320px; scoped word wrapping and wrapping session actions removed the observed overflow. This is controlled stress testing, not native browser zoom certification. The account capture predates the final line-height adjustment and is font-only stress evidence.

The founder rechecked Safari suggested/autofilled password visibility and reported it fixed in the current preview. Typed synthetic text also revealed and hid in native Safari checks. No toggle code change, confirmed root cause, or automated autofill regression coverage is claimed in this checkpoint.

## Evidence

Local evidence folder:
`/Users/garces/.codex/visualizations/2026/10/22/01a164fb-0899-7500-a387-b81e8f79f1a3/`.

- `recovery-checkpoint-review.html` indexes the relevant captures and their limits.
- `sessions-polish-{light,dark,mobile-light,mobile-dark}.png` records the approved session polish.
- `checkpoint-reset-{1440,390}-{light,dark}.png` records reset layout.
- `recovery-request-light.png`, `recovery-request-mobile-light.png`, and `recovery-expired-320-dark.png` record request and expired-link layouts.
- `preview-footer-clean-dark.png` records the final preview-only footer cleanup.
- `accessibility-{request,reset,account}-large-text.png` records the stress checks described above.
- `recovery-checkpoint-tests.log` records the final focused run.

Captures were taken during the approved iteration, before the final documentation commit. They are not represented as fresh captures at the committed head. Older account captures in `password-design-review.html` predate session polish and are not the final account reference. No images are committed.

## Remaining integration and verification gaps

1. Verify the real recovery-link exchange, expiry, reuse, and reload. `hasRecoverySession` currently checks for a user session; verify recovery-specific proof at the provider/service boundary. The synthetic preview does not establish it.
2. Preserve conditional account-existence-safe email responses. Align resend timing with provider limits and honor Retry-After. Accepted sends use the existing 60-second fallback.
3. Keep current-password enforcement for signed-in changes distinct from verified forgotten-password recovery. The founder confirmed a minimum of eight characters and no required character classes in staging and production. Signup confirmation uses an eight-digit OTP with a 3,600-second expiry; that is separate from this recovery-link flow.
4. Verify password updates and global session revocation separately. Partial revocation or cookie-cleanup failure must keep truthful warnings and retry behavior. Check that retry remains possible after local cleanup.
5. Exercise interrupted requests, repeated submissions, corrected email, all three sign-out scopes, and fresh login after success through the connected workflow.
6. Actual screen-reader speech, physical-phone keyboard/OS text size, native browser zoom visual proof, and an operating-system reduced-motion test remain manual checks. Reduced-motion CSS is present, but this pass did not toggle the OS preference.
7. CI, independent Eval, full repository checks, and provider end-to-end verification remain integration gates. No real credentials, provider settings, email delivery, password, or session were changed during design review.

These notes were held locally until the founder authorized this handoff. They are verification requirements for integration, not a claim that backend work is complete.
