# #665 guest `captcha_unavailable` UX fixtures

Static HTML fixtures of the empty-chat guest error and AuthForm failure path
(EN). They use the same locale strings and actions as
`EmptyChatSurface` and `AuthForm`. This is **not** a live Turnstile session:
the cloud environment cannot complete a real Cloudflare check, and production
Turnstile is not bypassed.

- `before.png` — parent-tip behavior: generic temporary-chat copy + **Try again**;
  AuthForm still said “try again.”
- `after.png` — this tip: `auth.errors.captcha_unavailable` + **Reload**
  only; composer and starter chips look disabled so they cannot send.
  AuthForm uses the same honest copy and keeps submit.
- `before-after-collage.png` — both columns together.
- `expired-after.png` — ExpiredGuestSession after `captcha_unavailable`:
  honest copy + **Reload** only (no Start new / Sign in / Create account).
- `expired-before.png` — parent tip on that surface: all three actions stayed
  live after the same failure.
- `expired-before-after.png` — those two expired cards together.

Source HTML (gitignored): `temp/issue-665-ux-fixtures.html`.
