import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";
import { FOCUS_RING } from "@/components/business-app/foundation/presentation";

const WEB = resolve(import.meta.dir, "..");
const source = (path: string) => readFileSync(resolve(WEB, path), "utf8");
const rule = (css: string, selector: string) => css.match(new RegExp(`(?:^|\\n)${selector.replace(/[.()[\]"=]/g, "\\$&")} \\{([^}]*)\\}`))?.[1] ?? "";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function render(node: ReactNode) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}>{node}</I18nextProvider>));
  return { host, act, close: () => act(async () => { root.unmount(); host.remove(); }) };
}

test("the toast close button wears the one focus ring, and each kind's stripe follows the theme", async () => {
  const { clearToasts, showToast } = await import("@/components/business-app/foundation/toasts");
  const { ToastViewport } = await import("@/components/business-app/foundation/ToastViewport");
  clearToasts();
  const page = await render(<ToastViewport />);
  await page.act(async () => { showToast({ kind: "success", text: "Listo." }); });
  const success = page.host.querySelector('[data-kind="success"]') as HTMLElement;
  const close = success.querySelector('button[aria-label="Cerrar"]') as HTMLElement;
  assert.ok(close.className.includes(FOCUS_RING), close.className);
  assert.doesNotMatch(close.className, /outline-\[#/);
  assert.equal(success.style.borderLeftColor, "", "no light-only inline stripe");
  assert.ok(success.classList.contains("border-l-[var(--cuadrao-green)]"));
  assert.ok(success.classList.contains("dark:border-l-[var(--cuadrao-green)]"), "the dark hairline must not win the stripe");
  await page.act(async () => { showToast({ kind: "info", text: "Copiado." }); });
  const info = page.host.querySelector('[data-kind="info"]') as HTMLElement;
  assert.equal(info.style.borderLeftColor, "");
  assert.ok(info.classList.contains("border-l-[#56635e]"));
  assert.ok(info.classList.contains("dark:border-l-white/70"));
  await page.act(async () => { clearToasts(); });
  await page.close();
});

test("the small switch draws its off track with the segment border token", async () => {
  const { SwitchIndicator } = await import("@/components/ui/Switch");
  const page = await render(<><SwitchIndicator on={false} pending={false} /><SwitchIndicator on pending={false} /></>);
  const off = page.host.querySelector('[data-switch-indicator="off"]') as HTMLElement;
  const on = page.host.querySelector('[data-switch-indicator="on"]') as HTMLElement;
  assert.ok(off.classList.contains("bg-[var(--segment-thumb-border)]"), off.className);
  // A white knob needs 3:1 on the dark off track too: #7d8a84 gives 4.4:1 to the dark menu and 3.6:1 to the knob.
  assert.ok(off.classList.contains("dark:bg-[#7d8a84]"), off.className);
  assert.doesNotMatch(off.className, /bg-\[#c9cec9\]|bg-white\/20/);
  assert.ok(on.classList.contains("bg-[#2f5a49]") && on.classList.contains("dark:bg-[#8fcbb0]"), "on keeps its green");
  assert.ok(!on.classList.contains("bg-[var(--segment-thumb-border)]"));
  await page.close();
});

test("the dossier's bordered controls, compare switch and neutral chip read tokens that exist in both themes", () => {
  const dossier = source("components/business-app/dossier/dossier.module.css");
  for (const selector of [".act", ".currency"]) assert.match(rule(dossier, selector), /border:1px solid var\(--segment-thumb-border\);/, selector);
  assert.match(rule(dossier, ".actSave"), /border-color:var\(--d-green\)/, "save keeps its green edge");
  assert.match(rule(dossier, '.currency[data-missing="true"]'), /border-color:var\(--d-warn-bg\)/, "a missing currency keeps its warning edge");

  const compare = source("components/business-app/dossier/compare.module.css");
  assert.doesNotMatch(compare, /\.switch/, "the shared segmented control draws the switch, with its own tokens");
  assert.match(rule(compare, ".sides"), /background:var\(--d-card\);/, "its backing is the card's token in both themes");

  const chip = source("components/business-app/foundation/status-chip.module.css");
  assert.match(rule(chip, ".neutral"), /--workflow-ink:color-mix\(in srgb,var\(--fg\) 66%,transparent\);/);
  assert.doesNotMatch(chip, /var\(--muted\)/, "--muted is only set inside Bandeja");
});

test("every dossier focus ring in these files is the shared one, never a light-only literal", async () => {
  const files = [
    "components/business-app/ReceiptReviewFrame.tsx",
    "components/business-app/ReceiptFieldControls.tsx",
    "components/business-app/ReceiptImageZoom.tsx",
    "components/business-app/foundation/ToastViewport.tsx",
    "components/ui/AdaptivePanel.tsx",
  ];
  for (const file of files) {
    const text = source(file);
    assert.doesNotMatch(text, /outline-\[#2f5a49\]/, file);
    assert.match(text, /\bFOCUS_RING\b/, file);
  }
  const { REVIEW_INPUT_CLASS } = await import("@/components/business-app/ReceiptFieldControls");
  assert.ok(REVIEW_INPUT_CLASS.includes(FOCUS_RING));
});

test("a sheet holds a caller's summary slot without nesting it in a paragraph", async () => {
  const { renderToStaticMarkup } = await import("react-dom/server");
  const { BottomSheetSurface } = await import("@/components/ui/BottomSheet");
  const html = renderToStaticMarkup(
    <BottomSheetSurface isOpen onClose={() => undefined} title="Detalle" closeLabel="Cerrar" description={<div data-header-slot="" />}>
      <span>cuerpo</span>
    </BottomSheetSurface>,
  );
  const describedBy = html.match(/aria-describedby="([^"]+)"/)?.[1];
  assert.ok(describedBy, "the dialog still names its description");
  assert.match(html, new RegExp(`<div id="${describedBy}"[^>]*><div data-header-slot=""></div></div>`));
});
