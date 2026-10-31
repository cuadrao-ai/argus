import assert from "node:assert/strict";
import { test } from "bun:test";
import { readBusinessDossier } from "@/lib/business-dossier";

const SENTENCE = "No pudimos verificar este remitente.";

test("a dossier response keeps a review note, and treats null, a missing field, and a non-string as none", () => {
  assert.equal(readBusinessDossier({ draft_id: "d-1", review_note: `  ${SENTENCE}  ` }).review_note, SENTENCE);
  assert.equal(readBusinessDossier({ draft_id: "d-1", review_note: SENTENCE }).draft_id, "d-1");
  assert.equal(readBusinessDossier({ review_note: null }).review_note, null);
  assert.equal(readBusinessDossier({ draft_id: "d-absent" }).review_note, null);
  assert.equal(readBusinessDossier({ review_note: 12 }).review_note, null);
  assert.equal(readBusinessDossier({ review_note: { text: SENTENCE } }).review_note, null);
  assert.equal(readBusinessDossier({ review_note: "   " }).review_note, null);
});
