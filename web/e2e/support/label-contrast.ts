import type { Locator, Page } from "@playwright/test";

export type PointerState = "rest" | "hover" | "focus-visible" | "active";

export type LabelContrast = { state: PointerState; label: string; background: string; ratio: number };

/** The label's WCAG contrast against what is painted under it, with the state forced through the browser's own cascade. */
export async function labelContrast(page: Page, target: Locator, state: PointerState): Promise<LabelContrast> {
  const cdp = await page.context().newCDPSession(page);
  try {
    await cdp.send("DOM.enable");
    await cdp.send("CSS.enable");
    await target.evaluate((node) => {
      if (!document.querySelector("style[data-contrast-probe-style]")) {
        const style = document.createElement("style");
        style.dataset.contrastProbeStyle = "";
        style.textContent = "[data-contrast-probe] { transition: none !important; }";
        document.head.append(style);
      }
      node.setAttribute("data-contrast-probe", "");
    });
    const { root } = await cdp.send("DOM.getDocument", { depth: 0 });
    const { nodeId } = await cdp.send("DOM.querySelector", { nodeId: root.nodeId, selector: "[data-contrast-probe]" });
    await cdp.send("CSS.forcePseudoState", { nodeId, forcedPseudoClasses: state === "rest" ? [] : [state] });
    const measured = await target.evaluate((node) => {
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
      const chain: Element[] = [];
      for (let element: Element | null = node; element; element = element.parentElement) chain.push(element);
      let backdrop = [255, 255, 255, 1];
      for (const element of chain.slice(1).reverse()) backdrop = over(rgba(getComputedStyle(element).backgroundColor), backdrop);
      const style = getComputedStyle(node);
      const opacity = chain.reduce((product, element) => product * Number(getComputedStyle(element).opacity), 1);
      const background = over(rgba(style.backgroundColor), backdrop);
      const label = over(rgba(style.color), background);
      const fade = (color: number[]) => over([...color.slice(0, 3), opacity], backdrop);
      const luminance = (color: number[]) => {
        const [r, g, b] = color.slice(0, 3).map((value) => {
          const channel = value / 255;
          return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
        });
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
      };
      const [light, dark] = [luminance(fade(label)), luminance(fade(background))].sort((a, b) => b - a);
      const css = (color: number[]) => `rgb(${color.slice(0, 3).map(Math.round).join(", ")})`;
      return { label: css(fade(label)), background: css(fade(background)), ratio: (light + 0.05) / (dark + 0.05) };
    });
    await cdp.send("CSS.forcePseudoState", { nodeId, forcedPseudoClasses: [] });
    await target.evaluate((node) => node.removeAttribute("data-contrast-probe"));
    return { state, ...measured };
  } finally {
    await cdp.detach();
  }
}
