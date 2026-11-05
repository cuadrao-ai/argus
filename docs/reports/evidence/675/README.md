# Issue 675: feedback attachment picker removal

Playwright captures of the written feedback dialog on
`codex/private-alpha-next` @ `7c05021` (before) and this worker branch (after).

- `before/feedback-dialog-en.png` — Settings → Feedback → General Feedback, with the attachment dropzone that only sent a file count.
- `after/feedback-dialog-en.png` — the same path after the picker was removed.

Captured by `web/e2e/feedback-dialog-no-attachments.spec.ts` with
`FEEDBACK_DIALOG_SHOT_DIR` set.
