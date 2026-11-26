import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDossier, BusinessFact } from "@/lib/business-dossier";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

/** Every read sample receipt with its dossier. */
async function readSamples() {
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const receipts = (await Promise.all((await source.receipts("all")).map((listed) => source.receipt(listed.id)))).filter((receipt) => receipt.draft_id);
  assert.ok(receipts.length > 3, "the sample has read receipts");
  return Promise.all(receipts.map(async (receipt) => ({ receipt, dossier: await source.dossier!(receipt.draft_id!) as BusinessDossier })));
}

const ANSWERS = ["funding", "business_share", "receipt_state", "category_id"] as const;

test("a sample receipt's first revision is the read, as the server writes it for every channel", async () => {
  for (const { receipt, dossier } of await readSamples()) {
    const [first, ...later] = dossier.history;
    assert.equal(first.before, null, receipt.id);
    assert.equal(first.actor.actor_kind, "extractor", `${receipt.id}: the read is the extractor's, for the person whose grant it used`);
    assert.ok(!first.reason, receipt.id);
    assert.deepEqual([first.before_document_type, first.after_document_type], [null, "recibo"], receipt.id);
    const arrival = dossier.sources.find((source) => source.id === first.source_ids[0]);
    assert.deepEqual([first.source_ids.length, arrival?.kind, arrival?.kind === "attachment" ? arrival.channel : null], [1, "attachment", receipt.channel], `${receipt.id}: the read names the file it read`);
    assert.ok(Date.parse(first.created_at) > Date.parse(receipt.received_at), `${receipt.id}: the read ends after the file arrives`);
    const { fiscal, ...facts } = first.after;
    const read = [...Object.values(facts), ...Object.values(fiscal ?? {})] as BusinessFact<unknown>[];
    assert.deepEqual([...new Set(read.filter((fact) => fact.state === "known").map((fact) => fact.origin))], ["extracted"], `${receipt.id}: a read value is the read's, never a person's`);
    for (const answer of ANSWERS) assert.equal(first.after[answer].state, "unknown", `${receipt.id}: no read answers ${answer}`);
    // What a person did after the read is its own revision, by that person, over the read's values.
    for (const [index, revision] of later.entries()) {
      assert.equal(revision.actor.actor_kind, "member", receipt.id);
      assert.deepEqual(revision.before, dossier.history[index].after, receipt.id);
    }
  }
});

test("the sample's Historial is Llegó por, Leído, then what a person changed", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const samples = await readSamples();
  const shown: Record<string, (string | null | undefined)[][]> = {};
  for (const { receipt, dossier } of samples) {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => { root.render(<I18nextProvider i18n={i18n}><ReceiptHistory history={dossier.history} origin={dossier.origin} accounts={dossier.accounts} sources={dossier.sources} documentType="recibo" /></I18nextProvider>); });
    const lines = [...host.querySelectorAll("li")].map((item) => [...[...item.querySelectorAll("p")].map((line) => line.querySelector('[aria-hidden="true"]')?.textContent ?? line.textContent), item.querySelector('[data-testid="history-who"] span')?.textContent ?? null]);
    shown[receipt.id] = lines;
    assert.deepEqual(lines.at(-2), ["Leído", "Cuadrao"], `${receipt.id}: Cuadrao read it`);
    assert.match(lines.at(-1)?.[0] ?? "", /^Llegó por /, receipt.id);
    assert.doesNotMatch(host.textContent ?? "", /Actividad|Parte del negocio|Categoría|Total|Moneda|Emisor|Fecha:/, `${receipt.id}: the read's values are not corrections`);
    await act(async () => { root.unmount(); host.remove(); });
  }
  // The owner marked this one "sin comprobante" after the read: one change, by the person.
  const marked = samples.find(({ receipt }) => receipt.id === "rcpt-ferreteria")!;
  assert.deepEqual(shown["rcpt-ferreteria"], [["Comprobante", "Ana Peña"], ["Leído", "Cuadrao"], ["Llegó por WhatsApp", marked.receipt.filename, null]]);
});
