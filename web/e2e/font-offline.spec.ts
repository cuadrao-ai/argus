import { expect, test } from "@playwright/test";

const BILINGUAL_SAMPLE =
  "English UI: Backtest your idea. Español: ¿Qué pasó? ¡Sí! Acción, corazón, pingüino, Müller.";

test("renders bilingual text with local canonical font faces", async ({ page }, testInfo) => {
  const fontRequests: string[] = [];
  const unexpectedExternalRequests: string[] = [];
  const consoleWarnings: string[] = [];

  page.on("request", (request) => {
    const url = new URL(request.url());
    const isKnownExternalFontService = /(^|\.)fonts\.(googleapis|gstatic)\.com$/.test(
      url.hostname,
    );
    if (request.resourceType() === "font" || isKnownExternalFontService) {
      fontRequests.push(request.url());
      if (url.hostname !== "127.0.0.1" && url.hostname !== "localhost") {
        unexpectedExternalRequests.push(request.url());
      }
    }
  });
  page.on("console", (message) => {
    if (message.type() === "warning" || message.type() === "error") {
      consoleWarnings.push(message.text());
    }
  });

  await page.goto("/auth/forgot-password", { waitUntil: "networkidle" });
  await expect(page.locator("h1").first()).toBeVisible();

  const typography = await page.evaluate(async (sample) => {
    const heading = document.querySelector("h1");
    if (!heading) throw new Error("representative display heading is missing");

    const bodyFamily = getComputedStyle(document.body).fontFamily;
    const displayFamily = getComputedStyle(heading).fontFamily;
    const bilingual = document.createElement("p");
    bilingual.textContent = sample;
    bilingual.style.fontFamily = bodyFamily;
    bilingual.style.margin = "24px 0 0";
    bilingual.style.maxWidth = "70ch";
    bilingual.style.lineHeight = "1.5";
    bilingual.setAttribute("data-font-qa-sample", "true");
    document.body.appendChild(bilingual);

    const bodyFaces = await document.fonts.load(`16px ${bodyFamily}`, sample);
    const displayFaces = await document.fonts.load(`32px ${displayFamily}`, sample);
    const loadedFamilies = [...document.fonts]
      .filter((font) => font.status === "loaded")
      .map((font) => font.family);

    return {
      bodyFamily,
      displayFamily,
      bodyFacesLoaded: bodyFaces.length,
      displayFacesLoaded: displayFaces.length,
      loadedFamilies,
      sampleRendered: bilingual.getBoundingClientRect().width > 0,
    };
  }, BILINGUAL_SAMPLE);

  expect(fontRequests.length).toBeGreaterThanOrEqual(2);
  expect(fontRequests.every((url) => url.includes("/_next/static/media/"))).toBe(true);
  expect(unexpectedExternalRequests).toEqual([]);
  expect(typography.bodyFamily).toMatch(/Inter/i);
  expect(typography.displayFamily).toMatch(/spaceGrotesk|Space_Grotesk|Space Grotesk/i);
  expect(typography.loadedFamilies).toContain("inter");
  expect(typography.loadedFamilies).toContain("spaceGrotesk");
  expect(typography.bodyFacesLoaded).toBeGreaterThan(0);
  expect(typography.displayFacesLoaded).toBeGreaterThan(0);
  expect(typography.sampleRendered).toBe(true);
  expect(consoleWarnings.filter((message) => /Google Fonts|fallback/i.test(message))).toEqual([]);

  const screenshotDirectory = process.env.ARGUS_FONT_SCREENSHOT_DIR;
  if (screenshotDirectory) {
    await page.screenshot({
      path: `${screenshotDirectory}/font-offline-${testInfo.project.name}.png`,
      fullPage: true,
    });
  }
});
