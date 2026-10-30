import { expect, test, type Locator } from "@playwright/test";

import { asNewClient, resetMock, uniqueAddress } from "./support";

const ENABLED = {
  backgroundColor: "rgb(47, 90, 73)",
  color: "rgb(255, 255, 255)",
  borderTopColor: "rgb(23, 43, 38)",
  borderTopWidth: "1px",
  borderRadius: "5px",
  cursor: "pointer",
  opacity: "1",
  fontSize: "16px",
  fontWeight: "400",
  minHeight: "54px",
  paddingTop: "14px",
  paddingRight: "22px",
  paddingBottom: "14px",
  paddingLeft: "22px",
};

const UNAVAILABLE = {
  backgroundColor: "rgb(215, 221, 192)",
  color: "rgb(23, 43, 38)",
  borderTopColor: "rgb(86, 99, 94)",
  cursor: "not-allowed",
  opacity: "1",
};

function channel(value: number): number {
  const scaled = value / 255;
  return scaled <= 0.04045 ? scaled / 12.92 : ((scaled + 0.055) / 1.055) ** 2.4;
}

function contrast(foreground: string, background: string): number {
  const luminance = (color: string) => {
    const [red, green, blue] = color.match(/\d+/g)!.map(Number);
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue);
  };
  const lighter = Math.max(luminance(foreground), luminance(background));
  const darker = Math.min(luminance(foreground), luminance(background));
  return (lighter + 0.05) / (darker + 0.05);
}

async function paint(button: Locator) {
  return button.evaluate((node) => {
    const style = getComputedStyle(node);
    return {
      backgroundColor: style.backgroundColor,
      color: style.color,
      borderTopColor: style.borderTopColor,
      borderTopWidth: style.borderTopWidth,
      borderRadius: style.borderRadius,
      cursor: style.cursor,
      opacity: style.opacity,
      fontSize: style.fontSize,
      fontWeight: style.fontWeight,
      minHeight: style.minHeight,
      paddingTop: style.paddingTop,
      paddingRight: style.paddingRight,
      paddingBottom: style.paddingBottom,
      paddingLeft: style.paddingLeft,
    };
  });
}

async function box(locator: Locator) {
  const bounds = await locator.boundingBox();
  expect(bounds).not.toBeNull();
  return bounds!;
}

async function place(locator: Locator) {
  return locator.evaluate((node) => {
    const bounds = node.getBoundingClientRect();
    const element = node as HTMLElement;
    return {
      width: bounds.width,
      height: bounds.height,
      offsetTop: element.offsetTop,
      offsetLeft: element.offsetLeft,
    };
  });
}

test.describe("contact submit unavailable state", () => {
  test.beforeEach(({}, info) => {
    test.skip(info.project.name !== "desktop", "viewports are set inside the test");
  });

  test("before hydration the button is disabled, not-allowed, and a different color", async ({ browser }, info) => {
    for (const width of [390, 1280]) {
      const context = await browser.newContext({
        javaScriptEnabled: false,
        viewport: { width, height: 900 },
      });
      await asNewClient(context, info);
      const page = await context.newPage();
      await page.goto("/contacto");
      const button = page.locator('main button[type="submit"]');
      await expect(button).toBeDisabled();
      await expect(button.locator("svg")).toHaveCount(1);
      const styles = await paint(button);
      expect(styles.cursor).toBe("not-allowed");
      expect(styles.opacity).toBe("1");
      expect(styles.backgroundColor).toBe(UNAVAILABLE.backgroundColor);
      expect(styles.color).toBe(UNAVAILABLE.color);
      expect(styles.backgroundColor).not.toBe(ENABLED.backgroundColor);
      expect(styles.color).not.toBe(ENABLED.color);
      expect(contrast(styles.color, styles.backgroundColor)).toBeCloseTo(10.63, 2);
      const bounds = await box(button);
      expect(bounds.height).toBeGreaterThanOrEqual(44);
      expect(bounds.width).toBeGreaterThan(44);
      const visible = await page.locator("body").innerText();
      expect(visible.toLowerCase()).not.toContain("waitlist");
      expect(visible).not.toContain("Turnstile");
      await context.close();
    }
  });

  test("after hydration the enabled paint stays put, and sending shows Enviando without a second post", async ({
    page,
    request,
  }, info) => {
    await resetMock(request);
    await asNewClient(page.context(), info);
    let posts = 0;
    page.on("request", (incoming) => {
      if (incoming.method() === "POST" && incoming.url().endsWith("/api/inquiries")) posts += 1;
    });
    const hold: { current: Promise<void> } = { current: Promise.resolve() };
    await page.route("**/api/inquiries", async (route) => {
      await hold.current;
      await route.continue();
    });

    for (const width of [390, 1280]) {
      posts = 0;
      let release = () => {};
      hold.current = new Promise<void>((resolve) => {
        release = resolve;
      });
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/contacto");
      const button = page.locator('main button[type="submit"]');
      const privacy = page.locator("#contact-privacy");
      await expect(button).toBeEnabled();
      await expect(button).toHaveText("Enviar mensaje");
      await expect(button.locator("svg")).toHaveCount(1);
      await expect.poll(async () => (await paint(button)).backgroundColor).toBe(ENABLED.backgroundColor);
      const enabled = await paint(button);
      expect(enabled).toEqual(ENABLED);
      const enabledButton = await box(button);
      const enabledPlace = await place(button);
      const enabledPrivacy = await place(privacy);
      expect(enabledButton.height).toBeGreaterThanOrEqual(44);
      expect(enabledButton.width).toBeGreaterThan(44);

      await page.locator("#contact-name").fill("Ana Ruiz");
      await page.locator("#contact-email").fill(uniqueAddress(info));
      await button.click();
      await expect(button).toHaveAttribute("aria-disabled", "true");
      await expect(button).toHaveText("Enviando…");
      await expect(button.locator("svg")).toHaveCount(0);
      await expect.poll(async () => (await paint(button)).backgroundColor).toBe(UNAVAILABLE.backgroundColor);
      const sending = await paint(button);
      expect(sending.backgroundColor).toBe(UNAVAILABLE.backgroundColor);
      expect(sending.color).toBe(UNAVAILABLE.color);
      expect(sending.borderTopColor).toBe(UNAVAILABLE.borderTopColor);
      expect(sending.cursor).toBe("not-allowed");
      expect(sending.opacity).toBe("1");
      expect(contrast(sending.color, sending.backgroundColor)).toBeCloseTo(10.63, 2);
      await button.hover();
      const hovered = await paint(button);
      expect(hovered.backgroundColor).toBe(UNAVAILABLE.backgroundColor);
      expect(hovered.color).toBe(UNAVAILABLE.color);
      expect(await place(button)).toEqual(enabledPlace);
      expect(await place(privacy)).toEqual(enabledPrivacy);
      await button.click({ force: true });
      expect(posts).toBe(1);

      const done = page.waitForResponse((response) => response.url().endsWith("/api/inquiries"));
      release();
      await done;
    }
  });
});
