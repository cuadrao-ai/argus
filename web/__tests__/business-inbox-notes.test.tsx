import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import i18next from "i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";

import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import { NotesAwaitingReview, openNotesByDraft } from "../components/business-app/BusinessInboxPanel";
import type { BusinessCapture } from "../lib/business-api";

// The draft's version runs ahead of the note's revision (later actions bump it); rows show the revision.
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

  test("rows show the note text, revision and earlier count in Spanish, and open the draft", async () => {
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish }, en: { translation: english } } });
    const html = renderToStaticMarkup(
      <I18nextProvider i18n={i18n}>
        <NotesAwaitingReview notes={openNotesByDraft(CAPTURES)} error={false} onOpen={() => undefined} />
      </I18nextProvider>,
    );
    assert.ok(html.includes("Notas en revisión"));
    assert.ok(html.includes("Pagué con mi dinero."));
    assert.ok(html.includes("Revisión 2"));
    assert.ok(!html.includes("Revisión 5"));
    assert.ok(html.includes("1 nota anterior"));
    assert.ok(html.includes("Aprobando el pago de luz"));
    assert.ok(!html.includes("Recorded already") && !html.includes("Dismissed"));
    assert.equal((html.match(/<button/g) ?? []).length, 3);
    assert.ok(!html.includes("últimas 50"));
  });

  test("a full page says it shows the latest notes", async () => {
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
    const html = renderToStaticMarkup(
      <I18nextProvider i18n={i18n}>
        <NotesAwaitingReview notes={openNotesByDraft(CAPTURES)} error={false} truncated onOpen={() => undefined} />
      </I18nextProvider>,
    );
    assert.ok(html.includes("Se muestran las últimas 50 notas guardadas"));
  });

  test("a notes outage says so and renders no invented rows; no notes renders nothing", async () => {
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "en", resources: { en: { translation: english } } });
    const render = (notes: ReturnType<typeof openNotesByDraft>, error: boolean) =>
      renderToStaticMarkup(<I18nextProvider i18n={i18n}><NotesAwaitingReview notes={notes} error={error} onOpen={() => undefined} /></I18nextProvider>);
    const failed = render([], true);
    assert.ok(failed.includes('role="alert"') && failed.includes("We couldn&#x27;t load your notes. Try again."));
    assert.ok(!failed.includes("<button"));
    assert.equal(render([], false), "");
  });
});
