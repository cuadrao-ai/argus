import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { expect, test, type Page } from "@playwright/test";
import {
  FREEZE_CSS,
  installBreakpointFixture,
  type Account,
  type Language,
  type Theme,
  type UsageState,
} from "./support/breakpoint-fixture";

/**
 * Capture pass for the breakpoint audit.
 *
 * This spec walks every guest and signed-in surface at the DESIGN.md section 8
 * bands and writes a PNG plus the rendered text of each capture, because
 * reading the text is what catches clipping and duplication that a passing
 * assertion does not. Focused navigation regressions also assert their route.
 * Visual enforcement lives in `breakpoint-baselines.spec.ts`; this file is the
 * evidence the audit is read from. Run with:
 *   bunx playwright test e2e/breakpoint-audit.spec.ts
 */

const OUT_DIR = join(
  __dirname,
  "..",
  "..",
  "docs",
  "evidence",
  "breakpoint-audit",
);

/* Taken inside each band rather than on its boundary, so a stop that moved by a
   pixel still shows up here. */
const BANDS = {
  390: { width: 390, height: 844 },
  720: { width: 720, height: 1024 },
  1024: { width: 1024, height: 800 },
} as const;

type Band = keyof typeof BANDS;

type Ctx = {
  account?: Account;
  language?: Language;
  theme?: Theme;
  usage?: UsageState;
  emptyChat?: boolean;
};

/**
 * `proof` is the marker that the surface the file is named after is actually on
 * screen. It is required, and that is the point.
 *
 * A capture takes whatever is rendered and files it under a name that claims a
 * surface. When the two disagree the artifact is worse than missing, because it
 * reads as coverage. Three of those had shipped across two review rounds: a
 * guest result card that was byte-identical to the conversation capture, two
 * dossier captures that were transcripts, and a `settings-security` capture
 * that was the empty chat at the two bands where that surface did not exist.
 *
 * The first round made `proof` optional, which fixed the instances and left the
 * shape: any call site could still opt out by passing nothing, and the one that
 * did was the surface a sibling test in this same file documented as
 * unreachable below 1024. So the parameter is mandatory now. A capture with no
 * honest marker is not a capture worth filing, and a surface that cannot be
 * reached at a band should not be photographed there.
 */
async function capture(page: Page, name: string, proof: RegExp) {
  const base = join(OUT_DIR, name);
  await mkdir(dirname(base), { recursive: true });
  await page.addStyleTag({ content: FREEZE_CSS });
  await page.waitForTimeout(400);
  const text = await page
    .evaluate(() => document.body.innerText)
    .catch(() => "");
  if (!proof.test(text)) {
    throw new Error(
      `Capture "${name}" does not contain the surface it is named for.\n` +
        `Expected to match ${proof}\nRendered text was:\n${text.slice(0, 800)}`,
    );
  }
  await page.screenshot({ path: `${base}.png`, fullPage: false });
  await writeFile(`${base}.txt`, text, "utf8");
}

/* Markers for the surfaces whose names make a claim. Each is text the surface
   cannot render without, in either language. */
const PROOF = {
  emptyChat: /What do you want to test|Describe an investing idea|Qué quieres probar|Describe una idea/i,
  transcript: /Compare Apple with SPY|Compara Apple con SPY/i,
  confirmation: /Run backtest|Ejecutar backtest/i,
  result: /Ending value|Simulation Complete|Valor final|Simulación completa/i,
  search: /\d+\s+conversa/i,
  /* Not "Open conversation": that button belongs to the sheet, and from the
     desktop stop up the dossier is a pane without it. This marker is the run
     outcome itself, which both forms render. */
  dossier: /Retest with current data|Volver a probar con datos actuales/i,
  conversionPrompt: /KEEP GOING WITH ARGUS|Request access|Solicitar acceso|SIGUE|Start a new conversation|nueva conversación/i,
  settingsRoot: /Data Controls|Controles de datos/i,
  usage: /left today|available this hour|hoy|esta hora/i,
  /* One per settings destination, each a row only that panel renders. */
  settingsProfile: /Avatar color|Color de avatar/i,
  settingsData: /Delete all conversations|Eliminar todas las conversaciones/i,
  /* Not the Sidebar row: that one only exists from the tablet stop up, so it
     cannot prove this panel at 390. Appearance is the row that is always here
     and that the Profile panel does not also render. */
  settingsPreferences: /Appearance|Apariencia/i,
  settingsHelpLegal: /Keyboard shortcuts|Atajos de teclado/i,
  /* At 390 the panel drops the keyboard shortcuts row, and its remaining rows
     are Terms and Privacy, which the settings root also renders in its footer.
     So the marker there is the drilled-in sheet itself: its title followed by
     the back label, which the root never produces because the row after
     Help & Legal at root is Feedback. */
  settingsHelpLegalSheet:
    /Help & Legal\s*\n\s*(Settings|Ajustes|Configuración)/i,
  settingsArchived: /Archived chats|Chats archivados/i,
  settingsDeleted: /currently be restored|Currently restorable|restaurar/i,
  settingsSecurity: /Account security|Seguridad de la cuenta/i,
  settingsLanguage: /Español/i,
  settingsAppearance: /System|Sistema/i,
  settingsSidebar: /Icons only|On hover|Solo íconos|Al pasar/i,
  /* Below the desktop stop the Security row goes nowhere, so what is on screen
     after that click is the chat shell. Named for what it is. */
  chatShell: /Describe an investing idea|Describe una idea/i,
  recents: /Recents|Recientes/i,
  usageError: /Try again|Reintentar/i,
  /* The typed question itself, which the composer renders into the DOM. */
  typedQuestion: /drawdown/i,
  /* Legal and auth each cross-link to the other, so the marker has to be body
     copy rather than a heading or a nav label. */
  privacy: /Data we collect|Datos que recopilamos/i,
  terms: /Acceptable use|Uso aceptable/i,
  login: /Forgot password|Olvidaste tu contraseña/i,
  signup: /At least 8 characters|Al menos 8 caracteres/i,
  requestAccess: /Request access to Cuadrao|Solicita acceso a Cuadrao/i,
  forgotPassword: /Recover your account|Recupera tu cuenta/i,
  recovery: /Choose a new password|Elige una nueva contraseña/i,
} as const;

async function open(page: Page, band: Band, url: string, ctx: Ctx = {}) {
  await page.setViewportSize(BANDS[band]);
  await page.emulateMedia({ colorScheme: ctx.theme ?? "dark" });
  await installBreakpointFixture(page, ctx);
  await page.goto(url, { waitUntil: "networkidle" });
  // Dev-only chrome sits in the same corner as the header menu and swallows its
  // clicks, so it goes before any interaction, not just before a capture.
  await page.addStyleTag({ content: FREEZE_CSS });
  await page.waitForTimeout(700);
}

/** Below 720 the drawer holds what the rail holds from tablet up. */
async function openDrawerIfNarrow(page: Page, band: Band) {
  if (band >= 720) return;
  const trigger = page.getByTestId("chat-shell-menu-trigger");
  if (await trigger.count()) {
    await trigger.click();
    await page.waitForTimeout(500);
  }
}

/**
 * Below the desktop stop the dossier is a sheet that a row click opens. From
 * 1024 up it is a pane already rendered beside the list, and clicking the row
 * leaves the palette for the conversation instead, which is how two captures
 * came to be named for a dossier while holding a transcript.
 */
async function openDossier(page: Page, band: Band): Promise<boolean> {
  if (band >= 1024) return true;
  const row = page.locator("[data-palette-row-index]").first();
  if (!(await row.count())) return false;
  await row.click();
  await page.waitForTimeout(700);
  return true;
}

async function openSearch(page: Page, band: Band) {
  await openDrawerIfNarrow(page, band);
  const search = page.getByRole("button", { name: /^(search|buscar)$/i }).first();
  if (await search.count()) {
    await search.click();
    await page.waitForTimeout(700);
  }
}

async function openSettings(page: Page, band: Band, label = /^(settings|configuración|ajustes)$/i) {
  await openDrawerIfNarrow(page, band);
  const trigger = page.getByRole("button", { name: label }).first();
  if (await trigger.count()) {
    await trigger.click();
    await page.waitForTimeout(600);
  }
}

async function clickByName(page: Page, name: RegExp) {
  const target = page.getByRole("button", { name }).first();
  if (!(await target.count())) return false;
  try {
    await target.click({ timeout: 4_000 });
  } catch {
    // A panel left open by the previous step swallows the click; the audit
    // should record what it can rather than abandoning the whole band.
    return false;
  }
  await page.waitForTimeout(600);
  return true;
}

/** Modals stack, and one left open intercepts every later click in the band. */
async function dismissDialogs(page: Page) {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    if (!(await page.locator('[role="dialog"]').count())) return;
    await page.keyboard.press("Escape");
    await page.waitForTimeout(350);
  }
}

const ALL_BANDS: Band[] = [390, 720, 1024];

/* ---------------------------------------------------------------- guest --- */

test.describe("guest surfaces", () => {
  for (const band of ALL_BANDS) {
    test(`guest at ${band}`, async ({ page }) => {
      /* The guest entry surface is NOT captured here. An established session
         redirects `/` to `/chat` under mock auth, so this config can only ever
         photograph the redirect. `breakpoint-audit-landing.spec.ts` owns
         `guest/entry-*` and runs with mock auth off. */
      await open(page, band, "/chat", { account: "guest", emptyChat: true });
      await capture(page, `guest/empty-chat-${band}-en-dark`, PROOF.emptyChat);

      // A first question typed but not sent: the composer at its tallest.
      const composer = page
        .locator("textarea, [contenteditable='true']")
        .first();
      if (await composer.count()) {
        await composer.click();
        await composer.fill(
          "Compare Apple with SPY over the last twelve months and show me the drawdown",
        );
        await page.waitForTimeout(500);
        await capture(page, `guest/first-question-${band}-en-dark`, PROOF.typedQuestion);
      }

      await open(page, band, "/chat?conversation=conversation-alpha", {
        account: "guest",
      });
      await capture(page, `guest/conversation-${band}-en-dark`, PROOF.transcript);

      const confirm = page.locator('button[class*="tablet:min-h-9"]').first();
      if (await confirm.count()) {
        await confirm.scrollIntoViewIfNeeded();
        await page.waitForTimeout(400);
        await capture(page, `guest/confirmation-card-${band}-en-dark`, PROOF.confirmation);
      }

      /* Scroll the card itself into frame rather than guessing with a wheel
         delta. A wheel that lands on the wrong element leaves the viewport at
         the bottom of the transcript, and because innerText carries the whole
         transcript regardless of scroll, the text proof would still pass while
         the PNG showed something else entirely. */
      const resultCard = page
        .getByText(/Ending value|Valor final/i)
        .first();
      await resultCard.scrollIntoViewIfNeeded();
      await page.waitForTimeout(500);
      await capture(page, `guest/result-card-${band}-en-dark`, PROOF.result);
    });

    test(`guest dossier and exhaustion at ${band}`, async ({ page }) => {
      await open(page, band, "/chat?conversation=conversation-alpha", {
        account: "guest",
      });
      await openSearch(page, band);
      await capture(page, `guest/search-${band}-en-dark`, PROOF.search);

      if (await openDossier(page, band)) {
        await capture(page, `guest/dossier-${band}-en-dark`, PROOF.dossier);
      }

      await open(page, band, "/chat?conversation=conversation-alpha", {
        account: "guest",
        usage: "exhausted",
      });
      await capture(page, `guest/exhausted-${band}-en-dark`, PROOF.transcript);

      /* Exhaustion is not a banner. It surfaces when the guest tries to spend
         the allowance they no longer have, so the capture has to run the
         action rather than just load the exhausted state. */
      const run = page
        .getByRole("button", { name: /run backtest|ejecutar/i })
        .first();
      if (await run.count()) {
        await run.scrollIntoViewIfNeeded();
        await run.click();
        await page.waitForTimeout(1200);
        await capture(page, `guest/exhausted-prompt-${band}-en-dark`, PROOF.conversionPrompt);
      }

      /* A guest cannot open a second conversation, so New chat is the gated
         action that raises the conversion prompt without needing a live turn. */
      await open(page, band, "/chat?conversation=conversation-alpha", {
        account: "guest",
      });
      await openDrawerIfNarrow(page, band);
      if (await clickByName(page, /^(new chat|chat nuevo|nuevo chat)$/i)) {
        await capture(page, `guest/signup-prompt-${band}-en-dark`, PROOF.conversionPrompt);
      }

      await open(page, band, "/chat", { account: "guest", emptyChat: true });
      if (await clickByName(page, /^(sign in|iniciar sesión)$/i)) {
        await capture(page, `guest/sign-in-cta-${band}-en-dark`, PROOF.conversionPrompt);
      }
    });
  }
});

/* ------------------------------------------------------------ signed in --- */

test.describe("signed-in surfaces", () => {
  for (const band of ALL_BANDS) {
    test(`chat and recents at ${band}`, async ({ page }) => {
      await open(page, band, "/chat", { emptyChat: true });
      await capture(page, `signed-in/empty-chat-${band}-en-dark`, PROOF.emptyChat);

      await open(page, band, "/chat?conversation=conversation-alpha", {});
      await capture(page, `signed-in/conversation-${band}-en-dark`, PROOF.transcript);

      await openDrawerIfNarrow(page, band);
      await capture(page, `signed-in/recents-${band}-en-dark`, PROOF.recents);

      await open(page, band, "/chat?conversation=conversation-alpha", {});
      await openSearch(page, band);
      await capture(page, `signed-in/search-${band}-en-dark`, PROOF.search);
    });

    /* The settings menu is an accordion whose sections push sub-views and
       modals, so each leaf is reached from a fresh open rather than by
       unwinding the previous one. */
    test(`settings panels at ${band}`, async ({ page }) => {
      // Each leaf is reached from a fresh load, so this walk is a dozen boots.
      test.setTimeout(180_000);
      await open(page, band, "/chat", { emptyChat: true });
      await openSettings(page, band);
      await capture(page, `signed-in/settings-main-${band}-en-dark`, PROOF.settingsRoot);

      for (const [section, name, proof] of [
        ["profile", /^(profile|perfil)$/i, PROOF.settingsProfile],
        ["data", /^(data controls|controles de datos)$/i, PROOF.settingsData],
        ["preferences", /^(preferences|preferencias)$/i, PROOF.settingsPreferences],
        [
          "help-legal",
          /^(help & legal|ayuda y legal|ayuda y aviso legal)$/i,
          // The keyboard shortcuts row is not rendered at 390.
          band >= 720 ? PROOF.settingsHelpLegal : PROOF.settingsHelpLegalSheet,
        ],
      ] as const) {
        await open(page, band, "/chat", { emptyChat: true });
        await openSettings(page, band);
        if (await clickByName(page, name)) {
          await capture(
            page,
            `signed-in/settings-${section}-${band}-en-dark`,
            proof,
          );
        }
      }

      /* `bands` narrows a destination that does not exist at every width. */
      for (const { leaf, name, proof, bands } of [
        {
          leaf: "archived",
          name: /archived chats|chats archivados/i,
          proof: PROOF.settingsArchived,
        },
        {
          leaf: "deleted",
          name: /recently deleted|borrados recientemente/i,
          proof: PROOF.settingsDeleted,
        },
        {
          leaf: "security",
          name: /^(security|seguridad)$/i,
          proof: PROOF.settingsSecurity,
        },
        { leaf: "usage", name: /^(usage|uso)$/i, proof: PROOF.usage },
      ]) {
        if (bands && !bands.includes(band)) continue;
        await open(page, band, "/chat", { emptyChat: true });
        await openSettings(page, band);
        if (!(await clickByName(page, /^(data controls|controles de datos)$/i)))
          continue;
        if (await clickByName(page, name)) {
          await capture(page, `signed-in/settings-${leaf}-${band}-en-dark`, proof);
        }
        await dismissDialogs(page);
      }

      for (const [leaf, name, proof] of [
        ["language", /^(app language|idioma de la app)$/i, PROOF.settingsLanguage],
        ["appearance", /^(appearance|apariencia)$/i, PROOF.settingsAppearance],
        ["sidebar", /^(sidebar|barra lateral)$/i, PROOF.settingsSidebar],
      ] as const) {
        await open(page, band, "/chat", { emptyChat: true });
        await openSettings(page, band);
        if (!(await clickByName(page, /^(preferences|preferencias)$/i))) continue;
        if (await clickByName(page, name)) {
          await capture(page, `signed-in/settings-${leaf}-${band}-en-dark`, proof);
        }
        await dismissDialogs(page);
      }
    });

    /* The profile menu is the `settings-profile` capture above; this test
       carries the two allowance states the healthy fixture never reaches. */
    test(`usage states at ${band}`, async ({ page }) => {
      await open(page, band, "/chat", { emptyChat: true, usage: "error" });
      await openSettings(page, band);
      if (await clickByName(page, /^(data controls|controles de datos)$/i)) {
        if (await clickByName(page, /^(usage|uso)$/i)) {
          await capture(page, `signed-in/usage-error-${band}-en-dark`, PROOF.usageError);
        }
      }

      await open(page, band, "/chat", { emptyChat: true, usage: "nearly_out" });
      await openSettings(page, band);
      if (await clickByName(page, /^(data controls|controles de datos)$/i)) {
        if (await clickByName(page, /^(usage|uso)$/i)) {
          await capture(page, `signed-in/usage-nearly-out-${band}-en-dark`, PROOF.usage);
        }
      }

    });

    /*
     * A persisted result card hydrates from a run fetch rather than from
     * message metadata, so it cannot be stubbed onto a transcript message. The
     * committed playground renders the same component from static fixtures,
     * which is what the width behaviour is read from here.
     */
    test(`result card fixtures at ${band}`, async ({ page }) => {
      await open(page, band, "/dev/result-card", {});
      await capture(page, `signed-in/result-card-playground-${band}-en-dark`, PROOF.result);

      for (const fixture of [
        "positive-single-symbol",
        "negative-single-symbol",
        "benchmark-underperformance-positive",
        "modeled-execution-costs",
      ]) {
        const card = page.getByTestId(`result-card-fixture-${fixture}`).first();
        if (!(await card.count())) continue;
        await card.scrollIntoViewIfNeeded();
        await page.waitForTimeout(300);
        const base = join(OUT_DIR, `signed-in/result-card-${fixture}-${band}-en-dark`);
        await mkdir(dirname(base), { recursive: true });
        await card.screenshot({ path: `${base}.png` });
        await writeFile(`${base}.txt`, await card.innerText(), "utf8");
      }
    });

    /*
     * The cross pass. Crossing every view by language and theme is ~300
     * captures that nobody reads, so it is spent only where copy length or
     * theming actually breaks things: the metric table, the allowance meters
     * and their status chips, the truncated conversation titles, and the
     * five-action confirmation row.
     */
    test(`language and theme cross at ${band}`, async ({ page }) => {
      test.setTimeout(180_000);
      for (const [language, theme] of [
        ["es-419", "dark"],
        ["en", "light"],
        ["es-419", "light"],
      ] as const) {
        const suffix = `${band}-${language === "es-419" ? "es" : "en"}-${theme}`;

        await open(page, band, "/chat?conversation=conversation-alpha", {
          language,
          theme,
        });
        await capture(page, `cross/conversation-${suffix}`, PROOF.transcript);

        await openSearch(page, band);
        await capture(page, `cross/search-${suffix}`, PROOF.search);

        if (await openDossier(page, band)) {
          await capture(page, `cross/dossier-${suffix}`, PROOF.dossier);
        }

        await open(page, band, "/chat", {
          emptyChat: true,
          language,
          theme,
          usage: "nearly_out",
        });
        await openSettings(page, band);
        if (await clickByName(page, /^(data controls|controles de datos)$/i)) {
          if (await clickByName(page, /^(usage|uso)$/i)) {
            await capture(page, `cross/usage-${suffix}`, PROOF.usage);
          }
        }
      }
    });

    /* The visible Security row reaches the same account surface at every band. */
    test(`account security navigation at ${band}`, async ({ page }) => {
      await open(page, band, "/chat?conversation=conversation-alpha", {});
      await openSettings(page, band);
      if (!(await clickByName(page, /^(data controls|controles de datos)$/i)))
        return;
      await capture(page, `findings/security-${band}-before-click`, PROOF.settingsData);

      const security = page.getByRole("button", { name: /^(security|seguridad)$/i }).first();
      if (!(await security.count())) return;
      await security.click();
      // Generous: a client route change plus a paint.
      await page.waitForTimeout(2_500);
      await expect(page).toHaveURL(/\/account\/security$/);
      await capture(
        page,
        `findings/security-${band}-after-click`,
        PROOF.settingsSecurity,
      );

      await writeFile(
        join(OUT_DIR, `findings/security-${band}-url.txt`),
        `${new URL(page.url()).pathname}\n`,
        "utf8",
      );

      // The sheet contributes a temporary entry below 1024; the rail popover
      // does not. Either way, one Back must restore the exact conversation.
      await page.goBack();
      await expect(page).toHaveURL(
        /\/chat\?conversation=conversation-alpha$/,
      );
    });

    test(`legal and auth at ${band}`, async ({ page }) => {
      await open(page, band, "/privacy", {});
      await capture(page, `chrome/privacy-${band}-en-dark`, PROOF.privacy);

      await open(page, band, "/terms", {});
      await capture(page, `chrome/terms-${band}-en-dark`, PROOF.terms);

      await open(page, band, "/?auth=login", {});
      await capture(page, `chrome/login-${band}-en-dark`, PROOF.login);

      await open(page, band, "/?auth=signup", {});
      await capture(page, `chrome/signup-${band}-en-dark`, PROOF.signup);

      await open(page, band, "/?auth=request", {});
      await capture(page, `chrome/request-access-${band}-en-dark`, PROOF.requestAccess);

      await open(page, band, "/auth/forgot-password", {});
      await capture(page, `chrome/forgot-password-${band}-en-dark`, PROOF.forgotPassword);

      await open(page, band, "/auth/recovery", {});
      await capture(page, `chrome/recovery-${band}-en-dark`, PROOF.recovery);

      await open(page, band, "/account/security", {});
      await capture(page, `chrome/account-security-${band}-en-dark`, PROOF.settingsSecurity);
    });
  }
});
