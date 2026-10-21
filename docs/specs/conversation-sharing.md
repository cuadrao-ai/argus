# Conversation sharing

Active founder decision, 2026-09-14. This adapts the existing evidence receipt
feature after the #604 promotion walk. It supersedes section 7.5 of
[the original receipt spec](https://github.com/lagarcess/argus/blob/651870a54be4e5506dbb38f3902fef1a97eef8df/docs/superpowers/specs/2026-08-07-sharing-evidence-receipts.md#75-what-is-shareable--superseded-2026-09-14)
and the earlier eligibility restrictions in this document.

## 0. The answer

**Shareable by default; refuse only what is private.** The owner chooses a user
question and the final answer that ended that turn, in the conversation thread
itself. Backtest results, research answers, calculations and plain answers are
sharing units. Confirmation cards and clarifications are not.

Reuse the evidence receipt records, `public_excerpt_snapshots`, `/r/<id>`, the
header chain-link entry, Settings Shared links, revoke, tombstone, delete
cascade, noindex and rate limits. This is one feature and one lifecycle.

## 1. Why

In the 2026-09-13 promotion walk a normal backtest conversation had no selectable
answers. A finished result was marked incomplete. A long public publisher URL
triggered credential-shape scanning. A follow-up lacked sources, research exceeded
4,000 characters, and confirmation cards appeared as rows. The founder promoted
with sharing off, then approved this correction on 2026-09-14.

The owner already sees the conversation. Their explicit selection and the exact
public preview decide what they publish. The system's job is to freeze that
choice without adding account data or other turns.

## 2. The sharing unit

A unit is one user question plus its final answer, with the answer's supported
public card facts and sources where present. The backend determines completion
and question identity from canonical messages and jobs. A finished backtest must
pass the same completion truth used by the rest of Argus; a sharing-specific
misjudgment must be fixed at its cause, not bypassed.

Confirmations, clarification requests and intermediate placeholders are not
selectable. They remain ordinary conversation content outside sharing mode.
The client renders server-declared candidates and does not infer completion or
privacy from wording. Selecting multiple units preserves conversation order.

## 3. Privacy boundary

The owner chooses the units and sees the exact public rendering before making
a link. Preview is read-only. Creation rechecks the selection and compares the
payload digest; changed public content requires a fresh preview. An existing
live selection previews its already-frozen content before reusing that link.

Remove the earlier refusals for:

- credential-shaped text;
- absent publisher sources or links absent from the source list;
- question or answer length;
- degraded answers and answers that used memory.

Keep exact matching against Argus's own private user, conversation, message,
job and artifact identifiers. Closed public payloads contain selected text and
explicit public presentation fields, never automatic account enrichment, raw
message metadata, runtime state, source ids, provider/model metadata or other
turns. Memory use does not add stored memory records to the page.

The owner note remains optional and bounded at 280 characters. It is part of
the preview and frozen content. Rejected private identifiers are not silently
redacted. Rendering treats Markdown and links as untrusted content.

## 4. The read-only public conversation

### 4.1 Eligible answers

A registered owner may share completed answers from their live conversation.
Completion and ownership checks remain server-owned. Missing sources do not
make an answer ineligible. A supported research sidecar contributes its source
list and dates when present; absent sources are represented honestly.

### 4.2 Frozen fields

Version 1 backtest payloads remain readable. New receipts use the existing
closed version 2 wrapper: `{schema_version: 2, kind: "turns", turns: [...]}`.
The leaf kinds are `backtest`, `research_answer`, `calculation` and `answer`.
A document with different leaf kinds has owner-list kind `mixed`.

Every new leaf freezes its question and final answer text. Backtests also freeze
the existing public fact bank, chart, title, assumptions and figures.
Calculations keep their existing typed public presentation fields. Plain answers
use a closed answer leaf. Research sources retain title, domain, URL and source
date, with retrieval time where available. No field is populated by a new
provider call at sharing time.

The concrete schema is owned by `src/argus/api/public_excerpt_schemas.py`, with
API shapes in [API_CONTRACT.md](../API_CONTRACT.md#public-evidence-receipts) and
storage rules in [DATA_MODEL.md](../DATA_MODEL.md#1213-public_excerpt_snapshots).
Optional text additions preserve old version 2 documents. The renderer uses the
same payload for owner preview and the signed-out page.

### 4.3 Dates and language

Authored content stays in the conversation's language. Reader-facing labels and
formatting use the reader's supported language. Sources and their dates remain
visible when the answer has them. Do not invent a source or retrieval date for
a plain answer.

### 4.4 No hidden enrichment

A share never queries a provider, rebuilds an answer, injects account data, adds
other conversation turns or supplies executable continuation state. Receiver copies carry only ordinary
trimmed public history, under the follow-up contract below. Public
reads use only the snapshot. Calculations are not recomputed for the reader.

### 4.5 Founder selection decision

Founder-locked 2026-09-14: the header chain-link enters selection mode in the
conversation thread itself. A checkbox accompanies each server-declared final
answer and selects its paired question too. There is no separate list of titles
from which to guess which answer is being shared.

Keep Select all, clear/cancel, an owner note and the exact preview. The note,
preview and link step use the existing `AdaptivePanel`. Make the link is the
explicit write step. Editing the selection or note invalidates the preview.
No new per-message entry, share service or Settings list is introduced.

## 5. Freeze, revoke and deletion

The snapshot is immutable at creation. Later questions, edits and reruns do not
change it. Revoke is immediate and irreversible; re-sharing after revoke creates
a fresh link. Deleting the chat removes access through the existing revocation
and delete cascade. Restoring a chat does not restore a revoked link. Unknown
and revoked links share the existing tombstone behavior.

The public page is signed out, uncached for revocation, and always noindex and
nofollow. Its follow-up composer starts a receiver-owned copy without private source
conversation ids or execution state. Copies already made survive revocation.

## 6. Owner experience and responsive behavior

Follow [BREAKPOINTS.md](../BREAKPOINTS.md), built on DESIGN.md section 8.
Selection stays in the thread. The note, preview and link step, and Settings
Shared links, use `AdaptivePanel`: a bottom sheet below 1024px and a dialog from
1024px. Modals remain dialogs at every band. Sheet tap targets are at least
44px. Use `AdaptivePanel` and `useResponsiveLayout`, with no locally hard-coded
breakpoint widths or duplicate panel shell.

The registered-owner boundary remains. Guests cannot create receipts. Sharing
flags stay false in `render.yaml` and the release profile; the founder enables
them at promotion. Local verification enables them explicitly.

## 7. API and persistence

The existing candidate, preview and create routes remain. Candidate reads
exclude non-unit confirmations and clarifications. Preview/create select private
message ids, but those ids do not enter the public payload. Final creation
retains the exact digest check and the existing concurrency, ownership and
source-liveness protections. Revoke, owner listing, public read, funnel and rate
limits retain their existing behavior.

Prefer no migration. If a new receipt kind requires widening the database check,
ship that migration in the lane and name it in the promotion report. Do not
apply a hosted migration as part of delivery.

## 8. Reader actions

Founder-locked 2026-09-14 reverses the earlier no-fork clause. Anyone with the link
can read without an access list or sign-in wall. A real follow-up box imports
trimmed frozen public history into the receiver's own account or guest chat on
first submit. Viewing creates nothing. The existing guest choice protects an
already-started chat; guest caps, expiry and signup handoff are unchanged.

The page and exact owner preview share Argus's read-only chat visuals: user
question bubbles, Argus replies, frozen cards, sources and dates. Put the owner
note at the top, and label the snapshot date and receiver-owned follow-ups.
Carried turns keep their own dated provenance in the new chat. They cost nothing,
never affect naming, interest greetings or memory, and carry no owner note or live
run/calculation handles. New changes use normal receiver allowances and flows.

History text is bounded at 64 KiB UTF-8; carried text and card metadata at 512 KiB.
Trim long text fairly over selected turns without a model. Refuse oversized facts
before writes. Revoke, deletion and tombstones prevent new forks; existing copies
survive. Count-only followed_up and signed_up extend the existing funnel without
viewer identifiers. The detailed route/storage and execution contract lives in
API_CONTRACT.md, DATA_MODEL.md and the current lane spec.

## 9. Acceptance

Scripted tests must fail on the current integration base, then pass for the
finished backtest, Quick take and Breakdown containing the recorded long
publisher link, the follow-up without sources and research over 4,000 characters.
Confirmations and clarifications must not be selectable. Retain tests for exact
private ids, preview mismatch, frozen content, registered ownership, flag-off
behavior, revoke, tombstone, source deletion and public read isolation.

Use seeded or recorded conversations with no provider spend. Browser evidence
matches `web/e2e/breakpoint-baselines.spec.ts`: English dark at 390, 720 and
1024px, Spanish light at 390px, plus 1280px. Show selection and sharing within
the conversation. Show the signed-out page at 390 and 1024px. Keep durable
screenshots and observed behavior on the PR's exact product head.

A second Codex finding on the same preview/privacy mechanism stops this lane
for a report, rather than another fix. Any needed live answer requires a
proposed spend cap and explicit founder approval. Delivery ends at a PR against
`codex/private-alpha-next` with green CI and a clean Codex review at the head.
The founder merges and promotes.

## 10. Delivery record

The current lane contract is
[2026-09-14-conversation-sharing-604.md](https://github.com/lagarcess/argus/blob/651870a54be4e5506dbb38f3902fef1a97eef8df/docs/superpowers/specs/2026-09-14-conversation-sharing-604.md).
Issue [#604](https://github.com/lagarcess/argus/issues/604) holds the reproduced
promotion failure. The original receipt spec remains history for earlier design
decisions; this document owns the current sharing boundary.
