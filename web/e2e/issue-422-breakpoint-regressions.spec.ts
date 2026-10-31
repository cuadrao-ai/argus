import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { expect, test, type Locator, type Page } from "@playwright/test";
import {
  FREEZE_CSS,
  installBreakpointFixture,
  type Language,
  type Theme,
} from "./support/breakpoint-fixture";

const VIEWPORT = { width: 390, height: 844 } as const;
const CAPTURE_SCREENSHOT_OPTIONS = {
  animations: "disabled",
  caret: "hide",
  scale: "css",
} as const;
const EVIDENCE_ROOT = join(
  __dirname,
  "..",
  "..",
  "docs",
  "reports",
  "evidence",
  "422",
);
const capturePhase = process.env.ARGUS_ISSUE_422_CAPTURE_PHASE;

async function captureFinding({
  finding,
  slug,
  screenshot,
  renderedText,
  metadata,
}: {
  finding: number;
  slug: string;
  screenshot: () => Promise<Buffer>;
  renderedText: string;
  metadata?: unknown;
}) {
  if (capturePhase !== "before" && capturePhase !== "after") return;
  const normalizedRenderedText = renderedText
    .split("\n")
    .map((line) => (line.trim() ? line : ""))
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  const base = join(
    EVIDENCE_ROOT,
    capturePhase,
    `finding-${finding}-${slug}`,
  );
  await mkdir(dirname(base), { recursive: true });
  await writeFile(`${base}.png`, await screenshot());
  await writeFile(`${base}.txt`, `${normalizedRenderedText}\n`, "utf8");
  if (metadata !== undefined) {
    await writeFile(
      `${base}.json`,
      `${JSON.stringify(metadata, null, 2)}\n`,
      "utf8",
    );
  }
}

async function captureVerifiedFinding(
  input: Parameters<typeof captureFinding>[0] & {
    verify: () => void | Promise<void>;
  },
) {
  const { verify, ...capture } = input;
  if (capturePhase === "after") await verify();
  await captureFinding(capture);
  if (capturePhase !== "after") await verify();
}

async function openFixture(
  page: Page,
  url: string,
  options: {
    language?: Language;
    theme?: Theme;
    viewport?: { width: number; height: number };
  } = {},
) {
  const theme = options.theme ?? "dark";
  await page.setViewportSize(options.viewport ?? VIEWPORT);
  await page.emulateMedia({ colorScheme: theme });
  await installBreakpointFixture(page, options);
  await page.goto(url, { waitUntil: "networkidle" });
  await page.addStyleTag({ content: FREEZE_CSS });
  await page.waitForTimeout(400);
}

async function openSearch(page: Page, language: Language = "en") {
  const shellMenu = page.getByTestId("chat-shell-menu-trigger");
  if (await shellMenu.count()) await shellMenu.click();
  await page
    .getByRole("button", { name: language === "es-419" ? /^buscar$/i : /^search$/i })
    .first()
    .click();
  await page.waitForTimeout(400);
}

async function searchRowGeometry(row: Locator) {
  const title = row.locator("span.truncate").first();
  const date = row.getByText(/^Aug 1$/).first();
  const menu = row.getByTestId("command-palette-row-menu");
  return {
    title: await title.evaluate((element) => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      text: element.textContent,
    })),
    date: await date.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      return { left: rect.left, right: rect.right };
    }),
    menu: await menu.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      return { left: rect.left, right: rect.right };
    }),
  };
}

async function openUsageWithOneRemaining(page: Page) {
  await page.setViewportSize(VIEWPORT);
  await page.emulateMedia({ colorScheme: "dark" });
  await installBreakpointFixture(page, {
    language: "es-419",
    theme: "dark",
  });
  const dayEnd = "2026-08-01T23:59:59Z";
  const hourEnd = "2026-08-01T13:00:00Z";
  await page.route("**/api/v1/me/usage", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        allowances: {
          compute: {
            hour: null,
            day: null,
            guest_session: null,
            available_now: true,
            limiting_window: null,
          },
          grounding: {
            hour: {
              limit: 20,
              used: 19,
              remaining: 1,
              period_end: hourEnd,
            },
            day: {
              limit: 60,
              used: 59,
              remaining: 1,
              period_end: dayEnd,
            },
            guest_session: null,
            available_now: true,
            limiting_window: "hour",
          },
          execution: {
            hour: {
              limit: 5,
              used: 4,
              remaining: 1,
              period_end: hourEnd,
            },
            day: {
              limit: 10,
              used: 9,
              remaining: 1,
              period_end: dayEnd,
            },
            guest_session: null,
            available_now: true,
            limiting_window: "day",
          },
        },
      }),
    }),
  );
  await page.goto("/chat", { waitUntil: "networkidle" });
  await page.addStyleTag({ content: FREEZE_CSS });
  await page.getByTestId("chat-shell-menu-trigger").click();
  await page
    .getByRole("button", { name: /^(ajustes|configuración)$/i })
    .first()
    .click();
  await page.getByRole("button", { name: /^controles de datos$/i }).click();
  await page.getByRole("button", { name: /^uso$/i }).click();
  await page.waitForTimeout(300);
}

test.describe("issue #422 breakpoint regressions", () => {
  test("finding 2 keeps the full Omnisearch title at 390", async ({ page }) => {
    await openFixture(page, "/chat?conversation=conversation-alpha");
    await openSearch(page);
    const row = page.locator("[data-palette-row-index]").first();
    const geometry = await searchRowGeometry(row);

    await captureVerifiedFinding({
      finding: 2,
      slug: "omnisearch-title",
      screenshot: () => row.screenshot(CAPTURE_SCREENSHOT_OPTIONS),
      renderedText: await row.innerText(),
      metadata: geometry,
      verify: () => {
        expect(geometry.title.text).toBe("Apple vs SPY, twelve months");
        expect(geometry.title.scrollWidth).toBeLessThanOrEqual(
          geometry.title.clientWidth,
        );
      },
    });
  });

  for (const viewport of [
    { width: 720, height: 1024 },
    { width: 1024, height: 768 },
  ]) {
    test(`finding 2 preserves the readable title at ${viewport.width}`, async ({
      page,
    }) => {
      await openFixture(page, "/chat?conversation=conversation-alpha", {
        viewport,
      });
      await openSearch(page);
      const title = page
        .locator("[data-palette-row-index]")
        .first()
        .locator("span.truncate")
        .first();
      const geometry = await title.evaluate((element) => ({
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
      }));

      expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.clientWidth);
    });
  }

  test("finding 3 keeps the date clear of the row menu at 390", async ({ page }) => {
    await openFixture(page, "/chat?conversation=conversation-alpha");
    await openSearch(page);
    const row = page.locator("[data-palette-row-index]").first();
    const geometry = await searchRowGeometry(row);
    const gap = geometry.menu.left - geometry.date.right;

    await captureVerifiedFinding({
      finding: 3,
      slug: "omnisearch-date-menu-gap",
      screenshot: () => row.screenshot(CAPTURE_SCREENSHOT_OPTIONS),
      renderedText: await row.innerText(),
      metadata: { ...geometry, gap },
      verify: () => expect(gap).toBeGreaterThanOrEqual(8),
    });
  });

  test("finding 4 renders a single asset symbol once", async ({ page }) => {
    await openFixture(page, "/chat?conversation=conversation-alpha");
    const run = page.getByRole("button", { name: /run backtest/i }).first();
    await run.scrollIntoViewIfNeeded();
    const card = run.locator("xpath=ancestor::section[1]");
    const renderedText = await card.innerText();
    const symbolCount = renderedText.match(/\bAAPL\b/g)?.length ?? 0;

    await captureVerifiedFinding({
      finding: 4,
      slug: "confirmation-symbol",
      screenshot: () => card.screenshot(CAPTURE_SCREENSHOT_OPTIONS),
      renderedText,
      metadata: { symbolCount },
      verify: () => expect(symbolCount).toBe(1),
    });
  });

  test("finding 5 uses singular Spanish usage agreement at count one", async ({
    page,
  }) => {
    await openUsageWithOneRemaining(page);
    const sheet = page.locator('[role="dialog"]').last();
    const renderedText = await sheet.innerText();

    await captureVerifiedFinding({
      finding: 5,
      slug: "spanish-usage-singular",
      screenshot: () => sheet.screenshot(CAPTURE_SCREENSHOT_OPTIONS),
      renderedText,
      verify: () => {
        expect(renderedText).toContain("Queda 1 hoy");
        expect(renderedText).toContain("1 disponible esta hora");
        expect(renderedText).not.toContain("Quedan 1 hoy");
        expect(renderedText).not.toContain("1 disponibles esta hora");
      },
    });
  });

  test("finding 6 renders Spanish auth diacritics and accessible labels", async ({
    page,
  }) => {
    await openFixture(page, "/?auth=login", {
      language: "es-419",
      theme: "light",
    });
    const email = page.locator('input[type="email"]');
    const password = page.locator('input[type="password"]');
    const showPassword = page
      .getByRole("button", { name: /mostrar contrase/i })
      .first();

    await captureVerifiedFinding({
      finding: 6,
      slug: "spanish-auth-diacritics",
      screenshot: () =>
        page.screenshot({
          ...CAPTURE_SCREENSHOT_OPTIONS,
          fullPage: false,
        }),
      renderedText: await page.locator("body").innerText(),
      metadata: {
        emailPlaceholder: await email.getAttribute("placeholder"),
        passwordPlaceholder: await password.getAttribute("placeholder"),
        showPassword: await showPassword.getAttribute("aria-label"),
      },
      verify: async () => {
        await expect(email).toHaveAttribute(
          "placeholder",
          "Correo electrónico",
        );
        await expect(password).toHaveAttribute("placeholder", "Contraseña");
        await expect(showPassword).toHaveAccessibleName("Mostrar contraseña");
      },
    });
    await showPassword.click();
    await expect(page.getByRole("button", { name: /ocultar contrase/i }).first())
      .toHaveAccessibleName("Ocultar contraseña");
  });

  test("finding 7 keeps one visible dossier title and an accessible sheet name", async ({
    page,
  }) => {
    const title = "Apple vs SPY, twelve months";
    await openFixture(page, "/chat?conversation=conversation-alpha");
    await openSearch(page);
    await page.locator("[data-palette-row-index]").first().click();
    const sheet = page.getByRole("dialog", { name: title });
    const headings = sheet.locator("h1, h2, h3").filter({ hasText: title });
    const visibleTitleCount = await headings.evaluateAll((elements) =>
      elements.filter((element) => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return (
          style.display !== "none" &&
          style.visibility !== "hidden" &&
          rect.width > 2 &&
          rect.height > 2
        );
      }).length,
    );
    const renderedText = await sheet.innerText();

    await captureVerifiedFinding({
      finding: 7,
      slug: "dossier-title",
      screenshot: () => sheet.screenshot(CAPTURE_SCREENSHOT_OPTIONS),
      renderedText,
      metadata: { visibleTitleCount },
      verify: async () => {
        await expect(sheet).toHaveAccessibleName(title);
        expect(visibleTitleCount).toBe(1);
      },
    });
  });
});
