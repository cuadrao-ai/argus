import { afterAll, afterEach, beforeAll, expect, jest, setSystemTime, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import i18next from "i18next";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import WhatsAppLinkModal from "../components/settings/WhatsAppLinkModal";
import { SettingsWindowSection } from "../components/settings/SettingsSurface";
import { whatsappDisclosure } from "./fixtures/whatsapp-disclosure";
import spanish from "../public/locales/es-419/common.json";

import english from "../public/locales/en/common.json";

const eligible = [
  { space_id: "synthetic-business", name: "Taller de prueba", tax_id: { type: "rnc", value: "131456782" } },
  { space_id: "synthetic-cedula", name: "Colmado de prueba", tax_id: { type: "cedula", value: "00112345678" } },
];
const notice = whatsappDisclosure["es-419"].disclosure;
const message = "CUADRAO K7P2M9XQ";
const url = "https://wa.me/18095550100?text=CUADRAO%20K7P2M9XQ";
const originalFetch = globalThis.fetch;
const originalAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
const i18n = i18next.createInstance();
let root: Root | null;

beforeAll(async () => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  await i18n.init({ lng: "es-419", defaultNS: "common", resources: { "es-419": { common: spanish }, en: { common: english } } });
});
afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  root = null;
  setSystemTime();
  await i18n.changeLanguage("es-419");
  globalThis.fetch = originalFetch;
  if (originalAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalAuth;
  document.body.replaceChildren();
});
afterAll(() => GlobalRegistrator.unregister());

async function open({ blocked = false, seconds = 581, withUrl = true, linked = false, heldCount = 0, linkedAt = "" } = {}) {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  const issued: unknown[] = [];
  const requests = { linked, reads: 0, deletes: 0, limited: false, closes: 0,
    nextDelete: null as Promise<Response> | null, languages: [] as (string | null)[], nextRead: null as Promise<Response> | null,
  };
  globalThis.fetch = (async (input, init) => {
    const path = new URL(String(input)).pathname;
    if (path.endsWith("/whatsapp/link-codes") && init?.method === "POST") {
      issued.push(JSON.parse(String(init.body)));
      if (requests.limited) return Response.json({ code: "whatsapp_link_code_rate_limited" }, { status: 429 });
      return Response.json({ code: "K7P2M9XQ", message_text: message, wa_me_url: withUrl ? url : null, qr_data_url: withUrl ? "data:image/png;base64,AA==" : null, expires_at: new Date(Date.now() + seconds * 1000).toISOString() });
    }
    if (!path.endsWith("/whatsapp/link")) throw new Error(path);
    if (init?.method === "DELETE") {
      requests.deletes++;
      if (requests.nextDelete) return requests.nextDelete;
      requests.linked = false;
      return new Response(null, { status: 204 });
    }
    requests.reads++;
    const language = new URL(String(input)).searchParams.get("language");
    requests.languages.push(language);
    if (requests.nextRead) return requests.nextRead;
    return Response.json({ ...whatsappDisclosure[language === "en" ? "en" : "es-419"], linked: requests.linked, last4: requests.linked ? "4821" : null, linked_at: linkedAt || null, reply_language: null, receiving_businesses: blocked ? [] : eligible, held_count: heldCount });
  }) as typeof fetch;
  const host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  await act(async () => root?.render(<I18nextProvider i18n={i18n}><SettingsWindowSection><WhatsAppLinkModal onClose={() => { requests.closes++; }} /></SettingsWindowSection></I18nextProvider>));
  async function click(label: string) {
    const button = [...document.querySelectorAll("button")].find((node) => node.textContent === label);
    expect(button).toBeDefined();
    await act(async () => button!.click());
  }
  return { host, click, issued, requests };
}

test("ready shows what linking does and the notice accepted by its one button", async () => {
  const { host, click, issued, requests } = await open();
  expect(requests.languages).toEqual(["es-419"]);
  for (const line of [
    "Envía tus documentos por WhatsApp",
    "Vincula tu número y envía fotos o PDF de facturas y recibos al número de Cuadrao. Cada archivo va al negocio cuyo RNC o cédula sale en el documento.",
    "Si no sabemos a qué negocio va, te espera aquí para que lo elijas tú.",
    notice,
  ]) expect(host.textContent).toContain(line);
  await click("Vincular mi WhatsApp");
  expect(issued).toEqual([{ language: "es-419", disclosure_token: whatsappDisclosure["es-419"].disclosure_token }]);
});

test("waiting shows the camera steps, mobile send action, expiring message and copy alternative", async () => {
  const { host, click } = await open();
  await click("Vincular mi WhatsApp");
  for (const line of [
    "Escanea el código con tu teléfono", "Abre la cámara de tu teléfono y escanea el código.",
    "WhatsApp se abre con el mensaje listo. Toca Enviar.", "Esta pantalla cambia sola cuando llegue.",
    "¿Tienes WhatsApp en esta computadora?", "Envía el código por WhatsApp",
    "Toca Abrir WhatsApp. El mensaje ya viene escrito. Solo toca Enviar y vuelve aquí.",
    "Esperando tu mensaje…", "Vence en 9:41", spanish.settings.whatsapp.send_steps, message,
  ]) expect(host.textContent).toContain(line);
  expect(host.querySelector("img")?.getAttribute("src")).toBe("data:image/png;base64,AA==");
  expect(host.querySelector("img")?.alt).toBe(spanish.settings.whatsapp.scan_title);
  expect(host.querySelector("a")?.href).toBe(url);
  expect(host.querySelector('[aria-label="Copiar código"]')).toBeTruthy();
  await click("Cancelar");
  expect(host.textContent).toContain("Vincular mi WhatsApp");
});

test("blocked shows both setup requirements and a route to the chosen Business settings", async () => {
  const { host } = await open({ blocked: true });
  for (const line of [
    "Completa el RNC y activa la lectura automática en un negocio",
    "WhatsApp ubica cada archivo por el RNC o la cédula del negocio y lo lee al llegar. Hace falta en al menos un negocio donde puedas subir documentos.",
    "Agrega el RNC o la cédula", "Activar lectura de documentos", "Configurar negocio",
  ]) expect(host.textContent).toContain(line);
  const listLabel = host.querySelector("ol")?.getAttribute("aria-labelledby");
  expect(document.getElementById(listLabel ?? "")?.textContent).toBe(spanish.settings.whatsapp.setup_title);
  expect(host.querySelector("a")?.getAttribute("href")).toBe("/biz?view=business&tab=datos");
  expect(host.textContent).not.toContain(notice);
  expect(host.textContent).not.toContain("Vincular mi WhatsApp");
});

test("expired retires the old message and offers a fresh code once the final read returns unlinked", async () => {
  const { host, click, issued, requests } = await open({ seconds: 0 });
  const pending = Promise.withResolvers<Response>();
  requests.nextRead = pending.promise;
  await click("Vincular mi WhatsApp");
  expect(requests.reads).toBe(2);
  expect(host.textContent).not.toContain("Obtener otro código");
  await act(async () => {
    pending.resolve(Response.json({ ...whatsappDisclosure["es-419"], linked: false, receiving_businesses: eligible, held_count: 0 }));
  });
  requests.nextRead = null;
  for (const line of ["El código venció", "Cada código sirve 10 minutos. Pide otro y envíalo desde tu WhatsApp.", "Este mensaje ya no sirve.", message, "Cancelar"]) {
    expect(host.textContent).toContain(line);
  }
  expect(host.querySelector('[aria-label="Copiar código"]')).toBeNull();
  expect(host.querySelector('a[href^="https://wa.me"]')).toBeNull();
  await click("Obtener otro código");
  expect(issued).toHaveLength(2);
});

test("linked settings show the held count and the fiscal ID for each receiving business", async () => {
  const { host } = await open({ linked: true, heldCount: 7 });
  expect(host.querySelector("ul")?.getAttribute("aria-label")).toBe("Negocios que reciben");
  expect([...host.querySelectorAll("li")].map(row => row.textContent)).toEqual([
    "Taller de pruebaRNC 1-31-45678-2", "Colmado de pruebaCédula 001-1234567-8",
  ]);
  expect(host.textContent).toContain("Cada archivo va al negocio cuyo RNC o cédula sale en el documento.");
  expect(host.textContent).toContain("¿Falta un negocio? Necesita su RNC o cédula y la lectura automática activa.");
  const held = host.querySelector('[aria-label="Archivos sin negocio"]');
  expect(held?.textContent).toBe("Archivos sin negocioEsperan que elijas a qué negocio van7");
});

test("the linked panel shows the approved English for receiving businesses and held files", async () => {
  await i18n.changeLanguage("en");
  const { host } = await open({ linked: true, heldCount: 2 });
  expect(host.querySelector("ul")?.getAttribute("aria-label")).toBe("Businesses that receive");
  expect(host.textContent).toContain("Each file goes to the business whose RNC or cédula appears on the document.");
  expect(host.textContent).toContain("Missing a business? It needs its RNC or cédula and automatic reading turned on.");
  expect(host.querySelector('[aria-label="Files with no business"]')?.textContent)
    .toBe("Files with no businessWaiting for you to choose which business they go to2");
});

test("linked settings preserve the held count after the last eligible business is lost", async () => {
  const { host } = await open({ linked: true, blocked: true, heldCount: 3 });
  expect(host.querySelectorAll("li")).toHaveLength(0);
  expect(host.querySelector('[aria-label="Archivos sin negocio"]')?.textContent).toContain("3");
  expect(host.textContent).toContain("Desvincular número");
});

test("an empty held queue shows zero without saying that files are waiting", async () => {
  const { host } = await open({ linked: true, heldCount: 0 });
  expect(host.querySelector('[aria-label="Archivos sin negocio"]')?.textContent).toBe("Archivos sin negocio0");
});

test("the live status poll sees redemption and stops; unlink requires confirmation", async () => {
  const { host, click, requests } = await open();
  await click("Vincular mi WhatsApp");
  requests.linked = true;
  setSystemTime(Date.now() + 3500);
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 1050)); });
  expect(requests.reads).toBe(2);
  expect(host.textContent).toContain("Número que termina en 4821");
  expect(host.querySelector('a[href="/biz?view=inbox"]')).toBeNull();
  expect(host.textContent).not.toContain(spanish.business.activity.open_settings);
  expect(host.textContent).not.toContain("Esperando tu mensaje…");
  await click("Desvincular número");
  expect(requests.deletes).toBe(0);
  expect(document.querySelector("[role=alertdialog]")?.textContent).toContain("Ya no se aceptarán mensajes nuevos de ese número. Los recibos que ya llegaron siguen en la Bandeja de cada negocio.");
  await click("Desvincular");
  expect(requests.deletes).toBe(1);
  expect(host.textContent).toContain(notice);
});

async function advance(ms: number) {
  await act(async () => { jest.advanceTimersByTime(ms); });
}

test("a redemption in the final second wins over the local expiry", async () => {
  const { host, click, requests } = await open({ seconds: 4 });
  jest.useFakeTimers();
  try {
    await click("Vincular mi WhatsApp");
    await advance(3000);
    expect(requests.reads).toBe(2);
    await advance(500);
    requests.linked = true;
    await advance(500);
    expect(requests.reads).toBe(3);
    expect(host.textContent).toContain("Número que termina en 4821");
    expect(host.textContent).not.toContain("El código venció");
    await advance(6000);
    expect(requests.reads).toBe(3);
  } finally { jest.useRealTimers(); }
});

test.each([
  ["linked", true],
  ["still unlinked", false],
] as const)("a pre-expiry read resolving after zero reports %s", async (_, linked) => {
  const { host, click, requests } = await open({ seconds: 4 });
  jest.useFakeTimers();
  try {
    await click("Vincular mi WhatsApp");
    const pending = Promise.withResolvers<Response>();
    requests.nextRead = pending.promise;
    await advance(3000);
    await advance(1000);
    expect(requests.reads).toBe(2);
    expect(host.textContent).not.toContain("Obtener otro código");
    expect(host.textContent).not.toContain("El código venció");
    requests.nextRead = null;
    requests.linked = true;
    await act(async () => {
      pending.resolve(Response.json({ ...whatsappDisclosure["es-419"], linked, last4: linked ? "4821" : null,
        receiving_businesses: eligible, held_count: 0 }));
    });
    if (!linked) await advance(1000);
    expect(host.textContent).toContain("Número que termina en 4821");
    await advance(6000);
    expect(requests.reads).toBe(linked ? 2 : 3);
  } finally { jest.useRealTimers(); }
});

test("a missing receiving number still allows copying the message", async () => {
  const { host, click } = await open({ withUrl: false });
  await click("Vincular mi WhatsApp");
  expect(host.textContent).toContain(spanish.settings.whatsapp.send_steps);
  expect(host.textContent).toContain(message);
  expect(host.querySelector("img")).toBeNull();
  expect(host.querySelector("a")).toBeNull();
  expect(host.querySelector('[aria-label="Copiar código"]')).toBeTruthy();
});

test("a rate limit replaces the expired message and permits retry", async () => {
  const { host, click, requests } = await open({ seconds: 0 });
  await click("Vincular mi WhatsApp");
  requests.limited = true;
  await click("Obtener otro código");
  expect(host.querySelector('[role="alert"]')?.textContent).toBe(spanish.settings.whatsapp.problem_rate_limited);
  expect(host.textContent).not.toContain("El código venció");
  requests.limited = false;
  await click("Obtener otro código");
  expect(host.textContent).toContain("El código venció");
});


test("changing language fetches the new disclosure before it can be accepted", async () => {
  const { host, click, issued, requests } = await open();
  const pending = Promise.withResolvers<Response>();
  requests.nextRead = pending.promise;
  await act(async () => { await i18n.changeLanguage("en"); });
  expect(requests.languages).toEqual(["es-419", "en"]);
  expect(host.textContent).not.toContain(notice);
  expect([...document.querySelectorAll("button")].some((b) => b.textContent === "Link my WhatsApp" && !b.disabled)).toBe(false);
  await act(async () => {
    pending.resolve(Response.json({ ...whatsappDisclosure.en, linked: false, receiving_businesses: eligible, held_count: 0 }));
  });
  expect(host.textContent).toContain(whatsappDisclosure.en.disclosure);
  await click("Link my WhatsApp");
  expect(issued).toEqual([{ language: "en", disclosure_token: whatsappDisclosure.en.disclosure_token }]);
  expect(host.textContent).toContain("Waiting for your message…");
});

test("successful unlink clears the number before refresh and closes quietly when prepare access is gone", async () => {
  const { host, click, requests } = await open({ linked: true });
  expect(host.textContent).toContain("Número que termina en 4821");
  const pending = Promise.withResolvers<Response>();
  requests.nextRead = pending.promise;
  await click("Desvincular número");
  await click("Desvincular");
  expect(requests.deletes).toBe(1);
  expect(requests.reads).toBe(2);
  expect(host.textContent).not.toContain("4821");
  expect(host.textContent).not.toContain("Desvincular número");
  await act(async () => { pending.resolve(Response.json({ code: "whatsapp_unavailable" }, { status: 404 })); });
  expect(requests.closes).toBe(1);
  expect(host.querySelector('[role="alert"]')).toBeNull();
});

test.each([
  ["2026-11-16", "Vinculado hace 3 días"],
  ["2026-11-12", "Vinculado el 12 nov"],
])("the number uses its link timestamp from %s", async (day, expected) => {
  setSystemTime(new Date("2026-11-19T12:00:00Z"));
  const { host } = await open({ linked: true, linkedAt: day + "T12:00:00Z" });
  expect(host.querySelector("time")?.textContent).toBe(expected);
  expect(host.textContent).not.toContain("Número vinculado");
});

test("tapping info puts the explanation between the linked number and date inside the card", async () => {
  const { host } = await open({ linked: true, linkedAt: "2026-11-12T12:00:00Z" });
  const trigger = host.querySelector<HTMLButtonElement>('button[aria-label="Qué pasa con lo que envías"]');
  expect(trigger).toBeTruthy();
  await act(async () => trigger!.click());
  const bubble = document.getElementById(trigger!.getAttribute("aria-describedby") ?? "");
  expect(bubble?.textContent).toBe("Mientras esté vinculado, la foto o el PDF que envíes se lee con IA para saber a qué negocio va.");
  const card = trigger!.closest("section")!;
  expect(card.contains(bubble)).toBe(true);
  expect([...card.querySelectorAll('h3, [role="tooltip"], time')].map(node => node.tagName))
    .toEqual(["H3", "DIV", "TIME"]);
  await act(async () => trigger!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  expect(document.querySelector('[role="tooltip"]')).toBeNull();
});

test.each([true, false])("held files survive unlink with setup blocked = %s", async blocked => {
  const { host, click, requests } = await open({ linked: true, heldCount: 3, blocked });
  await click("Desvincular número");
  const dialog = document.querySelector('[role="alertdialog"]');
  expect(dialog?.querySelector("h2")?.textContent).toBe("¿Desvincular el número que termina en 4821?");
  expect([...dialog!.querySelectorAll("li")].map(item => item.textContent)).toEqual([
    "Ya no recibiremos archivos de ese número.",
    "Los 3 archivos sin negocio se quedan aquí hasta que los asignes o venzan.",
    "Los que se están leyendo terminan y llegan a su negocio o se quedan aquí.",
    "No le enviaremos ningún mensaje a ese número.",
  ]);
  await click("Cancelar");
  expect(requests.deletes).toBe(0);
  expect(document.querySelector('[role="alertdialog"]')).toBeNull();
  await click("Desvincular número");
  await click("Desvincular");
  expect(requests.deletes).toBe(1);
  expect(host.textContent).not.toContain("4821");
  const held = host.querySelector('[aria-label="Archivos sin negocio"]');
  expect(held?.textContent).toContain("3");
  expect(held?.querySelector("a,button,[tabindex]")).toBeNull();
});

test.each([
  ["es-419", "Desvincular número", "El archivo sin negocio se queda aquí hasta que lo asignes o venza."],
  ["en", english.settings.whatsapp.unlink, "The file with no business stays here until you assign it or it expires."],
])("one held file uses the approved singular in %s", async (language, label, sentence) => {
  await i18n.changeLanguage(language);
  const { click } = await open({ linked: true, heldCount: 1 });
  await click(label);
  expect(document.querySelectorAll('[role="alertdialog"] li')[1]?.textContent).toBe(sentence);
});

test("a failed unlink stays in the dialog and retries once", async () => {
  const { click, requests } = await open({ linked: true, heldCount: 2 });
  await click("Desvincular número");
  const pending = Promise.withResolvers<Response>();
  requests.nextDelete = pending.promise;
  await click("Desvincular");
  await click("Desvincular");
  await act(async () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  expect(requests.deletes).toBe(1);
  expect(document.querySelector('[role="alertdialog"]')).toBeTruthy();
  await act(async () => pending.resolve(new Response(null, { status: 503 })));
  expect(document.querySelector('[role="alertdialog"] [role="alert"]')?.textContent).toBe(spanish.settings.whatsapp.problem_failed);
  requests.nextDelete = null;
  await click("Desvincular");
  expect(requests.deletes).toBe(2);
  expect(document.querySelector('[role="alertdialog"]')).toBeNull();
});
