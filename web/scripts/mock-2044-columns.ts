// Mock only (#2044): open each Registros column preset at 1440 and 1280, report the
// table's scroll width against its visible width, and capture it. Loopback only.
import { mkdirSync, writeFileSync } from "node:fs";
import { chromium } from "@playwright/test";

const base = process.env.MOCK_WEB ?? "http://127.0.0.1:58300";
const out = process.env.MOCK_OUT ?? "../../argus/temp/mock-2044-columns";
const only = process.env.MOCK_PRESETS?.split(",");
if (new URL(base).hostname !== "127.0.0.1") throw new Error("loopback only");

const ALL = ["counterparty_id", "counterparty", "date", "fiscal_number", "expense_type", "net_amount", "itbis_amount", "gross_amount", "stage", "note", "attachment", "payment_form", "funding"];
const hiddenExcept = (shown: string[]) => ALL.filter((key) => !shown.includes(key));
export const PRESETS: Record<string, { order: string[]; hidden: string[] }> = {
  A: { order: ALL, hidden: ["payment_form", "funding"] },
  B: { order: ALL, hidden: hiddenExcept(JSON.parse(process.env.MOCK_B ?? '["counterparty_id","counterparty","date","fiscal_number","net_amount","itbis_amount","gross_amount","stage"]')) },
  C: { order: ALL, hidden: hiddenExcept(JSON.parse(process.env.MOCK_C ?? '["counterparty_id","counterparty","date","fiscal_number","net_amount","itbis_amount","gross_amount"]')) },
};
export function report(preset: string, family: "purchase" | "sale") {
  return JSON.stringify({ schema_version: 2, filters: { period: { kind: "all" }, record_families: [family], currencies: ["DOP"] }, sort: "date_desc", presentation: { ...PRESETS[preset], density: 48 }, page: 1, page_size: 25 });
}

mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [];
for (const preset of only ?? Object.keys(PRESETS)) for (const family of ["purchase", "sale"] as const) for (const width of [1440, 1280]) {
  const context = await browser.newContext({ viewport: { width, height: 900 }, locale: "es-DO", colorScheme: "light" });
  await context.route("**/*", (route) => ["127.0.0.1", "localhost"].includes(new URL(route.request().url()).hostname) || route.request().url().startsWith("data:") ? route.fallback() : route.abort());
  await context.addInitScript(() => { localStorage.setItem("cuadrao-business-preview-language", "es-419"); localStorage.setItem("argus-theme", "light"); });
  const page = await context.newPage();
  const url = `${base}/biz?view=transactions&report=${encodeURIComponent(report(preset, family))}`;
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.locator('[data-testid="transacciones-records"] tbody tr').first().waitFor({ timeout: 60_000 });
  const guide = page.getByRole("button", { name: "Ocultar guía" });
  if (await guide.count()) { await guide.first().click(); await guide.first().waitFor({ state: "detached" }).catch(() => undefined); }
  await page.waitForTimeout(600);
  const measured = await page.evaluate(() => {
    const scroll = document.querySelector<HTMLElement>('[data-testid="transacciones-scroll"]')!;
    const table = scroll.querySelector("table")!;
    // Natural widths: the same table, auto layout, no wrapping, off screen.
    const probe = table.cloneNode(true) as HTMLTableElement;
    probe.querySelector("colgroup")?.remove();
    Object.assign(probe.style, { position: "absolute", left: "-99999px", top: "0", width: "auto", minWidth: "0", tableLayout: "auto" });
    probe.querySelectorAll<HTMLElement>("th, td, th *, td *").forEach((node) => { node.style.whiteSpace = "nowrap"; node.style.maxWidth = "none"; node.style.overflow = "visible"; });
    scroll.appendChild(probe);
    const natural = new Map([...probe.querySelectorAll<HTMLElement>("thead th")].map((th) => [th.dataset.col!, Math.ceil(th.getBoundingClientRect().width)]));
    probe.remove();
    const columns = [...table.querySelectorAll<HTMLElement>("thead th")].map((th) => ({ key: th.dataset.col!, width: Math.round(th.getBoundingClientRect().width), natural: natural.get(th.dataset.col!) }));
    const main = scroll.getBoundingClientRect();
    return { visible: scroll.clientWidth, scrollWidth: scroll.scrollWidth, table: Math.round(table.getBoundingClientRect().width), tableLeft: Math.round(main.left), fits: scroll.scrollWidth <= scroll.clientWidth, columns, lang: document.documentElement.lang };
  });
  await page.locator('[data-testid="transacciones-scroll"]').evaluate((node) => node.scrollIntoView({ block: "end" }));
  await page.waitForTimeout(300);
  const name = `${preset}-${family === "purchase" ? "compras" : "ventas"}-${width}`;
  await page.screenshot({ path: `${out}/${name}.png` });
  results.push({ preset, family, width, url: `/biz?view=transactions&report=${encodeURIComponent(report(preset, family))}`, ...measured });
  console.log(name, measured.scrollWidth, "/", measured.visible, measured.fits ? "fits" : "scrolls", measured.lang);
  await context.close();
}
writeFileSync(`${out}/measurements.json`, JSON.stringify(results, null, 2));
await browser.close();
