import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { RecordRow } from "@/components/business-app/transacciones/transacciones-model";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
let cleanup = async () => {};
afterEach(async () => { await cleanup(); document.body.innerHTML = ""; });

async function render(node: ReactNode) {
  await cleanup();
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } }, interpolation: { escapeValue: false } });
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const value = { chosen: { space_id: "s", capabilities: ["read"] } } as unknown as BusinessContextValue;
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}>{node}</BusinessContext.Provider></I18nextProvider>));
  cleanup = async () => { await act(async () => root.unmount()); };
  return host.firstElementChild as HTMLElement;
}

const badge = async (ready: boolean) => {
  const RecordStatusCell = (await import("@/components/business-app/transacciones/RecordStatusCell")).default;
  const cell = await render(<RecordStatusCell row={{ id: "r", report: { ready, missing: ["missing_rnc"], stage: "needs_review" } } as unknown as RecordRow} />);
  return cell.querySelector<HTMLElement>("[data-record-status]") ?? cell;
};

test("Registros' Estado chip renders the classes and width it had before the chip was shared", async () => {
  // The class names and width #2197 rendered: the pill, the fixed-width chip and the palette tone.
  const chip = await badge(false);
  assert.equal(chip.textContent, "Falta 1 dato");
  assert.equal(chip.className, "workflow stage fiscal");
  assert.equal(chip.getAttribute("style"), "width: 120px;");
});

test("the shared chip draws Estado exactly as the badge does, tone for tone", async () => {
  const { StatusChip } = await import("@/components/business-app/foundation/StatusChip");
  for (const [ready, tone] of [[false, "warning"]] as const) {
    const fromBadge = await badge(ready);
    const [className, style] = [fromBadge.className, fromBadge.getAttribute("style")];
    const shared = await render(<StatusChip tone={tone}>x</StatusChip>);
    assert.equal(shared.className, className);
    assert.equal(shared.getAttribute("style"), style);
  }
});

test("the chip's shape, size and type are the rules Estado had", () => {
  const css = readFileSync(resolve(import.meta.dir, "../components/business-app/foundation/status-chip.module.css"), "utf8");
  const rule = (selector: string) => css.match(new RegExp(`(?:^|\\n)${selector.replace(/[.()]/g, "\\$&")} \\{([^}]*)\\}`))?.[1]?.trim();
  assert.equal(rule(".workflow"), "display:inline-flex; align-items:center; max-width:100%; border-radius:999px; padding:3px 8px; color:var(--workflow-ink,#422f29); font-size:12px; font-weight:500; line-height:1.4; white-space:nowrap;");
  assert.equal(rule(":global(.dark) .workflow"), "color:var(--workflow-ink,#f8eee7);");
  assert.equal(rule(".stage"), "display:inline-block; box-sizing:border-box; text-align:center; overflow:hidden; text-overflow:ellipsis; vertical-align:middle;");
  const cells = readFileSync(resolve(import.meta.dir, "../components/business-app/transacciones/transacciones-cells.module.css"), "utf8");
  assert.doesNotMatch(cells, /\.workflow|\.stage/, "one home for the chip's rules");
});
