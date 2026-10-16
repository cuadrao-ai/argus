# Shared staging email layout

Owner is the shared email layout lane. This change unblocks signup code delivery
and gives the personal waitlist the same layout without account codes.

The canonical renderer is `marketing/lib/email/account-layout.ts`. Run
`node scripts/emails/sync-layout.mjs --check` to check the generated web copy.
Separate Render roots require deploy-local files. The generated copy avoids a
runtime dependency across those roots without creating a second design owner.

`bun scripts/emails/render-staging-auth.ts` writes synthetic HTML previews and a
staging Auth template payload under the ignored `temp/staging-auth-email/`.
It does not read credentials, apply configuration, send email or change the hook.
The root coordinator owns staging activation after the exact-head Eval.

The account body text comes from the approved staging sender brief. The current
lane supplies the shared footer and the signup code expiry line. Two subject
choices remain pending product approval before activation. Magic link uses
"Tu enlace para entrar" and reauthentication uses "Tu código de verificación".
These drafts remove codes from non-signup subjects as required by the latest lock.

The screenshots use synthetic tokens and locally served wordmark assets. There
are light and dark renders for six account actions and four waitlist templates.
Waitlist copy comes from the separate waitlist writer. The waitlist footer uses the configured postal address and has no Business pitch.
The launch preview has no body because no launch wording was supplied. It cannot send automatically.

Local verification covers HTML escaping, unsafe URL refusal, unbroken codes,
mutually exclusive waitlist unsubscribe and account code content, footer position,
HTML and text action parity, generated-copy parity, and eleven color pairs.
Every pair passes WCAG AA at 4.5:1 or better in its stated mode. The screenshots
prove browser rendering, not every email client. The button includes a conditional
VML path for desktop mail clients. The HTML has no tracking pixel. Provider-level
tracking and actual staging inbox delivery remain hosted checks for the coordinator.

Detection signals remain the existing Auth hook HTTP result and provider delivery
status. No recipient, code, token or raw message is added to logs.

Verification on the delivery tree passed 2,662 web tests in 276 files with 19,455
assertions. The final focused email set passed 18 tests. The production web build,
changed-file lint, whitespace checks and modularity budget passed. Twenty-two
local screenshots show the old recovery layout and the new account and waitlist
layouts in both color schemes. No hosted inbox result is claimed by these checks.
