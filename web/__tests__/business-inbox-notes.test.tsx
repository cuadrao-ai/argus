import assert from "node:assert/strict";
import { describe, test } from "bun:test";

import { inboxCount, openNotesByDraft } from "../components/business-app/BusinessInboxPanel";
import type { BusinessCapture } from "../lib/business-api";

// The draft's version runs ahead of the note's revision (later actions bump it).
const note = (draft_id: string, revision: number, text: string, received_at: string, review_state: BusinessCapture["review_state"] = "open"): BusinessCapture =>
  ({ draft_id, version: revision + 3, revision, source_id: `${draft_id}-${revision}`, text, received_at, review_state });

const CAPTURES: BusinessCapture[] = [
  note("draft-a", 1, "Ayer compré pintura para el taller.", "2026-10-10T14:00:00Z"),
  note("draft-b", 1, "Me pagaron 5,000 por la reparación.", "2026-10-11T09:00:00Z"),
  note("draft-a", 2, "Pagué con mi dinero.", "2026-10-10T15:30:00Z"),
  note("draft-c", 3, "Recorded already", "2026-10-11T10:00:00Z", "accepted"),
  note("draft-d", 1, "Dismissed", "2026-10-11T11:00:00Z", "dismissed"),
  note("draft-e", 2, "Aprobando el pago de luz", "2026-10-11T12:00:00Z", "accepting"),
];

describe("notes awaiting review in the Inbox", () => {
  test("one row per open draft, newest first, with its latest note and the count of earlier ones", () => {
    assert.deepEqual(openNotesByDraft(CAPTURES), [
      { draftId: "draft-e", text: "Aprobando el pago de luz", receivedAt: "2026-10-11T12:00:00Z", revision: 2, earlier: 0 },
      { draftId: "draft-b", text: "Me pagaron 5,000 por la reparación.", receivedAt: "2026-10-11T09:00:00Z", revision: 1, earlier: 0 },
      { draftId: "draft-a", text: "Pagué con mi dinero.", receivedAt: "2026-10-10T15:30:00Z", revision: 2, earlier: 1 },
    ]);
    assert.deepEqual(openNotesByDraft([]), []);
  });
});

describe("the inbox count on the Overview card and the sidebar badge", () => {
  test("is countPorRevisar of the receipt list, and unknown until that list arrives", () => {
    assert.equal(inboxCount({ inbox: [{ status: "review_ready" }, { status: "review_ready" }, { status: "needs_attention", attention: "unreadable" }] }), 2);
    assert.equal(inboxCount({ inbox: [] }), 0);
    assert.equal(inboxCount({ inbox: null }), null);
    assert.equal(inboxCount({}), null);
  });
});
