import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BusinessUpdate } from "@/lib/business-api";
import { BUSINESS_STATUS } from "@/components/business-app/foundation/presentation";

mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("view=updates"),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz?view=updates" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

function flatten(node: unknown, prefix = "", out = new Map<string, string>()) {
  for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === "object") flatten(value, path, out);
    else out.set(path, String(value));
  }
  return out;
}
const SPANISH_VALUES = new Set(flatten(spanish).values());
const ENGLISH_ONLY = [...flatten(english).values()].filter((value) => value.length > 3 && !SPANISH_VALUES.has(value));

const update = (overrides: Partial<BusinessUpdate>): BusinessUpdate => ({
  id: "receipt_ready:r1",
  kind: "receipt_ready",
  occurred_at: new Date().toISOString(),
  receipt_id: "r1",
  expense_id: null,
  error_code: null,
  attention: null,
  label: "Ferretería La Esquina",
  ...overrides,
});

async function mount(overrides: Partial<BusinessDataSource> = {}) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const BusinessUpdatesPanel = (await import("@/components/business-app/BusinessUpdatesPanel")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const source = { ...createFixtureBusinessDataSource({ chatAvailable: true }), ...overrides };
  let business: ReturnType<typeof useBusiness> | null = null;
  function Probe() {
    business = useBusiness();
    return <BusinessUpdatesPanel />;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as never}>
            <Probe />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const wait = (ms: number) => act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 80 && !done(); i += 1) await wait(25);
    assert.ok(done(), "the screen settled");
  };
  const rows = () => [...host.querySelectorAll<HTMLElement>('[data-testid="business-update-row"]')];
  const close = async () => {
    await act(async () => root.unmount());
    host.remove();
  };
  return { act, host, wait, settle, rows, close, source, business: () => business! };
}

describe("Novedades rows", () => {
  test("each update the API sends is one row, in the API's order, newest first", async () => {
    const page = await mount({
      updates: async () => [
        update({ id: "expense_confirmed:r1", kind: "expense_confirmed", occurred_at: "2026-10-19T10:00:00Z", receipt_id: "r1", label: "Nube Hosting" }),
        update({ id: "receipt_needs_attention:r2", kind: "receipt_needs_attention", occurred_at: "2026-10-18T10:00:00Z", receipt_id: "r2", label: "Render", attention: "unreadable" }),
      ],
    });
    await page.settle(() => page.rows().length > 0);
    assert.deepEqual(
      page.rows().map((row) => [row.querySelector("a")?.getAttribute("href"), row.querySelector('[data-testid="status-pill"]')?.getAttribute("data-status")]),
      [["?receipt=r1", "approved"], ["?receipt=r2", "needs_attention"]],
    );
    await page.close();
  });

  test("every row is one link to its receipt holding the pill, the supplier, one sentence and the time", async () => {
    const page = await mount();
    await page.settle(() => page.rows().length > 0);
    const receipts = (await page.source.receiptPage!("all")).items;
    for (const row of page.rows()) {
      const links = row.querySelectorAll("a");
      assert.equal(links.length, 1, "the whole row is one link");
      const link = links[0];
      assert.equal(row.querySelectorAll("button").length, 0, "the row has no other control");
      const id = new URLSearchParams(link.getAttribute("href")!.slice(1)).get("receipt")!;
      const receipt = receipts.find((item) => item.id === id);
      assert.ok(receipt, `the row opens a real receipt (${id})`);
      assert.equal(link.querySelectorAll('[data-testid="status-pill"]').length, 1);
      assert.ok(link.querySelector("time")?.textContent?.trim(), "the time is in the row");
      const name = receipt.merchant ?? receipt.filename;
      assert.ok(link.textContent?.includes(name!), `the row names ${name}`);
      if (receipt.merchant) assert.ok(!link.textContent?.includes(receipt.filename!), `no file name beside ${receipt.merchant}`);
    }
    await page.close();
  });

  test("clicking a row opens the receipt detail in place", async () => {
    const page = await mount();
    await page.settle(() => page.rows().length > 0);
    const link = page.rows()[0].querySelector("a")!;
    const id = new URLSearchParams(link.getAttribute("href")!.slice(1)).get("receipt");
    await page.act(async () => { link.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 })); });
    assert.deepEqual(page.business().panel, { kind: "receipt", receiptId: id });
    await page.close();
  });

  test("each pill is the locked pair for the row's state, and nothing else on a row is colored", async () => {
    const page = await mount({
      updates: async () => [
        update({ id: "a", kind: "receipt_ready", receipt_id: "a" }),
        update({ id: "b", kind: "receipt_needs_attention", receipt_id: "b", attention: "unreadable" }),
        update({ id: "c", kind: "expense_confirmed", receipt_id: "c" }),
      ],
    });
    await page.settle(() => page.rows().length === 3);
    const expected = ["pending", "needs_attention", "approved"] as const;
    const icons = { pending: "lucide-clock", needs_attention: "lucide-circle-alert", approved: "lucide-circle-check" };
    page.rows().forEach((row, index) => {
      const pill = row.querySelector<HTMLElement>('[data-testid="status-pill"]')!;
      const tone = BUSINESS_STATUS[expected[index]];
      assert.equal(pill.dataset.status, expected[index]);
      assert.equal(pill.textContent, tone.label);
      assert.equal(pill.style.color, tone.ink);
      assert.equal(pill.style.backgroundColor, tone.surface);
      assert.deepEqual([...pill.querySelectorAll("svg")].map((icon) => icon.classList.contains(icons[expected[index]])), [true], "the pill carries its one icon");
      assert.deepEqual([...row.querySelectorAll("svg")].filter((icon) => !pill.contains(icon)).map((icon) => icon.outerHTML), [], "no dashed circle or red icon beside the pill");
      const outsidePill = [...row.querySelectorAll<HTMLElement>("*")].filter((element) => !pill.contains(element));
      assert.deepEqual(outsidePill.filter((element) => /#9e2f39|#d66d75|red|dashed/i.test(element.className + element.getAttribute("style"))).map((element) => element.outerHTML), []);
    });
    await page.close();
  });

  test("the sentence keeps today's words without the name or the status words, in Spanish", async () => {
    const page = await mount({
      updates: async () => [
        update({ id: "a", kind: "receipt_ready", receipt_id: "a", label: "Papelería Central" }),
        update({ id: "b", kind: "receipt_needs_attention", receipt_id: "b", label: "IMG_2209.jpg", attention: "unreadable" }),
        update({ id: "c", kind: "expense_confirmed", receipt_id: "c", label: "Nube Hosting" }),
      ],
    });
    await page.settle(() => page.rows().length === 3);
    const sentences = page.rows().map((row) => {
      const [, name, sentence] = [...row.querySelector("a")!.children].map((child) => child.textContent ?? "");
      assert.ok(!sentence.includes(name), "the sentence does not repeat the name");
      assert.ok(!/necesita atención|pendiente|aprobado/i.test(sentence), "the pill carries the status words");
      assert.ok(!/Argus|flujo|revisión \d/i.test(sentence));
      assert.deepEqual(ENGLISH_ONLY.filter((value) => sentence.includes(value)), []);
      return sentence;
    });
    assert.deepEqual(sentences, [
      "Está listo para revisar",
      "No pudimos leer este recibo. Escribe los detalles tú mismo o envía una foto más clara.",
      "Se guardó como gasto",
    ]);
    await page.close();
  });
});

describe("Novedades states", () => {
  test("the heading is the H1 Novedades with its line, shown before the rows arrive", async () => {
    let release: (items: BusinessUpdate[]) => void = () => undefined;
    const page = await mount({ updates: () => new Promise((resolve) => { release = resolve; }) });
    const heading = page.host.querySelector("h1");
    assert.equal(heading?.textContent, "Novedades");
    assert.match(heading!.className, /font-display/);
    assert.match(heading!.className, /font-medium/);
    assert.equal(heading?.nextElementSibling?.textContent, "Resultados de tus recibos y lo que necesita tu atención.");
    assert.equal(page.host.querySelector('[data-testid="business-loading"]'), null, "no skeleton flashes before 300ms");
    await page.wait(350);
    const skeleton = page.host.querySelector('[data-testid="business-loading"]');
    assert.equal(skeleton?.getAttribute("data-layout"), "updates");
    assert.equal(page.host.querySelector("h1")?.textContent, "Novedades", "the heading stays while loading");
    await page.act(async () => release([update({})]));
    await page.settle(() => page.rows().length === 1);
    assert.equal(page.host.querySelector('[data-testid="business-loading"]'), null);
    await page.close();
  });

  test("an empty feed is a first-run empty state in the card, with Agregar", async () => {
    const page = await mount({ updates: async () => [] });
    await page.settle(() => page.host.querySelector('[data-testid="business-updates-empty"]') !== null);
    const empty = page.host.querySelector('[data-testid="business-updates-empty"]')!;
    await page.settle(() => empty.querySelector("button") !== null);
    const state = empty.querySelector('[data-empty-kind="first_run"]');
    assert.ok(state, "the card holds a first-run empty state");
    assert.ok(state.querySelector("svg[data-mark]"), "the empty state is drawn");
    assert.equal(state.querySelector("h3")?.textContent, "Aquí verás qué pasó con tus recibos");
    assert.equal(state.querySelector("p")?.textContent, "Cuando Cuadrao lea, guarde o necesite algo de un recibo, te avisamos aquí.");
    assert.deepEqual([...state.querySelectorAll("button")].map((button) => button.textContent?.trim()), ["Agregar"]);
    await page.close();
  });

  test("a failed load says so in Spanish with Reintentar, and Reintentar loads the rows", async () => {
    let fail = true;
    const page = await mount({ updates: async () => { if (fail) throw new Error("offline"); return [update({})]; } });
    await page.settle(() => page.host.querySelector('[data-testid="business-updates-error"]') !== null);
    const alert = page.host.querySelector('[data-testid="business-updates-error"]')!;
    assert.equal(alert.getAttribute("role"), "alert");
    assert.equal(alert.getAttribute("data-empty-kind"), "error");
    assert.equal(alert.querySelector("h3")?.textContent, "No pudimos cargar las novedades");
    assert.ok(alert.querySelector("svg[data-mark]"), "the error is drawn");
    const retry = [...alert.querySelectorAll("button")];
    assert.deepEqual(retry.map((button) => button.textContent?.trim()), ["Reintentar"]);
    fail = false;
    await page.act(async () => { retry[0].click(); });
    await page.settle(() => page.rows().length === 1);
    assert.equal(page.host.querySelector('[data-testid="business-updates-error"]'), null);
    assert.equal(page.host.querySelector('[role="alert"]'), null);
    await page.close();
  });

  test("a failed refresh keeps the loaded rows on screen", async () => {
    let fail = false;
    const page = await mount({ updates: async () => { if (fail) throw new Error("offline"); return [update({})]; } });
    await page.settle(() => page.rows().length === 1);
    fail = true;
    await page.act(async () => page.business().reload());
    await page.settle(() => page.host.querySelector('[role="alert"]') !== null);
    assert.equal(page.rows().length, 1);
    await page.close();
  });
});

