import { expect, test, type Locator, type Page } from "@playwright/test";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

const MINIMUM = 3;

/** The WCAG contrast of one painted colour of `target` against what its ancestors paint under it. */
async function paintContrast(page: Page, target: Locator, property: "background-color" | "outline-color", forced: string[] = []) {
  const cdp = await page.context().newCDPSession(page);
  try {
    await cdp.send("DOM.enable");
    await cdp.send("CSS.enable");
    await target.evaluate((node) => node.setAttribute("data-paint-probe", ""));
    const { root } = await cdp.send("DOM.getDocument", { depth: 0 });
    const { nodeId } = await cdp.send("DOM.querySelector", { nodeId: root.nodeId, selector: "[data-paint-probe]" });
    await cdp.send("CSS.forcePseudoState", { nodeId, forcedPseudoClasses: forced });
    const measured = await target.evaluate((node, name) => {
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 1;
      const context = canvas.getContext("2d", { willReadFrequently: true })!;
      const rgba = (css: string) => {
        context.clearRect(0, 0, 1, 1);
        context.fillStyle = css;
        context.fillRect(0, 0, 1, 1);
        const [r, g, b, a] = context.getImageData(0, 0, 1, 1).data;
        return [r, g, b, a / 255];
      };
      const over = (top: number[], under: number[]) => [0, 1, 2].map((i) => top[i] * top[3] + under[i] * (1 - top[3])).concat(1);
      const ancestors: Element[] = [];
      for (let element = node.parentElement; element; element = element.parentElement) ancestors.push(element);
      let under = [255, 255, 255, 1];
      for (const element of ancestors.reverse()) under = over(rgba(getComputedStyle(element).backgroundColor), under);
      const style = getComputedStyle(node);
      const paint = over(rgba(style.getPropertyValue(name)), under);
      const luminance = (color: number[]) => {
        const [r, g, b] = color.slice(0, 3).map((value) => {
          const channel = value / 255;
          return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
        });
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
      };
      const [light, dark] = [luminance(paint), luminance(under)].sort((a, b) => b - a);
      const css = (color: number[]) => `rgb(${color.slice(0, 3).map(Math.round).join(", ")})`;
      return { paint: css(paint), under: css(under), ratio: (light + 0.05) / (dark + 0.05), outline: `${style.outlineStyle} ${style.outlineWidth}` };
    }, property);
    await cdp.send("CSS.forcePseudoState", { nodeId, forcedPseudoClasses: [] });
    await target.evaluate((node) => node.removeAttribute("data-paint-probe"));
    return measured;
  } finally {
    await cdp.detach();
  }
}

for (const theme of ["light", "dark"] as const) {
  test(`the off switch in Más and the toast close focus ring reach 3:1 in ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.emulateMedia({ reducedMotion: "reduce", colorScheme: theme });
    await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
    await installBreakpointFixture(page, { language: "es-419", theme, emptyChat: true });
    await page.goto(`/dev/business-preview?draft=${dossierFixtureIds.fiscal}`);
    await expect(page.getByTestId("receipt-review-fields")).toBeVisible();

    await page.getByTestId("receipt-more").getByRole("button", { name: "Más", exact: true }).click();
    const sale = page.getByTestId("receipt-mark-sale");
    await expect(sale).toHaveAttribute("aria-checked", "false");
    const track = await paintContrast(page, sale.locator('[data-switch-indicator="off"]'), "background-color");
    expect(track.ratio, `off track ${track.paint} on ${track.under}`).toBeGreaterThanOrEqual(MINIMUM);

    await sale.click();
    const toast = page.getByTestId("toast").first();
    await expect(toast).toBeVisible();
    const ring = await paintContrast(page, toast.getByRole("button", { name: "Cerrar" }), "outline-color", ["focus-visible"]);
    expect(ring.outline, "the ring is drawn").toBe("solid 2px");
    expect(ring.ratio, `focus ring ${ring.paint} on ${ring.under}`).toBeGreaterThanOrEqual(MINIMUM);
    console.log(`${theme}: off track ${track.ratio.toFixed(2)} (${track.paint} on ${track.under}), close ring ${ring.ratio.toFixed(2)} (${ring.paint} on ${ring.under})`);
  });
}
