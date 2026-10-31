# Issue #598: bounded checks for an unanswered saved user message

## Current follow-up

The web now keeps reading saved messages every two seconds while its loaded
transcript ends in a user message. This closes the reported interleaving where
an idle activity read is paired with a newer saved user-message id and the
ordinary activity loop stops before the assistant reply is saved.

The user-message role, id, and creation time come from the raw message API,
before UI projection. Repeated reads of that same message never extend its
turn deadline. The check stops on a saved assistant reply, a canonical streamed
reply already shown by the sender, or the runtime timeout. The web build exposes
only `CUADRAO_RUNTIME_EVENT_TIMEOUT_SECONDS`, with the requested 180-second default.
Old unanswered messages do not start a new timeout window; expiry aborts an
in-flight reply check and ignores its late result.

The existing API freshness check, anchors, scroll preservation, request
coalescing, and sender deduplication remain. Account/conversation changes, local
request ownership, and transcript readiness cancel the observer timer. This
follow-up changes web code and tests only. It adds no database or migration
change and does not change the activity API's existing two-read design.

## Exact interleaving and browser proof

1. Both tabs load the same saved conversation.
2. Tab A starts a turn; its user message is saved before the reply.
3. Tab B receives `idle` activity with that newer saved user-message id and
   reloads the user message. Every activity projection delivered to B is idle.
4. The assistant reply is saved and delivered to A. No focus or activity event
   is sent to B afterward.
5. B's bounded saved-message check loads the reply, then stops. Both tabs show
   one reply and B shows only one user message.

The English and Spanish cases fail on reviewed head
`0ce4b621b3f7d8b765e1462a4f5ef63d71bfab60`. Both pass after the web-only fix.
The original 17 accepted browser cases also pass, including anchors, scroll,
hidden observers, idle-only updates, and sender deduplication: **19 passed**.

| Locale | Observer before | Observer after |
| --- | --- | --- |
| English | [red](v3/red/598-v3-interleaving-en.png) | [green](v3/green/598-v3-interleaving-en.png) |
| Spanish | [red](v3/red/598-v3-interleaving-es-419.png) | [green](v3/green/598-v3-interleaving-es-419.png) |

[Red log](v3/browser-red.txt), [green log](v3/browser-green.txt), and
[provenance](v3/provenance.json) are committed. The two tabs use one shared local
API fixture. No providers, paid runs, or model-facing text are involved.

Four older activity-suite failures remain excluded exactly as before. Their
baseline proof is linked in the [previous evidence](saved-message-identity-v2.md).
No acceptance assertion or pixel-difference threshold was weakened.

## Timeout and deterministic proof

[Reload/activity unit tests](v3/reload-unit-green.txt): **43 passed**.
A controlled clock advances an unanswered turn through its full 180 seconds.
Repeated successful reads retain the original deadline; at expiry there is no
scheduled check, and focus/repeated activity cannot restart that expired window.
Other cases cover an already expired message, account/navigation cancellation,
local sender ownership, a canonical streamed reply, an older visible assistant
that must not stop the window, and a hung read aborted at the deadline.
The new timer cases [failed before implementation](v3/reload-unit-red.txt).

After reconciliation: **2,009 frontend tests pass**, lint has zero errors and
eight existing unrelated warnings, and the production build passes. The free
mocked eval harness passes **270 cases**. The [modularity check](v3/modularity.txt)
passes on the reconciled tree.

```sh
bun test --cwd web __tests__/conversation-activity-transcript-reload.test.ts __tests__/use-conversation-activity.test.tsx
PLAYWRIGHT_PORT=3198 bun run --cwd web test:e2e conversation-activity-ui.spec.ts conversation-transcript-freshness.spec.ts --grep-invert 'durable backtest stays|coarse pointer|resolved clarification'
```

## Integration and final-head discipline

- Original lane base: `edeaffa9f6565e4750fa0685a050f10aefd6d718`.
- Previous integration: `350e3dca8f573f5dfd61f1f753d8ed16a2724c9e`.
- Current integration: `73dc8b7f31bc1c829c3e40f8e85825b7b5631854`.
- Current one-way reconciliation: `d54894d194b769f62d081bc391a4e866497f74b6`.
- The integration delta changes drawer/overlay portals, related CSS/tests, and
  roadmap evidence. It shares UI containers with activity surfaces but changes
  no transcript/activity state owner, API/data contract, migration, or environment.
  Full frontend checks and all 19 accepted browser cases were rerun after the merge.
- Images were captured at the reconciled commit above. The final PR audit will
  explicitly revalidate them at the published head and record the single review
  result, CI, and unresolved-thread count. This is not a terminal audit.
