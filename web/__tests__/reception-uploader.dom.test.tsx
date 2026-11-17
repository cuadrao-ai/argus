import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReceiptSummary } from "@/lib/business-api";
import type { BusinessEmailDelivery } from "@/lib/business-email";
import type { PersonName } from "@/lib/person-name";

let cleanup = async () => {};
beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 1000 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => { await cleanup(); cleanup = async () => {}; document.body.innerHTML = ""; });
afterAll(async () => { await GlobalRegistrator.unregister(); });

const LANGUAGES = ["es-419", "en"] as const;
const SENDER = "proveedor@ejemplo.test";

/** The Remitente cell of one Bandeja row, drawn in `lng` with every column shown. */
async function senderCell(lng: typeof LANGUAGES[number], receipt: Partial<ReceiptSummary>, emails: BusinessEmailDelivery[] = []) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const Row = (await import("@/components/business-app/recepcion/ReceptionArrivalRow")).default;
  const { receptionRows } = await import("@/components/business-app/recepcion/reception-model");
  const source = (await import("@/components/business-app/fixture-data")).createFixtureBusinessDataSource({ chatAvailable: false });
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng, resources: { [lng]: { translation: (await import(`@/public/locales/${lng}/common.json`)).default } }, interpolation: { escapeValue: false } });
  const seed = (await source.receipts("all"))[0];
  const [row] = receptionRows([{ ...seed, id: "uploaded", email_delivery_ids: [], ...receipt }], [], emails);
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => {
    root.render(<I18nextProvider i18n={i18n}><ul><Row row={row} rowKey="uploaded" arrived={false} view="all" selectable={false} checkable={false} checked={false} unseen={false} onCheck={() => {}} panel={{ kind: "inbox" }} openPanel={() => {}} preferences={{ order: ["file", "source", "sender", "amount", "currency", "status", "arrival"], hidden: [], density: "amplio" }} /></ul></I18nextProvider>);
  });
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  const cell = host.querySelector<HTMLElement>('[data-testid="reception-sender"]')!;
  return { text: cell.textContent, known: cell.getAttribute("data-known") };
}

const person = (shown_as: PersonName["shown_as"], value?: string): PersonName =>
  ({ display_name: shown_as === "name" ? value! : null, email: shown_as === "email" ? value : null, shown_as });

const WORDS = {
  "es-419": { member: "Miembro", former: "Exmiembro" },
  en: { member: "Member", former: "Former member" },
};

for (const lng of LANGUAGES) {
  test(`${lng}: a web upload's Remitente names who uploaded it as the server says`, async () => {
    for (const [uploader, shown] of [
      [person("name", "Marisol Peña"), "Marisol Peña"],
      [person("email", "socia@ejemplo.test"), "socia@ejemplo.test"],
      [person("member"), WORDS[lng].member],
      [person("former"), WORDS[lng].former],
    ] as const) {
      assert.deepEqual(await senderCell(lng, { channel: "web", uploaded_by: uploader }), { text: shown, known: "true" }, uploader.shown_as);
      await cleanup();
    }
  });

  test(`${lng}: WhatsApp and email rows keep their own Remitente`, async () => {
    assert.equal((await senderCell(lng, { channel: "whatsapp", uploaded_by: null })).known, "false");
    await cleanup();
    const delivery = { id: "delivery", sender: SENDER } as BusinessEmailDelivery;
    assert.deepEqual(await senderCell(lng, { channel: "email", uploaded_by: null, email_delivery_ids: ["delivery"] }, [delivery]), { text: SENDER, known: "true" });
  });
}
