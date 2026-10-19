import path from "node:path";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "./support/breakpoint-fixture";

type Feed = "data" | "empty" | "error" | "slow" | "late";

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "tablet", width: 800, height: 1024 },
  { name: "mobile", width: 390, height: 844 },
] as const;

const SPACING_SCALE = new Set([0, 4, 8, 12, 16, 24, 32, 48, 64]);

const SHOTS = "test-results/design-novedades";
const axePath = path.join(process.cwd(), "node_modules/axe-core/axe.min.js");

test.skip(process.env.NEXT_PUBLIC_BUSINESS_PILOT_ENABLED !== "true", "/biz needs the Business pilot server");

async function installBusiness(page: Page, feed: Feed) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  await page.route("**/api/v1/business/**", async (route) => {
    const url = new URL(route.request().url());
    const parts = url.pathname.split("/business/")[1].split("/");
    if (parts[0] === "consent") return fulfillAcceptedBusinessConsent(route);
    try {
      let json: unknown;
      if (parts[0] === "updates") {
        if (feed === "error") return route.fulfill({ status: 503, json: { code: "unavailable" } });
        if (feed === "slow") await new Promise((resolve) => setTimeout(resolve, 60_000));
        if (feed === "late") await new Promise((resolve) => setTimeout(resolve, 1_500));
        json = { items: feed === "empty" ? [] : await source.updates() };
      } else if (parts[0] === "space") json = await source.ensureSpace("es-419");
      else if (parts[0] === "spaces") json = { spaces: await source.spaces() };
      else if (parts[0] === "workspace") json = await source.workspace();
      else if (parts[0] === "overview") json = await source.overview(url.searchParams.get("from") ?? "2026-10-01", url.searchParams.get("to") ?? "2026-10-31");
      else if (parts[0] === "receipt-reading") json = { enabled: false, available: true, can_change: true, disclosure: "Permiso", disclosure_token: "a".repeat(64), route: { gateway: "synthetic", interpretation: [], reply: [] }, consented_at: null, revoked_at: null };
      else if (parts[0] === "receipts" && parts.length === 1) json = await source.receiptPage!(url.searchParams.get("view") === "all" ? "all" : "inbox");
      else if (parts[0] === "receipts" && parts.length === 2) json = await source.receipt(parts[1]);
      else if (parts[0] === "email" && parts.length === 1) json = await source.emailIntake();
      else if (["captures", "expenses"].includes(parts[0]) || parts.join("/") === "email/deliveries") json = { items: [] };
      else return route.fulfill({ status: 404, json: { code: "fixture_only" } });
      return route.fulfill({ json });
    } catch (error) {
      const failure = error as { status?: number; code?: string };
      return route.fulfill({ status: failure.status ?? 500, json: { code: failure.code ?? "fixture_failure" } });
    }
  });
}

async function openNovedades(page: Page) {
  await page.goto("/biz?view=updates");
  await expect(page.getByRole("heading", { level: 1, name: "Novedades" })).toBeVisible();
}

const rows = (page: Page) => page.getByTestId("business-update-row");

async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

async function expectNoAxeViolations(page: Page) {
  await page.addScriptTag({ path: axePath });
  const violations = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (context: unknown, options: unknown) => Promise<{ violations: { id: string; nodes: { target: string[] }[] }[] }> } }).axe;
    const result = await axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] } });
    return result.violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).join(", ")}`);
  });
  expect(violations).toEqual([]);
}

/** Every padding, margin and gap in the screen is on the 4px scale, and every radius is 12, 20 or a pill. */
async function expectLockedSpacing(page: Page) {
  const offScale = await page.locator("section:has(> div > h1)").evaluate((section, scale) => {
    const allowed = new Set(scale);
    const bad: string[] = [];
    for (const element of [section, ...section.querySelectorAll<HTMLElement>("*:not(.sr-only)")]) {
      const css = getComputedStyle(element);
      for (const key of ["paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "marginTop", "marginRight", "marginBottom", "marginLeft", "rowGap", "columnGap"] as const) {
        const value = Number.parseFloat(css[key]);
        if (Number.isFinite(value) && !allowed.has(value)) bad.push(`${element.tagName}.${element.className.toString().slice(0, 40)} ${key}=${css[key]}`);
      }
      const radius = Number.parseFloat(css.borderTopLeftRadius);
      if (radius && radius !== 12 && radius !== 20 && radius < 999) bad.push(`${element.tagName}.radius=${css.borderTopLeftRadius}`);
    }
    return bad;
  }, [...SPACING_SCALE]);
  expect(offScale).toEqual([]);
}

/** Contrast of an element's text against the first opaque background behind it. */
async function textContrast(locator: Locator) {
  return locator.evaluate((element) => {
    const rgb = (value: string) => (value.match(/[\d.]+/g) ?? []).map(Number);
    const background = (start: Element | null): number[] => {
      for (let node = start; node; node = node.parentElement) {
        const [r, g, b, a = 1] = rgb(getComputedStyle(node).backgroundColor);
        if (a === 1 && getComputedStyle(node).backgroundColor !== "rgba(0, 0, 0, 0)") return [r, g, b];
      }
      return [255, 255, 255];
    };
    const luminance = ([r, g, b]: number[]) => {
      const channel = (value: number) => {
        const c = value / 255;
        return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
      };
      return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
    };
    const fore = luminance(rgb(getComputedStyle(element).color));
    const back = luminance(background(element));
    return (Math.max(fore, back) + 0.05) / (Math.min(fore, back) + 0.05);
  });
}

for (const viewport of VIEWPORTS) {
  test.describe(`Novedades ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("rows: one per receipt, a full-row link with pill, supplier, sentence and readable time", async ({ page }) => {
      await installBusiness(page, "data");
      await openNovedades(page);
      await expect(rows(page).first()).toBeVisible();
      const hrefs = await rows(page).locator("a").evaluateAll((links) => links.map((link) => link.getAttribute("href")));
      expect(hrefs.length).toBeGreaterThan(3);
      expect(new Set(hrefs).size).toBe(hrefs.length);
      for (const row of await rows(page).all()) {
        const link = row.locator("a");
        const box = (await link.boundingBox())!;
        expect(box.height).toBeGreaterThanOrEqual(64);
        expect((await row.boundingBox())!.width - box.width).toBeLessThanOrEqual(1);
        await expect(link.getByTestId("status-pill")).toHaveCount(1);
        const pillBox = (await link.getByTestId("status-pill").boundingBox())!;
        expect(pillBox.height).toBeGreaterThanOrEqual(24);
        expect(pillBox.height).toBeLessThanOrEqual(25);
        const clipped = await link.evaluate((element) => [...element.querySelectorAll<HTMLElement>("*")].filter((child) => child.scrollWidth > child.clientWidth + 1 && getComputedStyle(child).textOverflow !== "ellipsis").map((child) => child.outerHTML.slice(0, 80)));
        expect(clipped).toEqual([]);
        await expect(link.locator(".lucide-circle-dashed")).toHaveCount(0);
        const time = link.locator("time");
        expect(Number.parseFloat(await time.evaluate((element) => getComputedStyle(element).fontSize))).toBeGreaterThanOrEqual(12);
        expect(await textContrast(time)).toBeGreaterThanOrEqual(4.5);
        const name = link.locator(":scope > span").nth(1);
        expect(await name.evaluate((element) => getComputedStyle(element).fontFamily)).toMatch(/^"?inter/i);
        const sentence = link.locator(":scope > span").nth(2);
        expect(await textContrast(sentence)).toBeGreaterThanOrEqual(4.5);
        const sentenceBox = (await sentence.boundingBox())!;
        const timeBox = (await time.boundingBox())!;
        if (viewport.width >= 1024) expect(sentenceBox.height).toBeLessThanOrEqual(19);
        if (viewport.width < 720) expect(timeBox.y).toBeGreaterThanOrEqual(sentenceBox.y + sentenceBox.height - 1);
      }
      await noHorizontalScroll(page);
    });

    test("tokens: cream canvas, flat white card, Space Grotesk 500 heading, 4px spacing, 12/20/pill radii", async ({ page }) => {
      await installBusiness(page, "data");
      await openNovedades(page);
      await expect(rows(page).first()).toBeVisible();
      expect(await page.locator(".business-foundation").evaluate((element) => getComputedStyle(element).backgroundColor)).toBe("rgb(247, 245, 238)");
      const card = page.getByTestId("business-updates-list");
      const style = await card.evaluate((element) => {
        const css = getComputedStyle(element);
        return { background: css.backgroundColor, border: `${css.borderTopWidth} ${css.borderTopStyle} ${css.borderTopColor}`, radius: css.borderTopLeftRadius, shadow: css.boxShadow };
      });
      expect(style).toEqual({ background: "rgb(255, 254, 250)", border: "1px solid rgb(220, 224, 218)", radius: "20px", shadow: "none" });
      const heading = page.getByRole("heading", { level: 1, name: "Novedades" });
      expect(await heading.evaluate((element) => [getComputedStyle(element).fontFamily, getComputedStyle(element).fontWeight, getComputedStyle(element).fontSize])).toEqual([expect.stringMatching(/^"?space ?grotesk/i), "500", "28px"]);
      await expectLockedSpacing(page);
      if (viewport.width < 720) {
        const box = (await heading.boundingBox())!;
        expect(box.x).toBe(16);
        const cardBox = (await card.boundingBox())!;
        expect(viewport.width - (cardBox.x + cardBox.width)).toBe(16);
      }
    });

    test("focus: a row shows the 2px green ring", async ({ page }) => {
      await installBusiness(page, "data");
      await openNovedades(page);
      const link = rows(page).first().locator("a");
      await link.focus();
      expect(await link.evaluate((element) => { const css = getComputedStyle(element); return `${css.outlineWidth} ${css.outlineStyle} ${css.outlineColor}`; })).toBe("2px solid rgb(47, 90, 73)");
    });

    test("no jump: the heading stays put and skeleton rows hold the rows' height", async ({ page }) => {
      await installBusiness(page, "late");
      await openNovedades(page);
      const heading = page.getByRole("heading", { level: 1, name: "Novedades" });
      const before = (await heading.boundingBox())!;
      await expect(page.getByTestId("business-loading")).toBeVisible();
      const skeletonCard = page.getByTestId("business-loading").locator("[aria-hidden] > div").first();
      const skeleton = (await skeletonCard.boundingBox())!;
      const skeletonRow = (await skeletonCard.locator(":scope > div").first().boundingBox())!;
      await expect(rows(page).first()).toBeVisible();
      expect(await heading.boundingBox()).toEqual(before);
      const list = (await page.getByTestId("business-updates-list").boundingBox())!;
      expect(list.y).toBe(skeleton.y);
      if (viewport.width >= 720) expect(Math.abs((await rows(page).first().boundingBox())!.height - skeletonRow.height)).toBeLessThanOrEqual(4);
    });

    test("loading: heading at once, skeleton rows after 300ms", async ({ page }) => {
      await installBusiness(page, "slow");
      await openNovedades(page);
      await expect(page.getByTestId("business-loading")).toHaveAttribute("data-layout", "updates");
      const skeletonRow = page.getByTestId("business-loading").locator("[aria-hidden] > div > div").first();
      expect((await skeletonRow.boundingBox())!.height).toBeGreaterThanOrEqual(64);
      await expectLockedSpacing(page);
      await noHorizontalScroll(page);
      await expectNoAxeViolations(page);
      await page.screenshot({ path: `${SHOTS}/loading-${viewport.width}.png` });
    });

    test("data state screenshot and axe", async ({ page }) => {
      await installBusiness(page, "data");
      await openNovedades(page);
      await expect(rows(page).first()).toBeVisible();
      await expectNoAxeViolations(page);
      await page.screenshot({ path: `${SHOTS}/data-${viewport.width}.png`, fullPage: true });
    });

    test("empty: one Spanish line in the card", async ({ page }) => {
      await installBusiness(page, "empty");
      await openNovedades(page);
      await expect(page.getByTestId("business-updates-empty")).toHaveText("Nada nuevo. Aquí aparecerán los resultados de tus recibos.");
      await expectLockedSpacing(page);
      await noHorizontalScroll(page);
      await expectNoAxeViolations(page);
      await page.screenshot({ path: `${SHOTS}/empty-${viewport.width}.png` });
    });

    test("error: Spanish line and a 44px Reintentar", async ({ page }) => {
      await installBusiness(page, "error");
      await openNovedades(page);
      const alert = page.getByTestId("business-updates-error");
      await expect(alert).toContainText("No pudimos cargar las novedades.");
      const retry = alert.getByRole("button", { name: "Reintentar" });
      expect((await retry.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      await expectLockedSpacing(page);
      await noHorizontalScroll(page);
      await expectNoAxeViolations(page);
      await page.screenshot({ path: `${SHOTS}/error-${viewport.width}.png` });
    });
  });
}

test.describe("Novedades navigation", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("a row opens the receipt detail", async ({ page }) => {
    await installBusiness(page, "data");
    await openNovedades(page);
    const first = rows(page).first().locator("a");
    const href = await first.getAttribute("href");
    await first.click();
    const receipt = new URLSearchParams(href!.slice(1)).get("receipt");
    await expect(page).toHaveURL((url) => url.searchParams.get("receipt") === receipt);
    await expect(page.getByRole("heading", { name: "Revisar recibo" })).toBeVisible();
  });
});
