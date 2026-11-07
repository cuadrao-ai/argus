import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";
import tailwindcss from "@tailwindcss/postcss";
import { transform } from "lightningcss";
import postcss from "postcss";

let css: string;
let markup: string;

test.beforeAll(async () => {
  const globalsPath = resolve("app/globals.css");
  const overviewPath = resolve("components/business-app/transacciones/records-overview-preview.module.css");
  const globals = await postcss([tailwindcss()]).process(await readFile(globalsPath, "utf8"), { from: globalsPath });
  const overview = transform({ filename: overviewPath, code: await readFile(overviewPath), cssModules: true });
  const names = overview.exports;
  if (!names) throw new Error("Overview CSS module did not export its classes");
  css = `${globals.css}\n${overview.code.toString()}`;
  const families = ["Compras", "Ventas"].map((family) => `<div class="${names.family.name}"><span class="${names.familyLabel.name}">${family}</span><div class="${names.moneyValue.name}"><span class="cuadrao-amount ${names.amount.name}"><span aria-hidden="true">1,234<sup>.56</sup></span><span class="sr-only">DOP 1,234.56</span></span></div></div>`).join("");
  markup = `<main class="business-foundation" data-registros-summary-v2="true"><div class="${names.cards.name}">${["total", "itbis", "quantity", "goods", "services", "fiscal"].map((metric) => `<div class="${names.card.name} ${names[metric].name}" data-overview-card="${metric}">${metric === "quantity" || metric === "fiscal" ? `<span class="${names.count.name}">12</span>` : families}</div>`).join("")}</div></main>`;
});

for (const theme of ["light", "dark"]) {
  for (const reducedMotion of ["reduce", "no-preference"] as const) {
    test(`amounts hide immediately in ${theme} with motion ${reducedMotion}`, async ({ page }) => {
      await page.emulateMedia({ reducedMotion });
      await page.setContent(`<html class="${theme}"><head><style>${css}</style></head><body>${markup}</body></html>`);
      const result = await page.evaluate(() => {
        const amounts = [...document.querySelectorAll<HTMLElement>(".cuadrao-amount, .cuadrao-amount *")];
        const visible = amounts.map((node) => getComputedStyle(node).color);
        document.documentElement.dataset.amountsHidden = "true";
        const hidden = amounts.map((node) => {
          const style = getComputedStyle(node);
          return { color: style.color, shadow: style.textShadow, selection: style.userSelect, transitions: node.getAnimations().filter((animation) => animation instanceof CSSTransition).length };
        });
        delete document.documentElement.dataset.amountsHidden;
        return { visible, hidden, restored: amounts.map((node) => getComputedStyle(node).color) };
      });
      expect(result.hidden).toHaveLength(32);
      for (const amount of result.hidden) {
        expect(amount.color).toBe("rgba(0, 0, 0, 0)");
        expect(amount.shadow).not.toBe("none");
        expect(amount.selection).toBe("none");
        expect(amount.transitions).toBe(0);
      }
      expect(result.visible.every((color) => color !== "rgba(0, 0, 0, 0)")).toBe(true);
      expect(result.restored).toEqual(result.visible);
    });
  }
}
