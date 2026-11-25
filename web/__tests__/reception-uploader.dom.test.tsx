import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReceiptSummary } from "@/lib/business-api";
import type { BusinessEmailDelivery } from "@/lib/business-email";
import type { SentBy } from "@/lib/sent-by";
import type { PersonName } from "@/lib/person-name";

let cleanup = async () => {};
beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 1000 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => { await cleanup(); cleanup = async () => {}; document.body.innerHTML = ""; });
afterAll(async () => { await GlobalRegistrator.unregister(); });

const LANGUAGES = ["es-419", "en"] as const;
const SENDER = "proveedor@ejemplo.test";

/** The Enviado por cell of one Bandeja row, drawn in `lng` with every column shown. */
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
  return { text: cell.textContent, known: cell.getAttribute("data-known"), label: cell.getAttribute("aria-label") ?? cell.getAttribute("title") };
}

const person = (shown_as: PersonName["shown_as"], value?: string): PersonName =>
  ({ display_name: shown_as === "name" ? value! : null, email: shown_as === "email" ? value : null, shown_as });
const member = (who: PersonName): SentBy => ({ id: "member:someone", kind: "member", person: who });

const WORDS = {
  "es-419": { member: "Miembro", former: "Exmiembro", unknown: "Desconocido", allowlist: ["Remitentes", "Remitente no disponible"] },
  en: { member: "Member", former: "Former member", unknown: "Unknown", allowlist: ["Senders", "Sender unavailable"] },
};

for (const lng of LANGUAGES) {
  test(`${lng}: a web upload's Enviado por names who uploaded it as the server says`, async () => {
    for (const [uploader, shown] of [
      [person("name", "Marisol Peña"), "Marisol Peña"],
      [person("email", "socia@ejemplo.test"), "socia@ejemplo.test"],
      [person("member"), WORDS[lng].member],
      [person("former"), WORDS[lng].former],
    ] as const) {
      assert.deepEqual(await senderCell(lng, { channel: "web", sent_by: member(uploader) }), { text: shown, known: "true", label: null }, uploader.shown_as);
      await cleanup();
    }
  });

  test(`${lng}: an email row shows its address and a WhatsApp row names the sender or shows only the last four`, async () => {
    assert.equal((await senderCell(lng, { channel: "email", sent_by: { id: `email:${SENDER}`, kind: "email", address: SENDER } })).text, SENDER);
    await cleanup();
    assert.equal((await senderCell(lng, { channel: "whatsapp", sent_by: { id: "whatsapp:link", kind: "whatsapp", phone_last4: "1234" } })).text, "···1234");
    await cleanup();
    assert.equal((await senderCell(lng, { channel: "whatsapp", sent_by: member(person("name", "Marisol Peña")) })).text, "Marisol Peña");
  });

  test(`${lng}: with no sender from the server the cell is empty in its own words, and the web matches no email itself`, async () => {
    const delivery = { id: "delivery", sender: SENDER } as BusinessEmailDelivery;
    for (const receipt of [{ channel: "whatsapp" }, { channel: "web" }, { channel: "email", email_delivery_ids: ["delivery"] }] as const) {
      const cell = await senderCell(lng, { ...receipt, sent_by: null }, [delivery]);
      assert.deepEqual([cell.known, cell.text, cell.label], ["false", WORDS[lng].unknown, null], `${receipt.channel}: the value is the word, with no native tooltip`);
      await cleanup();
    }
  });

  test(`${lng}: the email allowlist keeps its own word for who may send email`, async () => {
    const { business } = (await import(`@/public/locales/${lng}/common.json`)).default;
    assert.deepEqual([business.reception.senders.list_title, business.email.no_sender], WORDS[lng].allowlist);
  });
}
