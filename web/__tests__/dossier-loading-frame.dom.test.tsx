import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";
import type { BusinessContextValue, BusinessPanelState } from "@/components/business-app/BusinessWorkspace";

// While a record loads, the dossier shows the frame of the Leyendo board: a title bar, the tabs, the three
// cards of label and value bars, and the document pane. Nothing at all before the short delay.
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

type Path = "draft" | "receipt" | "expense";
type Size = "page" | "regular";

const never = () => new Promise<never>(() => undefined);

async function mountLoading(path: Path, size: Size) {
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const es = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { RecordTrayContext } = await import("@/components/business-app/record-tray");
  const { default: Panel } = await import("@/components/business-app/ReceiptReviewPanel");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: es } } });
  const panel: BusinessPanelState = path === "draft" ? { kind: "draft", draftId: "draft-loading" } : path === "receipt" ? { kind: "receipt", receiptId: "receipt-loading" } : { kind: "expense", expenseId: "expense-loading" };
  const context = {
    source: { mode: "live", dossier: never, receipt: never, expense: never, dgiiFields: never, receipts: never },
    reload: () => undefined,
    records: { inbox: [], workspace: null },
    openPanel: () => undefined,
    guardPanel: () => () => undefined,
    panel,
    userId: "synthetic-member",
    chosen: { space_id: "space-loading", role: "owner", permissions: ["read"], capabilities: ["read", "prepare", "approve"] },
    actions: { create: [] },
    revision: 0,
  } as unknown as BusinessContextValue;
  const settled: string[] = [];
  const slots = { footer: document.createElement("div"), summary: document.createElement("div"), headerActions: document.createElement("div") };
  for (const slot of Object.values(slots)) document.body.appendChild(slot);
  function Tray({ children }: { children: ReactNode }) {
    const [title, setTitle] = useState<ReactNode>(null);
    return <RecordTrayContext.Provider value={{ ...slots, setTitle, settleList: (list) => settled.push(list), narrow: false, toggleNarrow: () => undefined }}>
      <h2 data-testid="tray-title">{title}</h2>
      {children}
    </RecordTrayContext.Provider>;
  }
  const target = path === "draft" ? { kind: "draft" as const, id: "draft-loading" } : path === "receipt" ? { kind: "receipt" as const, id: "receipt-loading" } : { kind: "expense" as const, id: "expense-loading" };
  const tree = <I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Panel target={target} /></BusinessContext.Provider></I18nextProvider>;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(size === "page" ? tree : <Tray>{tree}</Tray>));
  const wait = (milliseconds: number) => act(async () => { await new Promise((resolve) => setTimeout(resolve, milliseconds)); });
  const close = async () => { await act(async () => root.unmount()); document.body.innerHTML = ""; };
  return { wait, close, settled };
}

const frame = () => document.body.querySelector<HTMLElement>('[data-testid="business-record-review"]');
const tabs = () => [...document.body.querySelectorAll('[role="tab"]')].map((tab) => tab.textContent);
const visible = (node: Element | null) => {
  const clone = node?.cloneNode(true) as HTMLElement | undefined;
  clone?.querySelectorAll(".sr-only").forEach((item) => item.remove());
  return clone?.textContent ?? "";
};

describe("a dossier that is loading", () => {
  for (const path of ["draft", "receipt", "expense"] as const) {
    for (const size of ["page", "regular"] as const) {
      test(`the ${path} path in the ${size} size shows the Leyendo frame after the delay, never the detail skeleton`, async () => {
        const page = await mountLoading(path, size);
        try {
          assert.equal(frame(), null, "a fast load shows nothing");
          await page.wait(250);
          assert.equal(frame(), null, "still nothing just before the delay");
          await page.wait(80);
          const shown = frame();
          assert.ok(shown, "the dossier frame after the delay");

          assert.deepEqual(tabs(), size === "page" ? ["General", "Documento", "Detalles", "Historial"] : ["General", "Detalles", "Historial"]);
          const general = shown.querySelector('[data-tab-panel="general"]');
          const cards = [...(general?.querySelectorAll("section") ?? [])];
          assert.deepEqual(cards.map((card) => card.querySelector("h3")?.textContent), ["Comprobante", "Reporte 606", "Montos"]);
          for (const card of cards) {
            const rows = [...card.querySelectorAll("li")];
            assert.ok(rows.length > 0, "each card has rows");
            for (const row of rows) assert.equal(row.querySelectorAll("span").length, 2, "a label bar and a value bar");
          }

          const title = size === "page" ? document.body.querySelector("#receipt-review-title") : document.body.querySelector('[data-testid="tray-title"]');
          assert.ok(title?.querySelector('[data-testid="dossier-title-bar"]'), "the title is a bar");
          assert.equal(visible(title), "", "no invented title");
          assert.equal(visible(general), "ComprobanteReporte 606Montos", "only the card titles are words");
          assert.deepEqual(page.settled, [], "a loading frame never settles the list");

          const pane = document.body.querySelector('[data-testid="receipt-review-source"]');
          assert.ok(pane, "the document pane is there");
          if (size === "page") assert.ok(pane.closest('[data-tab-panel="documento"]'), "narrow: the pane is the Documento tab");
          else assert.equal(pane.closest("[data-tab-panel]"), null, "wide: the pane stands beside the tabs");

          assert.equal(document.body.querySelector('[data-testid="dossier-status"]'), null, "no status chip");
          assert.equal(document.body.querySelector('[data-testid="receipt-review-footer"]'), null, "no footer");
          assert.equal(document.body.querySelector('[data-layout="detail"]'), null, "never the old detail skeleton");
          assert.equal(document.body.querySelectorAll('[data-tab-panel] button, [data-tab-panel] input').length, 0, "nothing to press inside the tabs");
        } finally {
          await page.close();
        }
      });
    }
  }

  test("reduced motion stills every bar: the shimmer runs only under no-preference", async () => {
    const page = await mountLoading("receipt", "regular");
    try {
      await page.wait(330);
      const styles = (await import("@/components/business-app/receipt-reading.module.css")).default as Record<string, string>;
      const bars = [...document.body.querySelectorAll('[data-tab-panel="general"] li span'), document.body.querySelector('[data-testid="dossier-title-bar"]')];
      assert.ok(bars.length > 2);
      for (const bar of bars) assert.ok(bar?.classList.contains(styles.shimmer), "every loading bar takes the shimmer class");
      const css = readFileSync(join(import.meta.dir, "../components/business-app/receipt-reading.module.css"), "utf8");
      const open = css.indexOf("@media (prefers-reduced-motion: no-preference)");
      assert.ok(open >= 0);
      let depth = 0;
      let end = css.indexOf("{", open);
      for (; end < css.length; end += 1) {
        if (css[end] === "{") depth += 1;
        if (css[end] === "}" && --depth === 0) break;
      }
      assert.match(css.slice(open, end), /\.shimmer\s*\{[^}]*animation:\s*shimmer/);
      assert.doesNotMatch(css.slice(0, open) + css.slice(end + 1), /animation:\s*shimmer/, "no shimmer animation outside no-preference");
    } finally {
      await page.close();
    }
  });
});
