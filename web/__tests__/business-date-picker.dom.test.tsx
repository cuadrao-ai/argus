import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";

mock.module("next/navigation", () => ({
  usePathname: () => "/biz",
  useRouter: () => ({ push: () => {}, replace: () => {}, refresh: () => {}, prefetch: () => {} }),
  useSearchParams: () => new URLSearchParams(),
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function render(node: ReactNode) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<I18nextProvider i18n={i18n}>{node}</I18nextProvider>);
  });
  const type = (input: HTMLInputElement, value: string) => act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  const key = (target: Element, name: string) => act(async () => {
    target.dispatchEvent(new KeyboardEvent("keydown", { key: name, bubbles: true }));
  });
  const settle = async (ready: () => boolean) => {
    for (let i = 0; i < 80 && !ready(); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    assert.ok(ready(), "the page settled");
  };
  return {
    host,
    act,
    type,
    key,
    settle,
    close: () => act(async () => { root.unmount(); host.remove(); }),
  };
}

async function picker(value: string, onChange: (iso: string | null, invalid: boolean) => void = () => {}) {
  const { DatePicker } = await import("@/components/business-app/foundation/DatePicker");
  const { useState } = await import("react");
  function Harness() {
    const [day, setDay] = useState(value);
    return <><label htmlFor="day">Fecha de actividad</label><DatePicker id="day" label="Fecha de actividad" value={day} onChange={(iso, invalid) => { onChange(iso, invalid); setDay(iso ?? ""); }} /></>;
  }
  const page = await render(<Harness />);
  const input = page.host.querySelector<HTMLInputElement>("#day")!;
  const trigger = page.host.querySelector<HTMLButtonElement>('button[aria-haspopup="dialog"]')!;
  const dialog = () => page.host.querySelector<HTMLElement>('[data-testid="date-picker-dialog"]');
  const day = (iso: string) => page.host.querySelector<HTMLButtonElement>(`[data-day="${iso}"]`)!;
  return { ...page, input, trigger, dialog, day };
}

describe("the single-date picker", () => {
  test("shows the day as 14 oct 2026, never a native date input, and takes dd/mm/aaaa", async () => {
    const changes: [string | null, boolean][] = [];
    const page = await picker("2026-10-14", (iso, invalid) => changes.push([iso, invalid]));
    assert.equal(page.host.querySelector('input[type="date"]'), null);
    assert.equal(page.input.type, "text");
    assert.equal(page.input.value, "14 oct 2026");
    assert.equal(page.input.placeholder, "dd/mm/aaaa");
    assert.ok(page.trigger.querySelector("svg"), "calendar icon");
    await page.act(async () => { page.input.focus(); });
    assert.equal(page.input.value, "14/10/2026", "typing shows the dd/mm/aaaa form");
    assert.deepEqual([page.input.selectionStart, page.input.selectionEnd], [0, 10], "the whole day is selected to type over");
    await page.type(page.input, "18/10");
    await page.type(page.input, "10/31/2026");
    assert.equal(page.input.value, "10/31/2026", "a parent that stores half-typed text as empty keeps the typing");
    await page.type(page.input, "18/10/2026");
    assert.deepEqual(changes, [[null, true], [null, true], ["2026-10-18", false]]);
    await page.act(async () => { page.input.blur(); });
    assert.equal(page.input.value, "18 oct 2026");
    await page.close();
  });

  test("opens one month that starts on Monday, with Hoy and Ayer", async () => {
    const page = await picker("2026-10-14");
    assert.equal(page.dialog(), null);
    await page.act(async () => { page.trigger.click(); });
    const dialog = page.dialog()!;
    assert.equal(page.trigger.getAttribute("aria-expanded"), "true");
    const grid = dialog.querySelector('[role="grid"]')!;
    const heading = dialog.querySelector(`#${CSS.escape(grid.getAttribute("aria-labelledby")!)}`)!;
    assert.equal(heading.textContent, "octubre de 2026");
    assert.match(heading.className, /font-display/);
    assert.match(heading.className, /font-medium/);
    assert.equal(dialog.getAttribute("aria-labelledby"), grid.getAttribute("aria-labelledby"));
    assert.deepEqual([...grid.querySelectorAll("th")].map((cell) => cell.textContent), ["lu", "ma", "mi", "ju", "vi", "sá", "do"]);
    const firstWeek = [...grid.querySelectorAll("tbody tr")[0].querySelectorAll("td")].map((cell) => cell.textContent);
    assert.deepEqual(firstWeek, ["", "", "", "1", "2", "3", "4"], "1 oct 2026 is a Thursday");
    assert.equal(page.day("2026-10-14").getAttribute("tabindex"), "0");
    assert.equal(page.day("2026-10-14").closest("td")?.getAttribute("aria-selected"), "true");
    assert.equal(page.day("2026-10-14").getAttribute("aria-label"), "14 oct 2026");
    assert.deepEqual([...dialog.querySelectorAll("button")].slice(0, 2).map((button) => button.textContent), ["Hoy", "Ayer"]);
    for (const button of dialog.querySelectorAll("button")) assert.match(button.className, /(h-11 w-11|min-h-11)/, button.outerHTML);
    await page.close();
  });

  test("Hoy and Ayer choose today and yesterday and close the month", async () => {
    const { todayIso } = await import("@/components/business-app/business-format");
    const changes: (string | null)[] = [];
    const page = await picker("2026-10-14", (iso) => changes.push(iso));
    const now = new Date();
    const yesterday = todayIso(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1));
    await page.act(async () => { page.trigger.click(); });
    const ayer = [...page.dialog()!.querySelectorAll("button")].find((button) => button.textContent === "Ayer")!;
    await page.act(async () => { ayer.click(); });
    assert.equal(page.dialog(), null);
    await page.act(async () => { page.trigger.click(); });
    const hoy = [...page.dialog()!.querySelectorAll("button")].find((button) => button.textContent === "Hoy")!;
    await page.act(async () => { hoy.click(); });
    assert.deepEqual(changes, [yesterday, todayIso()]);
    assert.equal(document.activeElement, page.trigger);
    await page.close();
  });

  test("arrow keys move the day, Enter picks it, Esc closes and returns focus", async () => {
    const changes: (string | null)[] = [];
    const page = await picker("2026-10-30", (iso) => changes.push(iso));
    await page.act(async () => { page.trigger.click(); });
    assert.equal(document.activeElement, page.day("2026-10-30"));
    await page.key(page.day("2026-10-30"), "ArrowRight");
    assert.equal(document.activeElement, page.day("2026-10-31"));
    await page.key(page.day("2026-10-31"), "ArrowDown");
    assert.equal(document.activeElement, page.day("2026-11-07"), "a week down crosses into noviembre");
    assert.match(page.dialog()!.textContent ?? "", /noviembre de 2026/);
    await page.key(page.day("2026-11-07"), "ArrowUp");
    await page.key(page.day("2026-10-31"), "ArrowLeft");
    assert.equal(document.activeElement, page.day("2026-10-30"));
    await page.key(page.day("2026-10-30"), "Escape");
    assert.equal(page.dialog(), null);
    assert.equal(document.activeElement, page.trigger);
    await page.act(async () => { page.trigger.click(); });
    await page.key(page.day("2026-10-30"), "ArrowLeft");
    await page.act(async () => { (document.activeElement as HTMLButtonElement).click(); });
    assert.deepEqual(changes, ["2026-10-29"]);
    assert.equal(page.input.value, "29 oct 2026");
    await page.close();
  });

  test("the month arrows turn the page", async () => {
    const page = await picker("2026-01-15");
    await page.act(async () => { page.trigger.click(); });
    const [previous, next] = [...page.dialog()!.querySelectorAll<HTMLButtonElement>("button[aria-label]")].filter((button) => !button.dataset.day);
    assert.equal(previous.getAttribute("aria-label"), "Mes anterior");
    assert.equal(next.getAttribute("aria-label"), "Mes siguiente");
    await page.act(async () => { previous.click(); });
    assert.match(page.dialog()!.textContent ?? "", /diciembre de 2025/);
    await page.act(async () => { next.click(); next.click(); });
    assert.match(page.dialog()!.textContent ?? "", /febrero de 2026/);
    await page.close();
  });

  test("a phone number pad's ddmmaaaa counts, a year before 1900 does not, and a wrong day is marked invalid", async () => {
    const changes: [string | null, boolean][] = [];
    const page = await picker("", (iso, invalid) => changes.push([iso, invalid]));
    await page.act(async () => { page.input.focus(); });
    await page.type(page.input, "14/10/0026");
    assert.equal(page.input.getAttribute("aria-invalid"), "true");
    await page.type(page.input, "05102026");
    assert.equal(page.input.getAttribute("aria-invalid"), "false");
    assert.deepEqual(changes, [[null, true], ["2026-10-05", false]]);
    await page.close();
  });

  test("a new value from the record replaces what the field shows", async () => {
    const { DatePicker } = await import("@/components/business-app/foundation/DatePicker");
    const { useState } = await import("react");
    let replace: (iso: string) => void = () => {};
    function Harness() {
      const [day, setDay] = useState("2026-10-14");
      replace = setDay;
      return <><label htmlFor="day">Fecha</label><DatePicker id="day" label="Fecha" value={day} onChange={() => {}} /></>;
    }
    const page = await render(<Harness />);
    const input = page.host.querySelector<HTMLInputElement>("#day")!;
    await page.act(async () => { replace("2026-09-02"); });
    assert.equal(input.value, "2 sept 2026");
    await page.close();
  });

  test("a press outside the open month closes it", async () => {
    const page = await picker("2026-10-14");
    await page.act(async () => { page.trigger.click(); });
    assert.ok(page.dialog());
    await page.act(async () => { document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true })); });
    assert.equal(page.dialog(), null);
    await page.close();
  });

  test("an empty date shows only the format and stays empty", async () => {
    const page = await picker("");
    assert.equal(page.input.value, "");
    assert.equal(page.input.placeholder, "dd/mm/aaaa");
    await page.close();
  });
});

describe("receipt detail uses the picker for its date", () => {
  test("the receipt review form has no native date input and keeps the read day", async () => {
    const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
    const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
    const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
    const { setChosenGrant } = await import("@/lib/business-grant");
    const { formatDay } = await import("@/components/business-app/business-format");
    const ReceiptReviewPanel = (await import("@/components/business-app/ReceiptReviewPanel")).default;
    setChosenGrant(null);
    const source = createFixtureBusinessDataSource({ chatAvailable: false });
    const receipt = await source.receipt("rcpt-ferreteria");
    const page = await render(
      <BusinessConsentTestProvider accepted>
        <BusinessWorkspaceProvider source={source}>
          <ReceiptReviewPanel target={{ kind: "receipt", id: "rcpt-ferreteria" }} />
        </BusinessWorkspaceProvider>
      </BusinessConsentTestProvider>,
    );
    await page.settle(() => Boolean(page.host.querySelector('[data-testid="receipt-review-fields"] button[aria-haspopup="dialog"]')));
    assert.equal(page.host.querySelector('input[type="date"]'), null);
    const fields = page.host.querySelector('[data-testid="receipt-review-fields"]')!;
    const input = fields.querySelector<HTMLInputElement>('input[placeholder="dd/mm/aaaa"]')!;
    assert.equal(fields.querySelector(`label[for="${CSS.escape(input.id)}"]`)?.textContent, "Fecha");
    assert.equal(input.value, formatDay(receipt.occurred_on, "es-419"));
    const save = [...page.host.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent === "Guardar detalles de revisión")!;
    const merchant = [...fields.querySelectorAll("label")].find((label) => label.textContent?.startsWith("Comercio"))!.querySelector("input")!;
    await page.type(merchant, "Ferretería La Esquina SRL");
    const account = [...fields.querySelectorAll("label")].find((label) => label.textContent?.startsWith("Pagado desde"))!.querySelector("select")!;
    await page.act(async () => {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!.call(account, account.options[1].value);
      account.dispatchEvent(new Event("change", { bubbles: true }));
    });
    assert.equal(save.disabled, false, "a changed merchant can be saved");
    await page.act(async () => { input.focus(); });
    await page.type(input, "12/1");
    assert.equal(save.disabled, true, "a half-typed date blocks the save");
    await page.type(input, "12/10/2026");
    assert.equal(save.disabled, false, "a whole day unblocks it");
    await page.close();
  });

  test("the prepared record's date editor is the picker", async () => {
    const ReceiptFactEditor = (await import("@/components/business-app/ReceiptFactEditor")).default;
    const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
    const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
    const dossier = await createFixtureBusinessDataSource().dossier(dossierFixtureIds.ready);
    const patches: unknown[] = [];
    const page = await render(<ReceiptFactEditor field="occurred_on" facts={dossier.facts} patch={{}} accounts={[]} currencies={[]} disabled={false} autoFocus={false} onChange={(patch, invalid) => patches.push([patch, invalid])} />);
    assert.equal(page.host.querySelector('input[type="date"]'), null);
    const input = page.host.querySelector<HTMLInputElement>('input[placeholder="dd/mm/aaaa"]')!;
    assert.equal(page.host.querySelector(`label[for="${CSS.escape(input.id)}"]`)?.textContent, "Fecha de actividad");
    assert.ok(page.host.querySelector('button[aria-haspopup="dialog"]'));
    await page.act(async () => { input.focus(); });
    await page.type(input, "02/10/2026");
    assert.deepEqual(patches.at(-1), [{ occurred_on: { state: "known", value: "2026-10-02" } }, false]);
    await page.close();
  });
});
