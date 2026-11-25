import assert from "node:assert/strict";
import { test } from "bun:test";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { reviewPurchase, reviewSalePayment } from "@/lib/business-dgii";
import BusinessFiscalProfile from "@/components/business-app/BusinessFiscalProfile";
import type { BusinessDossier } from "@/lib/business-dossier";
import spanish from "@/public/locales/es-419/common.json";
import english from "@/public/locales/en/common.json";
import { field, fullForm, mountEditor, registerDom } from "./fixtures/fiscal-editor";

test("the form holds the rest of the 606: the facts with their own row are not fields here, and it sends them unchanged", async () => {
  const view = await mountEditor();
  try {
    assert.equal(view.host.querySelector("details"), null, "the tab holds the form: nothing folds it away");
    assert.deepEqual([...view.host.querySelectorAll("[data-field]")].map((row) => row.firstElementChild?.textContent).slice(0, 1), ["ITBIS facturado"]);
    for (const field of ["rnc", "ncf", "category", "payment_method"]) assert.equal(view.host.querySelector(`[data-field="${field}"]`), null);
    await view.open("itbis_cost");
    await view.input("itbis_cost", "12.00");
    assert.equal(view.dirty.at(-1), true);
    await view.save("itbis_cost");
    const request = view.writes[0];
    assert.ok(request.key);
    assert.deepEqual(request.input, { version: view.dossier.version, dgii: { fiscal: { rnc: "131999888", ncf: "B0100000099", itbis: "526.27" }, declaration: { form: "606", category: null, itbis: null, itbis_cost: "12.00", payment_method: null, actual_refund: false, purchase_activity_id: null } } });
    assert.equal(view.changes.length, 1);
    assert.equal(view.dirty.at(-1), false);
  } finally { await view.dispose(); }
});

const groupsOf = (host: Element) => [...host.querySelectorAll<HTMLElement>("[data-group]")].map((group) => [group.dataset.group, group.querySelector("h3")?.textContent]);

test("the fields read in five groups, every field the server sends stays, and no date is a native input", async () => {
  const view = await mountEditor({ fields: fullForm });
  try {
    assert.deepEqual(groupsOf(view.host), [["identity", "Reporte 606"], ["amounts", "Monto facturado"], ["itbis", "ITBIS"], ["retentions", "Retenciones"], ["other", "Otros impuestos"]]);
    const other = view.host.querySelector('[data-group="other"]');
    assert.ok(other?.textContent?.includes("a_new_server_column"), "an unknown field keeps its code instead of backend Spanish");
    assert.equal(view.host.querySelectorAll('input[type="date"]').length, 0);
    await view.open("paid_on");
    assert.ok(view.host.querySelector('[data-group="identity"] [aria-label="Abrir calendario"]'), "the date is our calendar");
    await view.cancel("paid_on");
    await view.open("services_amount");
    assert.ok(view.host.querySelector('[data-testid="fiscal-declaration-services_amount"]'), "an amount is our money field");
  } finally { await view.dispose(); }
});

const foldOf = (host: Element) => host.querySelector<HTMLButtonElement>('[data-group="retentions"] > div > button[aria-expanded]');
const shown = (host: Element, id: string) => {
  const row = host.querySelector(`[data-field="${id}"]`);
  return Boolean(row && !row.closest("[hidden]"));
};
const purchaseWithheld = (value: string) => (dossier: BusinessDossier): BusinessDossier => ({ ...dossier, dgii: { form: "606", itbis_withheld: value } });

test("a purchase with no withholdings folds them behind one row that opens and closes", async () => {
  const view = await mountEditor({ fields: fullForm });
  try {
    const fold = foldOf(view.host);
    assert.ok(fold, "the card offers to add one");
    assert.equal(fold.getAttribute("aria-expanded"), "false");
    assert.equal(fold.textContent, "Agregar retención");
    assert.equal(view.host.querySelector('[data-group="retentions"] > p')?.textContent, "Sin retenciones.");
    assert.equal(shown(view.host, "itbis_withheld"), false, "its fields wait behind the row");
    await act(async () => fold.click());
    assert.equal(fold.getAttribute("aria-expanded"), "true");
    assert.equal(fold.textContent, "Quitar", "an open card offers the way back");
    assert.equal(view.host.querySelector('[data-group="retentions"] > p'), null);
    assert.equal(shown(view.host, "itbis_withheld"), true);
    await act(async () => fold.click());
    assert.equal(fold.getAttribute("aria-expanded"), "false");
    assert.equal(shown(view.host, "itbis_withheld"), false);
  } finally { await view.dispose(); }
});

test("a purchase that holds a withholding shows the group open, with no row to fold it", async () => {
  const saved = await mountEditor({ fields: fullForm, dossier: purchaseWithheld("150.00") });
  try {
    assert.equal(foldOf(saved.host), null);
    assert.equal(saved.host.querySelector('[data-group="retentions"] h3')?.textContent, "Retenciones");
    assert.equal(shown(saved.host, "itbis_withheld"), true);
  } finally { await saved.dispose(); }
  const typed = await mountEditor({ fields: fullForm });
  try {
    await act(async () => foldOf(typed.host)!.click());
    await typed.open("itbis_withheld");
    await typed.input("itbis_withheld", "10.00");
    assert.equal(foldOf(typed.host), null, "a value typed into the open group keeps it open");
    assert.equal(shown(typed.host, "itbis_withheld"), true);
    await typed.input("itbis_withheld", "");
    assert.equal(foldOf(typed.host)?.getAttribute("aria-expanded"), "true");
    await typed.cancel("itbis_withheld");
    assert.equal(foldOf(typed.host)?.disabled, false, "the cleared row can fold again");
  } finally { await typed.dispose(); }
});

test("a sale folds its withholdings behind the same row as a purchase", async () => {
  const view = await mountEditor({ fields: fullForm, dossier: (dossier) => ({ ...dossier, document_type: "venta", facts: { ...dossier.facts, kind: { ...dossier.facts.kind, state: "known", value: "income" } as never } }) });
  try {
    const fold = foldOf(view.host);
    assert.equal(fold?.textContent, "Agregar retención");
    assert.equal(view.host.querySelector('[data-group="retentions"] > p')?.textContent, "Sin retenciones.");
    assert.equal(shown(view.host, "withheld_on"), false);
    await act(async () => fold!.click());
    assert.equal(shown(view.host, "withheld_on"), true);
    assert.equal(view.host.querySelector('[data-field="income_type"]'), null, "General owns the type of income");
  } finally { await view.dispose(); }
});

test("on a phone the fold is the same row, and it opens into the same column as every group", async () => {
  const view = await mountEditor({ fields: fullForm, width: 375 });
  try {
    const fold = foldOf(view.host);
    assert.ok(fold);
    assert.equal(fold.textContent, "Agregar retención");
    await act(async () => fold.click());
    const grid = (group: string) => view.host.querySelector(`[data-group="${group}"] > ul`)?.className;
    assert.ok(grid("identity"));
    assert.equal(grid("retentions"), grid("identity"));
  } finally { await view.dispose(); }
});

test("a date reaches the server as a day, and text that is not a date holds the save and says why", async () => {
  const view = await mountEditor({ fields: fullForm });
  try {
    await view.open("paid_on");
    const date = view.host.querySelector<HTMLInputElement>("#fiscal-declaration-paid_on");
    assert.ok(date);
    const type = (text: string) => act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(date, text);
      date.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await type("31/02/2026");
    await view.save("paid_on");
    assert.equal(view.writes.length, 0, "a day that does not exist is not sent");
    assert.ok(view.host.querySelector('[role="alert"]')?.textContent?.includes("fecha válida"));
    await type("15/10/2026");
    await view.save("paid_on");
    assert.equal(view.writes[0].input.dgii.declaration.paid_on, "2026-10-15");
  } finally { await view.dispose(); }
});

test("Formato never shows: the form is the declaration's, or the record's type", async () => {
  const formato = (host: Element) => Boolean(host.querySelector('[data-fact="form"]'));
  const known = await mountEditor({ fields: fullForm });
  assert.equal(formato(known.host), false, "an expense is a 606");
  await known.dispose();
  const income = await mountEditor({ fields: fullForm, dossier: (dossier) => ({ ...dossier, document_type: "venta", facts: { ...dossier.facts, kind: { ...dossier.facts.kind, state: "known", value: "income" } as never } }) });
  assert.equal(formato(income.host), false, "income is a 607");
  assert.ok(income.host.querySelector('[data-field="withheld_on"]'), "and it shows the 607's fields");
  await income.dispose();
  const open = await mountEditor({ fields: fullForm, dossier: (dossier) => ({ ...dossier, document_type: undefined, facts: { ...dossier.facts, kind: { state: "unknown", value: null, origin: null, verified: false, source_ids: [] } as never } }) });
  assert.equal(formato(open.host), false, "an unknown kind declares as a purchase until the server says otherwise");
  assert.ok(open.host.querySelector('[data-field="paid_on"]'), "and shows the 606's fields");
  await open.dispose();
  const saved = await mountEditor({ fields: fullForm, dossier: (dossier) => ({ ...dossier, document_type: undefined, dgii: { form: "607" } }) });
  assert.equal(formato(saved.host), false, "a saved declaration decides the form");
  assert.ok(saved.host.querySelector('[data-field="withheld_on"]'), "and shows its fields");
  await saved.dispose();
});

test("a lost fiscal review response retains the exact request key and blocks edits", async () => {
  const view = await mountEditor();
  try {
    await view.open("itbis_cost");
    await view.input("itbis_cost", "12.00");
    view.fail(); await view.save("itbis_cost");
    assert.ok(view.host.querySelector('[role="alert"] [data-testid="error-reference"]'), "the failure shows its reference");
    assert.ok([...view.host.querySelectorAll("input")].every((input) => input.disabled));
    await view.save("itbis_cost");
    assert.deepEqual(view.writes[1], view.writes[0]);
    assert.equal(view.changes.length, 0);
    assert.equal(view.dirty.at(-1), true);
  } finally { await view.dispose(); }
});

test("an owner's 606 choice is one purchase write with its key, not a declaration", async () => {
  const sent: { url: string; key: string | null; body: unknown }[] = [];
  const original = globalThis.fetch;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = async (url, init) => { sent.push({ url: String(url), key: new Headers(init?.headers).get("Idempotency-Key"), body: JSON.parse(String(init?.body)) }); return Response.json({}); };
  try {
    await reviewPurchase("draft-1", 4, { category: "02" }, "key-1");
    assert.ok(sent[0].url.endsWith("/business/drafts/draft-1/review"));
    assert.equal(sent[0].key, "key-1");
    assert.deepEqual(sent[0].body, { version: 4, purchase: { category: "02" } });
  } finally { globalThis.fetch = original; }
});

test("a sale's payment pick sends the form alone: no amount and no declaration", async () => {
  const sent: { url: string; key: string | null; body: unknown }[] = [];
  const original = globalThis.fetch;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = async (url, init) => { sent.push({ url: String(url), key: new Headers(init?.headers).get("Idempotency-Key"), body: JSON.parse(String(init?.body)) }); return Response.json({}); };
  try {
    await reviewSalePayment("draft-1", 4, "bank", "key-1");
    assert.ok(sent[0].url.endsWith("/business/drafts/draft-1/review"));
    assert.equal(sent[0].key, "key-1");
    assert.deepEqual(sent[0].body, { version: 4, sale_payment_form: "bank" });
  } finally { globalThis.fetch = original; }
});

test("an absent Business RNC shows No aplica and a read-only accountant cannot edit it", async () => {
  const release = registerDom();
  globalThis.fetch = async () => Response.json({ name: "Taller Norte", tax_id: null, can_edit: false });
  const i18n = i18next.createInstance(); await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  try {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessFiscalProfile /></I18nextProvider>));
    assert.match(host.textContent ?? "", /Taller Norte/);
    assert.match(host.textContent ?? "", /No aplica/);
    assert.equal(host.querySelectorAll("input, button, select").length, 0);
  } finally { await act(async () => root.unmount()); host.remove(); await release(); }
});

test("a read-only member reads an unnamed Business by the name every screen gives it", async () => {
  const release = registerDom();
  globalThis.fetch = async () => Response.json({ name: null, tax_id: null, can_edit: false });
  const i18n = i18next.createInstance(); await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  try {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessFiscalProfile /></I18nextProvider>));
    assert.match(host.textContent ?? "", /^Mi negocio · /);
  } finally { await act(async () => root.unmount()); host.remove(); await release(); }
});

test("the owner can save an eleven-digit filer cedula without losing leading zeros", async () => {
  const release = registerDom();
  const writes: unknown[] = [];
  globalThis.fetch = async (_url, init) => {
    if (!init?.body) return Response.json({ name: null, tax_id: null, can_edit: true });
    writes.push(JSON.parse(String(init.body)));
    return Response.json({ name: "Taller Norte", tax_id: { type: "cedula", value: "00100000001" }, can_edit: true });
  };
  const i18n = i18next.createInstance(); await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  try {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessFiscalProfile /></I18nextProvider>));
    const name = host.querySelector<HTMLInputElement>('input[name="business-name"]');
    const kind = host.querySelector<HTMLSelectElement>('select[name="tax-id-type"]');
    const value = host.querySelector<HTMLInputElement>('input[name="tax-id-value"]');
    const button = host.querySelector("button");
    assert.ok(name && kind && value && button);
    assert.equal(value.maxLength, 13);
    assert.equal(name.value, "", "an unnamed Business starts with an empty name field");
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      assert.ok(setter);
      setter.call(name, "Taller Norte");
      name.dispatchEvent(new Event("input", { bubbles: true }));
      kind.value = "cedula";
      kind.dispatchEvent(new Event("change", { bubbles: true }));
      setter.call(value, "001-0000000-1");
      value.dispatchEvent(new Event("input", { bubbles: true }));
    });
    assert.equal(button.disabled, false);
    await act(async () => button.click());
    assert.deepEqual(writes, [{
      name: "Taller Norte",
      previous_name: null,
      tax_id: { type: "cedula", value: "001-0000000-1" },
      previous_tax_id: null,
    }]);
    assert.equal(value.value, "00100000001", "the saved number keeps its leading zeros");
    assert.equal(kind.value, "cedula");
  } finally { await act(async () => root.unmount()); host.remove(); await release(); }
});

test("an unnamed Business opens the Negocio card with nothing to save", async () => {
  const release = registerDom();
  globalThis.fetch = async () => Response.json({ name: null, tax_id: null, can_edit: true });
  const i18n = i18next.createInstance(); await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  const dirty: boolean[] = [];
  try {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessFiscalProfile onDirtyChange={(value) => dirty.push(value)} /></I18nextProvider>));
    const name = host.querySelector<HTMLInputElement>('input[name="business-name"]');
    const save = host.querySelector<HTMLButtonElement>('button[type="submit"]');
    assert.ok(name && save);
    assert.equal(name.value, "");
    assert.equal(dirty.at(-1), false, "an untouched form has no changes to discard");
    assert.equal(save.disabled, true, "an untouched form has nothing to save");
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(name, "Taller Norte");
      name.dispatchEvent(new Event("input", { bubbles: true }));
    });
    assert.equal(dirty.at(-1), true);
    assert.equal(save.disabled, false);
  } finally { await act(async () => root.unmount()); host.remove(); await release(); }
});

test("the Negocio card fills the name field with a real name as saved", async () => {
  const release = registerDom();
  globalThis.fetch = async () => Response.json({ name: "My business supplies", tax_id: null, can_edit: true });
  const i18n = i18next.createInstance(); await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  try {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessFiscalProfile /></I18nextProvider>));
    assert.equal(host.querySelector<HTMLInputElement>('input[name="business-name"]')?.value, "My business supplies");
  } finally { await act(async () => root.unmount()); host.remove(); await release(); }
});


test("the 606 editor names its rows as the board does, in both languages", async () => {
  const view = await mountEditor({ fields: fullForm });
  try {
    const labels = () => [...view.host.querySelectorAll("[data-field]")].map((row) => row.firstElementChild?.textContent);
    assert.deepEqual(labels(), ["Tipo de ID", "Fecha de pago", "Servicios", "ITBIS llevado al costo", "ITBIS Retenido", "a_new_server_column"]);
    await act(async () => { await view.i18n.changeLanguage("en"); });
    assert.deepEqual(labels(), ["ID type", "Payment date", "Services", "ITBIS taken to cost", "ITBIS withheld", "a_new_server_column"]);
  } finally { await view.dispose(); }
});

test("the 607 editor names its rows as the board does, in both languages, and leaves out what a sale's tab does not hold", async () => {
  const sale607 = [
    field("id_type", "Tipo Identificación", "select", ["1", "2", "3"]), field("modified_ncf", "Número Comprobante Fiscal Modificado", "text"), field("income_type", "Tipo de Ingreso", "select", ["1"]),
    field("withheld_on", "Fecha de Retención", "date"), field("billed_amount", "Monto Facturado"), field("itbis", "ITBIS Facturado"),
    field("itbis_withheld_by_third_parties", "ITBIS Retenido por Terceros"), field("itbis_perceived", "ITBIS Percibido"), field("income_withheld_by_third_parties", "Retención Renta por Terceros"), field("income_perceived", "ISR Percibido"),
    field("other_taxes", "Otros Impuestos/Tasas"), field("legal_tip", "Monto Propina Legal"), field("bank", "Cheque/ Transferencia/ Depósito"), field("gift", "Bonos o Certificados de Regalo"),
  ];
  const view = await mountEditor({
    fields: { "606": [], "607": sale607 },
    dossier: (dossier) => ({ ...dossier, document_type: "venta", dgii: { form: "607" }, source_owned_fields: [], sale_payment: { form: null, options: ["bank", "gift"] } }),
  });
  try {
    const labels = () => [...view.host.querySelectorAll("[data-field]")].map((row) => row.firstElementChild?.textContent);
    assert.deepEqual(labels(), ["Tipo de ID", "Monto facturado", "ITBIS facturado", "ITBIS retenido por terceros", "Retención de renta por terceros", "Fecha de retención", "Otros Impuestos/Tasas"]);
    await act(async () => { await view.i18n.changeLanguage("en"); });
    assert.deepEqual(labels(), ["ID type", "Billed amount", "ITBIS billed", "ITBIS withheld by third parties", "Income tax withheld by third parties", "Withholding date", "Other taxes/fees"]);
    await view.open("id_type");
    assert.deepEqual([...view.host.querySelector<HTMLSelectElement>("#fiscal-declaration-id_type")!.options].map((option) => [option.value, option.text]), [["", "Unknown"], ["1", "01 · RNC"], ["2", "02 · Cédula"], ["3", "03 · Passport or tax ID"]]);
  } finally { await view.dispose(); }
});

for (const form of ["606", "607"] as const) {
  const title = `the ${form} editor names each DGII withholding and ID code with production i18n and saves only the code`;
  test(title, async () => {
    // Production initialization changes the shared singleton; keep it out of other tests.
    if (process.env.CUADRAO_TEST_FISCAL_I18N !== "true") {
      const result = Bun.spawnSync({
        cmd: [process.execPath, "test", import.meta.filename, "--test-name-pattern", title],
        cwd: `${import.meta.dir}/..`,
        env: { ...process.env, CUADRAO_TEST_FISCAL_I18N: "true" },
        stdout: "pipe",
        stderr: "pipe",
      });
      assert.equal(result.exitCode, 0, result.stderr.toString());
      return;
    }
    const name = form === "606" ? "income_withholding_type" : "id_type";
    const codes = form === "606" ? ["01", "02", "03", "04", "05", "06", "07", "08", "09"] : ["1", "2", "3"];
    const formFields = [field(name, name, "select", codes)];
    const view = await mountEditor({
      productionI18n: true,
      fields: { "606": [], "607": [], [form]: formFields },
      dossier: (dossier) => ({ ...dossier, dgii: { form }, source_owned_fields: form === "606" ? ["id_type"] : [] }),
    });
    const showWithholding = async () => {
      const fold = foldOf(view.host);
      if (fold && fold.getAttribute("aria-expanded") === "false") await act(async () => fold.click());
    };
    const options = async (id: string) => {
      await showWithholding();
      await view.open(id);
      const select = view.host.querySelector<HTMLSelectElement>(`#fiscal-declaration-${id}`);
      assert.ok(select);
      const labels = [...select.options].filter((option) => option.value).map((option) => [option.value, option.text]);
      await view.cancel(id);
      return labels;
    };
    try {
      for (const [language, catalog] of [["es-419", spanish], ["en", english]] as const) {
        await act(async () => { await view.i18n.changeLanguage(language); });
        assert.equal(view.i18n.t(`business.dgii.option.${name}.99`, { defaultValue: "99" }), "", "the real missing-key handler overrides defaultValue");
        const names = catalog.business.dgii.option[name] as Record<string, string>;
        assert.deepEqual(await options(name), codes.map((code) => [code, `${code.padStart(2, "0")} · ${names[code]}`]));
      }
      await act(async () => { await view.i18n.changeLanguage("es-419"); });
      assert.deepEqual((await options(name))[1], form === "606" ? ["02", "02 · Honorarios por servicios"] : ["2", "02 · Cédula"]);
      if (form === "607") assert.deepEqual((await options(name))[2], ["3", "03 · Pasaporte o ID tributaria"]);
      const choose = async (id: string, value: string) => {
        await showWithholding();
        await view.open(id);
        const select = view.host.querySelector<HTMLSelectElement>(`#fiscal-declaration-${id}`);
        assert.ok(select);
        await act(async () => { select.value = value; select.dispatchEvent(new Event("change", { bubbles: true })); });
        await view.save(id);
      };
      await choose(name, codes[1]);
      const latest = view.writes.at(-1);
      assert.ok(latest);
      assert.equal(view.writes.length, 1, "the row has one save");
      assert.equal(latest.input.dgii.declaration[name], codes[1]);
    } finally { await view.dispose(); }
  });
}

for (const [moved, es, en] of [
  [0, null, null],
  [1, "1 borrador pasó a Ventas: lo emitió tu negocio", "1 draft moved to Sales: your business issued it"],
  [2, "2 borradores pasaron a Ventas: los emitió tu negocio", "2 drafts moved to Sales: your business issued them"],
] as const) {
  test(`saving the Business RNC says the server moved ${moved} drafts to Ventas`, async () => {
    for (const [lng, translation, words] of [["es-419", spanish, es], ["en", english, en]] as const) {
      const release = registerDom();
      globalThis.fetch = async (_url, init) => init?.body
        ? Response.json({ name: "Taller Norte", tax_id: { type: "rnc", value: "199990013" }, legal_name: null, can_edit: true, retyped_drafts: moved })
        : Response.json({ name: "Taller Norte", tax_id: null, legal_name: null, can_edit: true });
      const i18n = i18next.createInstance(); await i18n.init({ lng, resources: { [lng]: { translation } } });
      const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
      try {
        await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessFiscalProfile /></I18nextProvider>));
        const value = host.querySelector<HTMLInputElement>('input[name="tax-id-value"]');
        assert.ok(value);
        await act(async () => {
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(value, "199990013");
          value.dispatchEvent(new Event("input", { bubbles: true }));
        });
        await act(async () => host.querySelector("button")?.click());
        const status = host.querySelector('[role="status"]');
        assert.match(status?.textContent ?? "", lng === "en" ? /^Details saved\./ : /^Datos guardados\./);
        assert.equal(host.querySelector('[data-testid="profile-drafts-retyped"]')?.textContent?.trim() ?? null, words);
      } finally { await act(async () => root.unmount()); host.remove(); await release(); }
    }
  });
}
