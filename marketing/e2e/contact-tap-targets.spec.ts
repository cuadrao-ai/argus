import { expect, test, type Page } from "@playwright/test";

const SENTENCE = "Me interesa una demostración de Cuadrao.";

const DESKTOP = {
  h1: { dx: -668, dy: -63.39, w: 545, h: 136.94 },
  pilot: { dx: 0, dy: 630.22, w: 479, h: 44 },
  send: { dx: 0, dy: 694.22, w: 479, h: 55.59 },
  mailto: { dx: -668, dy: 312.11, w: 144, h: 44 },
  footer: { dx: -716, dy: 963.98, w: 1280, h: 737.39 },
};

async function box(page: Page, selector: string) {
  return page.locator(selector).evaluate((node) => {
    const rect = node.getBoundingClientRect();
    return { x: rect.x, y: rect.y, w: rect.width, h: rect.height };
  });
}

function overlaps(a: { x: number; y: number; w: number; h: number }, b: { x: number; y: number; w: number; h: number }) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

test.describe("contact form tap targets", () => {
  test.beforeEach(({}, info) => {
    test.skip(info.project.name !== "desktop", "viewports are set inside the test");
  });

  test("phone targets are at least 44px and the consent label toggles the checkbox", async ({ page }) => {
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 1400 });
      await page.goto("/contacto");
      const pilot = page.locator("label:has(input[name=pilot])");
      const checkbox = page.locator("input[name=pilot]");
      const link = page.locator("#contact-privacy a");
      const pilotBox = await box(page, "label:has(input[name=pilot])");
      const linkBox = await box(page, "#contact-privacy a");
      const checkBox = await box(page, "input[name=pilot]");
      expect(pilotBox.w).toBeGreaterThanOrEqual(44);
      expect(pilotBox.h).toBeGreaterThanOrEqual(44);
      expect(linkBox.w).toBeGreaterThanOrEqual(44);
      expect(linkBox.h).toBeGreaterThanOrEqual(44);
      expect(checkBox.w).toBeCloseTo(18, 0);
      expect(checkBox.h).toBeCloseTo(18, 0);
      await expect(link).toHaveCSS("font-size", "12px");

      const short = await page.evaluate(() => {
        const nodes = [...document.querySelectorAll("main a[href], main button, main input, main textarea")];
        return nodes.flatMap((node) => {
          if (node.closest("[aria-hidden='true']")) return [];
          if (node.getAttribute("name") === "pilot") return [];
          const rect = node.getBoundingClientRect();
          if (rect.width === 0 || rect.height === 0) return [];
          if (rect.width >= 44 && rect.height >= 44) return [];
          const label = (node.getAttribute("aria-label") || node.textContent || node.getAttribute("name") || "").trim().replace(/\s+/g, " ").slice(0, 40);
          return [`${node.tagName} ${label} ${rect.width.toFixed(1)}x${rect.height.toFixed(1)}`];
        });
      });
      expect(short).toEqual([]);

      await checkbox.scrollIntoViewIfNeeded();
      const hit = await checkbox.evaluate((node) => {
        const rect = node.getBoundingClientRect();
        const cx = rect.x + rect.width / 2;
        const cy = rect.y + rect.height / 2;
        return [[-21, -21], [21, -21], [-21, 21], [21, 21]].every(([dx, dy]) => {
          const target = document.elementFromPoint(cx + dx, cy + dy);
          return target?.closest("label") === node.parentElement;
        });
      });
      expect(hit).toBe(true);

      const wrapped = await pilot.locator("span").evaluate((node) => {
        const style = getComputedStyle(node);
        const line = Number.parseFloat(style.lineHeight);
        return {
          text: node.textContent,
          lines: Math.round(node.getBoundingClientRect().height / line),
          scrollWidth: node.scrollWidth,
          clientWidth: node.clientWidth,
          scrollHeight: node.scrollHeight,
          clientHeight: node.clientHeight,
          wordBreak: style.wordBreak,
          overflow: style.overflow,
        };
      });
      expect(wrapped.text).toBe(SENTENCE);
      expect(wrapped.scrollWidth).toBeLessThanOrEqual(wrapped.clientWidth + 1);
      expect(wrapped.scrollHeight).toBeLessThanOrEqual(wrapped.clientHeight + 1);
      expect(wrapped.wordBreak).not.toBe("break-all");
      expect(wrapped.overflow).not.toBe("hidden");
      if (width === 320) expect(wrapped.lines).toBeGreaterThan(1);

      const send = await box(page, "main button[type=submit]");
      expect(overlaps(linkBox, send)).toBe(false);
      expect(overlaps(linkBox, pilotBox)).toBe(false);
      expect(linkBox.y - (send.y + send.h)).toBeGreaterThanOrEqual(16);

      await expect(checkbox).not.toBeChecked();
      await pilot.locator("span").click();
      await expect(checkbox).toBeChecked();
    }
  });

  test("desktop neighbours stay put and every link shows the green focus ring", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/contacto");
    const name = await box(page, "#contact-name");
    const current = await page.evaluate(() => {
      const nameRect = document.querySelector("#contact-name")!.getBoundingClientRect();
      const item = (selector: string) => {
        const rect = document.querySelector(selector)!.getBoundingClientRect();
        return {
          dx: +(rect.x - nameRect.x).toFixed(2),
          dy: +(rect.y - nameRect.y).toFixed(2),
          w: +rect.width.toFixed(2),
          h: +rect.height.toFixed(2),
        };
      };
      return {
        h1: item("main h1"),
        pilot: item("label:has(input[name=pilot])"),
        send: item("main button[type=submit]"),
        mailto: item("a[href^='mailto:']"),
        footer: item("footer"),
      };
    });
    for (const key of Object.keys(DESKTOP) as (keyof typeof DESKTOP)[]) {
      for (const field of ["dx", "dy", "w", "h"] as const) {
        expect(Math.abs(current[key][field] - DESKTOP[key][field])).toBeLessThanOrEqual(1);
      }
    }
    expect(name.w).toBeGreaterThan(44);

    const link = await box(page, "#contact-privacy a");
    expect(link.w).toBeGreaterThanOrEqual(44);
    expect(link.h).toBeGreaterThanOrEqual(44);
    const lines = await page.locator("label:has(input[name=pilot]) span").evaluate((node) => {
      const line = Number.parseFloat(getComputedStyle(node).lineHeight);
      return Math.round(node.getBoundingClientRect().height / line);
    });
    expect(lines).toBe(1);

    const links = page.locator("a[href]");
    const count = await links.count();
    let checked = 0;
    for (let index = 0; index < count; index += 1) {
      const link = links.nth(index);
      if (!(await link.isVisible())) continue;
      await link.evaluate((node: HTMLElement) => node.focus({ focusVisible: true }));
      await expect(link).toHaveCSS("outline-width", "2px");
      await expect(link).toHaveCSS("outline-style", "solid");
      await expect(link).toHaveCSS("outline-color", "rgb(47, 90, 73)");
      checked += 1;
    }
    expect(checked).toBeGreaterThan(3);
  });
});
