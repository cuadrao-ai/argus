import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import type { ReceivingChannels } from "@/lib/business-api";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost/biz" }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterAll(async () => { await GlobalRegistrator.unregister(); });

test("Bandeja filters share mixed/all/none behavior and restrict bulk selection to search results", async () => {
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } } });
  const { BusinessContext } = await import("@/components/business-app/business-context");
  const available = { receivingChannels: { email: { available: false }, whatsapp: { available: false } } } as unknown as import("@/components/business-app/BusinessWorkspace").BusinessContextValue;
  const Filters = (await import("@/components/business-app/recepcion/ReceptionFilters")).default;
  const { emptyReceptionFilters } = await import("@/components/business-app/recepcion/reception-filters");
  function Harness() { const [value, setValue] = useState(emptyReceptionFilters); return <><Filters value={value} onChange={setValue} senders={[{ id: "a", name: "Ana", address: "ana@example.test" }, { id: "b", name: "Bea", address: "bea@example.test" }]} /><output>{JSON.stringify(value)}</output></>; }
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  const button = (text: string) => [...document.querySelectorAll<HTMLButtonElement>("button")].find(node => node.textContent === text)!;
  const checkbox = (text: string) => { const label = [...document.querySelectorAll("label")].find(node => node.textContent === text); assert.ok(label); return label.querySelector<HTMLInputElement>("input")!; };
  const click = (node: HTMLElement) => act(async () => { assert.ok(node); node.click(); });
  try {
    await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={available}><Harness /></BusinessContext.Provider></I18nextProvider>); });
    await click(button("Filtros"));
    const parent = () => checkbox("Seleccionar todo");
    assert.ok(parent()); await click(checkbox("Carga manual"));
    assert.equal(parent().indeterminate, true); assert.equal(parent().getAttribute("aria-checked"), "mixed");
    await click(parent()); assert.equal(parent().checked, true);
    await click(parent()); assert.equal(checkbox("Carga manual").checked, false);
    await click(button("Remitente")); await click(checkbox("Anaana@example.test"));
    const search = document.querySelector<HTMLInputElement>('input[type="search"]')!;
    const type = (value: string) => act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(search, value); search.dispatchEvent(new Event("input", { bubbles: true })); });
    await type("Bea");
    assert.equal(checkbox("Anaana@example.test").checked, true);
    await click(checkbox("Seleccionar resultados"));
    assert.equal(checkbox("Beabea@example.test").checked, true);
    await click(checkbox("Seleccionar resultados"));
    assert.equal(checkbox("Beabea@example.test").checked, false); assert.equal(checkbox("Anaana@example.test").checked, true);
    await type("missing"); assert.equal(checkbox("Seleccionar resultados").disabled, true);
    assert.equal(checkbox("Anaana@example.test").checked, true);
    assert.equal(host.querySelector("output")?.textContent, JSON.stringify(emptyReceptionFilters()), "edits remain draft");
    await click(button("Aplicar"));
    assert.deepEqual(JSON.parse(host.querySelector("output")!.textContent!), { channels: [], senders: ["a"] });
  } finally { await act(async () => { root.unmount(); host.remove(); }); }
});

const off = { available: false }, on = { available: true };
test.each<[string, ReceivingChannels, string[]]>([
  ["both off", { whatsapp: off, email: off }, ["Carga manual", "Escrito aquí"]],
  ["both on", { whatsapp: on, email: on }, ["WhatsApp", "Correo", "Carga manual", "Escrito aquí"]],
  ["email only", { whatsapp: off, email: on }, ["Correo", "Carga manual", "Escrito aquí"]],
  ["WhatsApp only", { whatsapp: on, email: off }, ["WhatsApp", "Carga manual", "Escrito aquí"]],
])("Canal offers only the channels the server says are available: %s", async (_, receivingChannels, expected) => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } } });
  const { BusinessContext } = await import("@/components/business-app/business-context");
  const business = { receivingChannels } as unknown as import("@/components/business-app/BusinessWorkspace").BusinessContextValue;
  const Filters = (await import("@/components/business-app/recepcion/ReceptionFilters")).default;
  const { emptyReceptionFilters } = await import("@/components/business-app/recepcion/reception-filters");
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  try {
    await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={business}><Filters value={emptyReceptionFilters()} onChange={() => undefined} senders={[]} /></BusinessContext.Provider></I18nextProvider>); });
    await act(async () => { [...document.querySelectorAll<HTMLButtonElement>("button")].find(node => node.textContent === "Filtros")!.click(); });
    const canal = document.querySelector('[role="tabpanel"][aria-label="Canal"]');
    assert.ok(canal, "the Canal group is open");
    const offered = [...canal.querySelectorAll("label")].map(node => node.textContent).filter(label => label !== "Seleccionar todo");
    assert.deepEqual(offered, expected);
  } finally { await act(async () => { root.unmount(); host.remove(); }); }
});
