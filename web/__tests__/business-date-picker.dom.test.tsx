import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";
import type { DateFieldContext } from "@/components/business-app/foundation/DatePicker";

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

async function picker(value: string, onChange: (iso: string | null, invalid: boolean) => void = () => {}, context?: DateFieldContext) {
  const { DatePicker } = await import("@/components/business-app/foundation/DatePicker");
  const { useState } = await import("react");
  function Harness() {
    const [day, setDay] = useState(value);
    return <><label htmlFor="day">Fecha del comprobante</label><DatePicker id="day" label="Fecha del comprobante" value={day} context={context} onChange={(iso, invalid) => { onChange(iso, invalid); setDay(iso ?? ""); }} /></>;
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

  test("the calendar button is Abrir calendario and no accessible name is a placeholder key", async () => {
    const page = await picker("2026-10-14");
    const names = () => [...document.body.querySelectorAll<HTMLElement>("*")].flatMap((element) => [
      element.getAttribute("aria-label"),
      element.getAttribute("title"),
      element.getAttribute("placeholder"),
      ...(element.getAttribute("aria-labelledby") ?? "").split(" ").filter(Boolean).map((id) => document.getElementById(id)?.textContent ?? null),
      element.matches("button, a, label, th, [role]") ? element.textContent : null,
    ]).filter((name): name is string => Boolean(name));
    assert.equal(page.trigger.getAttribute("aria-label"), "Abrir calendario");
    assert.deepEqual(names().filter((name) => name.trim().startsWith("[placeholder]")), [], "closed");
    await page.act(async () => { page.trigger.click(); });
    assert.ok(page.dialog());
    assert.deepEqual(names().filter((name) => name.trim().startsWith("[placeholder]")), [], "open");
    await page.close();
  });
});

describe("typed dates", () => {
  test("take d/m/yy and d/m/aaaa, and refuse a day that does not exist or text that could mean two days", async () => {
    const { parseDayText } = await import("@/components/business-app/foundation/DatePicker");
    const cases: [string, string | null][] = [
      ["4/11/26", "2026-11-04"],
      ["04/11/26", "2026-11-04"],
      ["4/11/2026", "2026-11-04"],
      ["14/10/2026", "2026-10-14"],
      [" 4/11/26 ", "2026-11-04"],
      ["14102026", "2026-10-14"],
      ["041126", "2026-11-04"],
      ["29/2/24", "2024-02-29"],
      ["31/12/25", "2025-12-31"],
      ["1/1/26", "2026-01-01"],
      ["31/2/26", null],
      ["29/2/26", null],
      ["4/13/26", null],
      ["0/11/26", null],
      ["4/0/26", null],
      ["41126", null],
      ["4112026", null],
      ["4/11/2", null],
      ["4/11/202", null],
      ["4/11/02026", null],
      ["4/1126", null],
      ["14/10/0026", null],
      ["4-11-26", null],
      ["", null],
    ];
    assert.deepEqual(cases.map(([text]) => [text, parseDayText(text)]), cases);
  });

  test("4/11/26 typed in the field is 4 nov 2026", async () => {
    const changes: [string | null, boolean][] = [];
    const page = await picker("", (iso, invalid) => changes.push([iso, invalid]));
    await page.act(async () => { page.input.focus(); });
    await page.type(page.input, "4/11/26");
    assert.deepEqual(changes.at(-1), ["2026-11-04", false]);
    assert.equal(page.input.getAttribute("aria-invalid"), "false");
    await page.act(async () => { page.input.blur(); });
    assert.equal(page.input.value, "4 nov 2026");
    await page.close();
  });
});

describe("the document date knows the upload year", () => {
  const uploaded2026: DateFieldContext = { kind: "document", uploadedAt: "2026-11-10T15:00:00Z" };
  const note = (page: Awaited<ReturnType<typeof picker>>) => page.dialog()?.querySelector<HTMLElement>('[data-testid="date-picker-upload-year"]') ?? null;
  const buttonNamed = (root: Element, text: string) => [...root.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent === text);

  test("shows no Hoy or Ayer", async () => {
    const page = await picker("2026-11-04", () => {}, uploaded2026);
    await page.act(async () => { page.trigger.click(); });
    const words = [...page.dialog()!.querySelectorAll("button")].map((button) => button.textContent);
    assert.equal(words.includes("Hoy"), false);
    assert.equal(words.includes("Ayer"), false);
    await page.close();
  });

  test("a 2024 date on a 2026 upload shows Subido en 2026 and changes the date only on Usar", async () => {
    const changes: (string | null)[] = [];
    const page = await picker("2024-11-04", (iso) => changes.push(iso), uploaded2026);
    await page.act(async () => { page.trigger.click(); });
    const shown = note(page);
    assert.ok(shown, "the note shows");
    assert.match(shown.textContent ?? "", /Subido en 2026/);
    assert.deepEqual(changes, [], "the note alone changes nothing");
    assert.equal(page.input.value, "4 nov 2024");
    const use = buttonNamed(shown, "Usar 4 nov 2026");
    assert.ok(use, "the button names the day it sets");
    assert.match(use.className, /min-h-11/);
    await page.act(async () => { use.click(); });
    assert.deepEqual(changes, ["2026-11-04"]);
    assert.equal(page.input.value, "4 nov 2026");
    assert.equal(page.dialog(), null, "choosing closes the month like a day does");
    await page.act(async () => { page.trigger.click(); });
    assert.equal(note(page), null, "the years match now");
    await page.close();
  });

  test("no note when the years match, when the upload time is unknown, or outside a document date", async () => {
    for (const [value, context] of [
      ["2026-03-04", uploaded2026],
      ["2024-11-04", { kind: "document", uploadedAt: null }],
      ["2024-11-04", { kind: "past" }],
      ["", uploaded2026],
    ] as [string, DateFieldContext][]) {
      const page = await picker(value, () => {}, context);
      await page.act(async () => { page.trigger.click(); });
      assert.equal(note(page), null, `${value} ${JSON.stringify(context)}`);
      await page.close();
    }
  });

  test("29 feb 2024 on a 2026 upload offers 28 feb 2026", async () => {
    const changes: (string | null)[] = [];
    const page = await picker("2024-02-29", (iso) => changes.push(iso), uploaded2026);
    await page.act(async () => { page.trigger.click(); });
    await page.act(async () => { buttonNamed(note(page)!, "Usar 28 feb 2026")!.click(); });
    assert.deepEqual(changes, ["2026-02-28"]);
    await page.close();
  });

  test("the upload year is the local year, and near midnight no day shifts", async () => {
    const originalZone = process.env.TZ;
    process.env.TZ = "America/Santo_Domingo";
    try {
      const lateOnNewYearsEve: DateFieldContext = { kind: "document", uploadedAt: "2026-01-01T03:30:00Z" };
      const same = await picker("2025-12-31", () => {}, lateOnNewYearsEve);
      await same.act(async () => { same.trigger.click(); });
      assert.equal(note(same), null, "23:30 on 31 dic 2025 in Santo Domingo is still 2025");
      await same.close();

      const changes: (string | null)[] = [];
      const page = await picker("2024-12-31", (iso) => changes.push(iso), lateOnNewYearsEve);
      await page.act(async () => { page.trigger.click(); });
      assert.match(note(page)?.textContent ?? "", /Subido en 2025/);
      await page.act(async () => { buttonNamed(note(page)!, "Usar 31 dic 2025")!.click(); });
      assert.deepEqual(changes, ["2025-12-31"]);
      assert.equal(page.input.value, "31 dic 2025");
      await page.act(async () => { page.input.focus(); });
      await page.type(page.input, "1/1/26");
      assert.deepEqual(changes.at(-1), "2026-01-01");
      await page.act(async () => { page.input.blur(); });
      assert.equal(page.input.value, "1 ene 2026");
      await page.act(async () => { page.trigger.click(); });
      await page.act(async () => { page.day("2026-01-01").click(); });
      assert.deepEqual(changes.at(-1), "2026-01-01", "picking the first day keeps it");
      await page.close();
    } finally {
      if (originalZone === undefined) delete process.env.TZ; else process.env.TZ = originalZone;
    }
  });
});

describe("the month header jumps to a month and a year", () => {
  const heading = (page: Awaited<ReturnType<typeof picker>>) => page.dialog()!.querySelector("h2")!;
  const headerButton = (page: Awaited<ReturnType<typeof picker>>) => heading(page).querySelector("button")!;
  const named = (page: Awaited<ReturnType<typeof picker>>, text: string) => [...page.dialog()!.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent === text || button.getAttribute("aria-label") === text);

  test("noviembre de 2024 opens the months, the year opens recent years, and 2026 lands on noviembre de 2026 in two clicks", async () => {
    const changes: (string | null)[] = [];
    const page = await picker("2024-11-04", (iso) => changes.push(iso), { kind: "document", uploadedAt: "2026-11-10T15:00:00Z" });
    await page.act(async () => { page.trigger.click(); });
    assert.equal(headerButton(page).textContent, "noviembre de 2024");
    await page.act(async () => { headerButton(page).click(); });
    const months = page.dialog()!.querySelector('[data-testid="date-picker-months"]')!;
    assert.ok(months, "a month grid");
    assert.equal(months.querySelectorAll("button").length, 12);
    assert.equal(headerButton(page).textContent, "2024");
    assert.equal(document.activeElement?.getAttribute("aria-label"), "noviembre de 2024", "focus lands on the shown month");
    await page.act(async () => { headerButton(page).click(); });
    const years = page.dialog()!.querySelector('[data-testid="date-picker-years"]')!;
    assert.ok(years, "a list of years");
    const yearWords = [...years.querySelectorAll("button")].map((button) => button.dataset.year);
    assert.ok(yearWords.includes("2024") && yearWords.includes("2026"), yearWords.join(" "));
    const uploadYear = years.querySelector<HTMLButtonElement>('button[data-year="2026"]')!;
    assert.match(uploadYear.textContent ?? "", /Subido en 2026/, "the upload year is marked");
    assert.equal(years.querySelectorAll('[data-upload-year]').length, 1, "only the upload year");
    await page.act(async () => { uploadYear.click(); });
    assert.equal(headerButton(page).textContent, "noviembre de 2026");
    assert.equal(document.activeElement, page.day("2026-11-04"));
    assert.deepEqual(changes, [], "moving the view sets no date");
    await page.act(async () => { page.day("2026-11-04").click(); });
    assert.deepEqual(changes, ["2026-11-04"]);
    await page.close();
  });

  test("the month grid's arrows step years and a month opens its days", async () => {
    const page = await picker("2024-11-04");
    await page.act(async () => { page.trigger.click(); });
    await page.act(async () => { headerButton(page).click(); });
    await page.act(async () => { named(page, "2025")!.click(); });
    assert.equal(headerButton(page).textContent, "2025");
    await page.act(async () => { named(page, "2026")!.click(); });
    assert.equal(headerButton(page).textContent, "2026");
    await page.act(async () => { named(page, "2025")!.click(); });
    assert.equal(headerButton(page).textContent, "2025");
    await page.act(async () => { named(page, "marzo de 2025")!.click(); });
    assert.equal(headerButton(page).textContent, "marzo de 2025");
    assert.ok(page.day("2025-03-04"));
    for (const button of page.dialog()!.querySelectorAll("button")) assert.match(button.className, /(h-11 w-11|min-h-11)/, button.outerHTML);
    await page.close();
  });

  test("a new opening starts on the days again", async () => {
    const page = await picker("2024-11-04");
    await page.act(async () => { page.trigger.click(); });
    await page.act(async () => { headerButton(page).click(); });
    await page.key(page.dialog()!, "Escape");
    await page.act(async () => { page.trigger.click(); });
    assert.equal(headerButton(page).textContent, "noviembre de 2024");
    await page.close();
  });
});

describe("receipt detail uses the picker for its date", () => {
  test("the prepared record's date editor is the picker", async () => {
    const ReceiptFactEditor = (await import("@/components/business-app/ReceiptFactEditor")).default;
    const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
    const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
    const dossier = await createFixtureBusinessDataSource().dossier(dossierFixtureIds.ready);
    const patches: unknown[] = [];
    const page = await render(<ReceiptFactEditor field="occurred_on" facts={{ ...dossier.facts, occurred_on: { ...dossier.facts.occurred_on, state: "known", value: "2024-10-09" } as typeof dossier.facts.occurred_on }} uploadedAt="2026-10-10T14:20:00Z" patch={{}} accounts={[]} currencies={[]} disabled={false} autoFocus={false} onChange={(patch, invalid) => patches.push([patch, invalid])} />);
    assert.equal(page.host.querySelector('input[type="date"]'), null);
    const input = page.host.querySelector<HTMLInputElement>('input[placeholder="dd/mm/aaaa"]')!;
    assert.equal(page.host.querySelector(`label[for="${CSS.escape(input.id)}"]`)?.textContent, "Fecha del comprobante");
    const trigger = page.host.querySelector<HTMLButtonElement>('button[aria-haspopup="dialog"]')!;
    await page.act(async () => { trigger.click(); });
    const dialog = page.host.querySelector('[data-testid="date-picker-dialog"]')!;
    assert.deepEqual([...dialog.querySelectorAll("button")].filter((button) => ["Hoy", "Ayer"].includes(button.textContent ?? "")), [], "a receipt is almost never from today");
    assert.match(dialog.querySelector('[data-testid="date-picker-upload-year"]')?.textContent ?? "", /Subido en 2026Usar 9 oct 2026/);
    await page.key(dialog, "Escape");
    await page.act(async () => { input.focus(); });
    await page.type(input, "02/10/2026");
    assert.deepEqual(patches.at(-1), [{ occurred_on: { state: "known", value: "2026-10-02" } }, false]);
    await page.close();
  });
});
