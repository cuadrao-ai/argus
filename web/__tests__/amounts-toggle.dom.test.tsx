import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { AmountsToggle } from "@/components/business-app/foundation/AmountsToggle";
import { TOOLTIP_DELAY_MS } from "@/components/ui/Tooltip";
import { setAmountsHidden } from "@/lib/amounts-hidden";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

test("the eye is a toggle with one name: pressing it flips aria-pressed, and its tooltip says the same name in both states", async () => {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { en: { translation: english }, "es-419": { translation: spanish } } });
  setAmountsHidden(false);
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const eye = () => host.querySelector<HTMLButtonElement>('[data-testid="amounts-toggle"]')!;
  const tooltip = async () => {
    await act(async () => { eye().dispatchEvent(new MouseEvent("mouseover", { bubbles: true })); });
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, TOOLTIP_DELAY_MS + 20)); });
    const text = document.querySelector('[role="tooltip"]')?.textContent ?? null;
    await act(async () => { eye().dispatchEvent(new MouseEvent("mouseout", { bubbles: true })); });
    return text;
  };
  try {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><AmountsToggle /></I18nextProvider>));
    assert.equal(eye().getAttribute("aria-label"), "Ocultar montos");
    assert.equal(eye().getAttribute("aria-pressed"), "false");
    assert.equal(await tooltip(), "Ocultar montos");
    assert.ok(eye().querySelector("svg.lucide-eye"), "an open eye while amounts show");
    await act(async () => eye().click());
    assert.ok(eye().querySelector("svg.lucide-eye-closed"), "a closed eye while they are hidden");
    assert.equal(eye().getAttribute("aria-pressed"), "true");
    assert.equal(eye().getAttribute("aria-label"), "Ocultar montos", "a toggle keeps its name; aria-pressed carries the state");
    assert.equal(await tooltip(), "Ocultar montos", "the tooltip never contradicts the name a screen reader hears");
  } finally {
    setAmountsHidden(false);
    await act(async () => root.unmount());
    host.remove();
  }
});
