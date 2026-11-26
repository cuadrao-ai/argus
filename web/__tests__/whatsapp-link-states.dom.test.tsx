import { afterAll, afterEach, beforeAll, expect, setSystemTime, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import i18next from "i18next";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import WhatsAppLinkModal from "../components/settings/WhatsAppLinkModal";
import { SettingsWindowSection } from "../components/settings/SettingsSurface";
import spanish from "../public/locales/es-419/common.json";

import english from "../public/locales/en/common.json";

const eligible = [{ space_id: "synthetic-business", name: "Taller de prueba" }];
const notice = "Al vincular tu número, aceptas que la foto o el PDF que envíes se lea con IA para saber a qué negocio va.";
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

async function open(blocked = false, seconds = 581, withUrl = true) {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  const issued: unknown[] = [];
  const requests = { linked: false, reads: 0, deletes: 0, limited: false };
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
      requests.linked = false;
      return new Response(null, { status: 204 });
    }
    requests.reads++;
    return Response.json({ linked: requests.linked, last4: requests.linked ? "4821" : null, linked_at: null, reply_language: null, receiving_businesses: blocked ? [] : eligible, held_count: 0 });
  }) as typeof fetch;
  const host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  await act(async () => root?.render(<I18nextProvider i18n={i18n}><SettingsWindowSection><WhatsAppLinkModal onClose={() => {}} /></SettingsWindowSection></I18nextProvider>));
  async function click(label: string) {
    const button = [...host.querySelectorAll("button")].find((node) => node.textContent === label);
    expect(button).toBeDefined();
    await act(async () => button!.click());
  }
  return { host, click, issued, requests };
}

test("ready shows what linking does and the notice accepted by its one button", async () => {
  const { host, click, issued } = await open();
  for (const line of [
    "Envía tus documentos por WhatsApp",
    "Vincula tu número y envía fotos o PDF de facturas y recibos al número de Cuadrao. Cada archivo va al negocio cuyo RNC o cédula sale en el documento.",
    "Si no sabemos a qué negocio va, te espera aquí para que lo elijas tú.",
    notice,
  ]) expect(host.textContent).toContain(line);
  await click("Vincular mi WhatsApp");
  expect(issued).toEqual([{ language: "es-419", disclosure: notice }]);
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
  const { host } = await open(true);
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

test("expired retires the old message and offers a fresh code", async () => {
  const { host, click, issued } = await open(false, 0);
  await click("Vincular mi WhatsApp");
  for (const line of ["El código venció", "Cada código sirve 10 minutos. Pide otro y envíalo desde tu WhatsApp.", "Este mensaje ya no sirve.", message, "Cancelar"]) {
    expect(host.textContent).toContain(line);
  }
  expect(host.querySelector('[aria-label="Copiar código"]')).toBeNull();
  expect(host.querySelector('a[href^="https://wa.me"]')).toBeNull();
  await click("Obtener otro código");
  expect(issued).toHaveLength(2);
});

test("the live status poll sees redemption and stops; unlink requires confirmation", async () => {
  const { host, click, requests } = await open();
  await click("Vincular mi WhatsApp");
  requests.linked = true;
  setSystemTime(Date.now() + 3500);
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 1050)); });
  expect(requests.reads).toBe(2);
  expect(host.textContent).toContain("Número que termina en 4821");
  expect(host.querySelector("a")?.getAttribute("href")).toBe("/biz?view=inbox");
  expect(host.textContent).not.toContain("Esperando tu mensaje…");
  await click("Desvincular número");
  expect(requests.deletes).toBe(0);
  expect(host.textContent).toContain(spanish.settings.whatsapp.confirm_unlink);
  await click("Confirmar");
  expect(requests.deletes).toBe(1);
  expect(host.textContent).toContain(notice);
});

test("a missing receiving number still allows copying the message", async () => {
  const { host, click } = await open(false, 581, false);
  await click("Vincular mi WhatsApp");
  expect(host.textContent).toContain(spanish.settings.whatsapp.send_steps);
  expect(host.textContent).toContain(message);
  expect(host.querySelector("img")).toBeNull();
  expect(host.querySelector("a")).toBeNull();
  expect(host.querySelector('[aria-label="Copiar código"]')).toBeTruthy();
});

test("a rate limit replaces the expired message and permits retry", async () => {
  const { host, click, requests } = await open(false, 0);
  await click("Vincular mi WhatsApp");
  requests.limited = true;
  await click("Obtener otro código");
  expect(host.querySelector('[role="alert"]')?.textContent).toBe(spanish.settings.whatsapp.problem_rate_limited);
  expect(host.textContent).not.toContain("El código venció");
  requests.limited = false;
  await click("Obtener otro código");
  expect(host.textContent).toContain("El código venció");
});


test("an English account submits the displayed English notice", async () => {
  await i18n.changeLanguage("en");
  const { host, click, issued } = await open();
  const notice = "By linking your number, you agree that the photo or PDF you send is read by AI to find which business it belongs to.";
  expect(host.textContent).toContain(notice);
  await click("Link my WhatsApp");
  expect(issued).toEqual([{ language: "en", disclosure: notice }]);
  expect(host.textContent).toContain("Waiting for your message…");
});
