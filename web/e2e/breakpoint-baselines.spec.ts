import { expect, test, type Locator, type Page } from "@playwright/test";
import {
  FREEZE_CSS,
  installBreakpointFixture,
  type Language,
  type Theme,
} from "./support/breakpoint-fixture";

/**
 * Visual baselines for legal, auth, and settings.
 *
 * Deliberately excludes the chat transcript, composer, confirmation card, and
 * result card: those are being rewritten, and a baseline committed against them
 * is a baseline somebody regenerates next week. Argus answers are model output
 * and cannot be baselined at all — nothing here captures one.
 *
 * Settings panels are captured as the panel element rather than the page,
 * because the settings sheet floats over the chat shell and a full-page capture
 * would fail on every chat change for reasons that have nothing to do with
 * settings.
 *
 * See `breakpoint-baselines.playwright.config.ts` for the run command.
 */

const BANDS = {
  390: { width: 390, height: 844 },
  720: { width: 720, height: 1024 },
  1024: { width: 1024, height: 800 },
} as const;

type Band = keyof typeof BANDS;

const SPINE: Array<{ band: Band; language: Language; theme: Theme }> = [
  { band: 390, language: "en", theme: "dark" },
  { band: 720, language: "en", theme: "dark" },
  { band: 1024, language: "en", theme: "dark" },
  /* One crossed cell per surface, at the band and combination most likely to
     break: narrowest width, longest copy, inverted theme. */
  { band: 390, language: "es-419", theme: "light" },
];

function tag(cell: { band: Band; language: Language; theme: Theme }) {
  return `${cell.band}-${cell.language === "es-419" ? "es" : "en"}-${cell.theme}`;
}

async function open(
  page: Page,
  cell: { band: Band; language: Language; theme: Theme },
  url: string,
) {
  await page.setViewportSize(BANDS[cell.band]);
  await page.emulateMedia({ colorScheme: cell.theme });
  await installBreakpointFixture(page, {
    language: cell.language,
    theme: cell.theme,
  });
  await page.goto(url, { waitUntil: "networkidle" });
  await page.addStyleTag({ content: FREEZE_CSS });
  await page.waitForTimeout(600);
}

/** Settings lives behind the drawer below the tablet stop. */
async function openSettings(page: Page, band: Band) {
  if (band < 720) {
    const trigger = page.getByTestId("chat-shell-menu-trigger");
    await trigger.click();
    await page.waitForTimeout(400);
  }
  await page
    .getByRole("button", { name: /^(settings|ajustes|configuración)$/i })
    .first()
    .click();
  await page.waitForTimeout(500);
}

/**
 * Below the desktop stop the settings menu is a sheet and the sheet is the
 * panel; at desktop the menu surface is. Modals are a dialog at every band.
 */
function settingsPanel(page: Page): Locator {
  return page
    .locator('[role="dialog"], [data-profile-menu-surface]')
    .last();
}

async function click(page: Page, name: RegExp) {
  await page.getByRole("button", { name }).first().click();
  await page.waitForTimeout(500);
}

async function captureMarkedBaseline(
  surface: Locator,
  marker: Locator,
  name: string,
) {
  await expect(
    marker,
    `Refusing to capture ${name} without its surface marker`,
  ).toBeVisible();
  await expect(surface).toHaveScreenshot(name);
}

/* ------------------------------------------------------------- auth --- */

const PAGES: Array<[string, string]> = [
  ["login", "/?auth=login"],
  ["signup", "/?auth=signup"],
  ["request-access", "/?auth=request"],
  ["forgot-password", "/auth/forgot-password"],
  ["recovery", "/auth/recovery"],
  ["account-security", "/account/security"],
];

for (const cell of SPINE) {
  test.describe(`auth ${tag(cell)}`, () => {
    for (const [name, url] of PAGES) {
      test(name, async ({ page }) => {
        await open(page, cell, url);
        await expect(page).toHaveScreenshot(`${name}-${tag(cell)}.png`);
      });
    }
  });
}

/* ---------------------------------------------- pointer-capability proof --- */

test.describe("sidebar actions 1024-touch-en-dark", () => {
  test.use({ hasTouch: true });

  test("recents actions", async ({ page }) => {
    const cell = { band: 1024, language: "en", theme: "dark" } as const;
    await open(page, cell, "/chat");
    expect(
      await page.evaluate(() => matchMedia("(any-pointer: coarse)").matches),
    ).toBe(true);

    await page.getByRole("button", { name: /^recents$/i }).first().click();
    await page.waitForTimeout(400);

    const sidebar = page.locator("aside").first();
    const marker = sidebar.getByText("Weekly Nvidia buys", { exact: true });
    await captureMarkedBaseline(
      sidebar,
      marker,
      "sidebar-recents-actions-1024-touch-en-dark.png",
    );
  });
});

/* --------------------------------------------------------------- settings --- */

/** Sections of the settings menu itself. */
const SECTIONS: Array<[string, RegExp]> = [
  ["settings-root", /^$/],
  ["settings-profile", /^(profile|perfil)$/i],
  ["settings-data", /^(data controls|controles de datos)$/i],
  ["settings-preferences", /^(preferences|preferencias)$/i],
  ["settings-help-legal", /^(help & legal|ayuda y legal|ayuda y aviso legal)$/i],
];

/**
 * Leaves reached from Data Controls, and from Preferences. `bands` can narrow
 * an intentional coverage slice: the sidebar preference exists only from the
 * tablet stop up, while the route-derived Security baseline targets the two
 * widths where sheet navigation had regressed.
 */
const LEAVES: Array<{
  name: string;
  section: RegExp;
  leaf: RegExp;
  bands?: Band[];
  pageUrl?: RegExp;
}> = [
  {
    name: "settings-archived",
    section: /^(data controls|controles de datos)$/i,
    leaf: /archived chats|chats archivados/i,
  },
  {
    name: "settings-deleted",
    section: /^(data controls|controles de datos)$/i,
    leaf: /recently deleted|borrados recientemente/i,
  },
  {
    name: "settings-security",
    section: /^(data controls|controles de datos)$/i,
    leaf: /^(security|seguridad)$/i,
    bands: [390, 720],
    pageUrl: /\/account\/security$/,
  },
  {
    name: "settings-usage",
    section: /^(data controls|controles de datos)$/i,
    leaf: /^(usage|uso)$/i,
  },
  {
    name: "settings-appearance",
    section: /^(preferences|preferencias)$/i,
    leaf: /^(appearance|apariencia)$/i,
  },
  {
    name: "settings-language",
    section: /^(preferences|preferencias)$/i,
    leaf: /^(app language|idioma de la app)$/i,
  },
  {
    name: "settings-sidebar",
    section: /^(preferences|preferencias)$/i,
    leaf: /^(sidebar|barra lateral)$/i,
    bands: [720, 1024],
  },
];

for (const cell of SPINE) {
  test.describe(`settings ${tag(cell)}`, () => {
    for (const [name, section] of SECTIONS) {
      test(name, async ({ page }) => {
        await open(page, cell, "/chat");
        await openSettings(page, cell.band);
        if (section.source !== "^$") await click(page, section);
        await expect(settingsPanel(page)).toHaveScreenshot(
          `${name}-${tag(cell)}.png`,
        );
      });
    }

    for (const { name, section, leaf, bands, pageUrl } of LEAVES) {
      if (bands && !bands.includes(cell.band)) continue;
      test(name, async ({ page }) => {
        await open(page, cell, "/chat");
        await openSettings(page, cell.band);
        await click(page, section);
        await click(page, leaf);
        if (pageUrl) {
          await expect(page).toHaveURL(pageUrl);
          await page.waitForLoadState("networkidle");
          // A document navigation drops the CSS installed by `open`.
          await page.addStyleTag({ content: FREEZE_CSS });
          await page.waitForTimeout(600);
          await page.locator("nextjs-portal").evaluateAll((portals) => {
            for (const portal of portals) {
              (portal as HTMLElement).style.setProperty(
                "display",
                "none",
                "important",
              );
            }
          });
          await expect(page).toHaveScreenshot(`${name}-${tag(cell)}.png`);
          return;
        }
        await expect(settingsPanel(page)).toHaveScreenshot(
          `${name}-${tag(cell)}.png`,
        );
      });
    }
  });
}
