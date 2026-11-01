import { expect, test, type Page } from "@playwright/test";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { installBreakpointFixture } from "./support/breakpoint-fixture";
import { atMidMonth, bandejaRows, reviewAction } from "./support/business-receipt-fixture";

// Business is Spanish only, so every string below is the es-419 copy.

async function capture(page: Page, name: string) {
  const directory = process.env.CUADRAO_RECORD_EVIDENCE_DIR;
  if (!directory) return;
  await page.screenshot({ path: `${directory}/${name}.png`, fullPage: true });
  const facts = page.getByTestId("receipt-current-facts").getByText("Cómo se pagó", { exact: true });
  if (await facts.count()) {
    await facts.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${directory}/${name}-current-facts.png`, fullPage: true });
  }
}

/** Where an open record renders: the page below the desktop stop, the tray beside its list from it. */
function recordArea(page: Page) {
  return page.getByTestId("workspace-panel-region").or(page.getByTestId("side-drawer"));
}

async function confirmRncWarning(page: Page) {
  const dialog = page.getByRole("alertdialog");
  if (await dialog.waitFor({ state: "visible", timeout: 2000 }).then(() => true, () => false)) await dialog.getByRole("button", { name: /^Aprobar( y siguiente)?$/ }).click();
}

const approveButton = (page: Page) => page.getByRole("button", { name: "Aprobar", exact: true });
const saveButton = (page: Page) => page.getByRole("button", { name: "Guardar detalles de revisión", exact: true });
const saveRow = (page: Page, label: string) => page.getByRole("button", { name: `Guardar · ${label}`, exact: true });
const editField = (page: Page, label: string) => page.getByRole("button", { name: `Editar detalles · ${label}`, exact: true });
const fact = (page: Page, key: string) => page.getByTestId("receipt-current-facts").locator(`[data-fact="${key}"]`);

/** Below the desktop stop the form and the original are tabs; from it both columns show and there are no tabs. */
async function showTab(page: Page, name: "Formulario" | "Original") {
  const tabs = page.getByTestId("receipt-review-tabs");
  if (await tabs.isVisible()) await tabs.getByText(name, { exact: true }).click();
}

async function openHistory(page: Page) {
  const all = page.getByTestId("receipt-history").getByRole("button", { name: "Ver todo", exact: true });
  if (await all.isVisible()) await all.click();
  return page.getByTestId("receipt-history");
}

async function openRecord(page: Page, id: string) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  await page.goto(`/dev/business-preview?draft=${id}`);
  await expect(page.getByTestId("business-record-review")).toBeVisible();
}

for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
  test.describe(`One record at ${viewport.width}px`, () => {
    test.use({ viewport });

    test("unknown funding stays beside its original and saves before explicit approval", async ({ page }) => {
      await openRecord(page, dossierFixtureIds.unknown);
      await showTab(page, "Original");
      await expect(page.getByRole("blockquote")).toContainText("No tengo recibo");
      await showTab(page, "Formulario");
      await expect(fact(page, "funding")).toHaveAttribute("data-standing", "empty");
      await expect(fact(page, "funding")).toHaveAttribute("data-attention", "true");
      await expect(page.getByTestId("dossier-attention")).toContainText("Cómo se pagó");
      await expect(page.getByTestId("receipt-review-questions")).toContainText("¿Cómo se pagó?");
      await capture(page, `unknown-funding-${viewport.width}`);
      const approve = approveButton(page);
      await expect(approve).toBeDisabled();
      await editField(page, "Cómo se pagó").click();
      await page.getByRole("combobox", { name: "Cómo se pagó", exact: true }).selectOption("account:acct-ops");
      await expect(approve).toBeDisabled();
      await saveRow(page, "Cómo se pagó").click();
      await expect(page.getByTestId("dossier-attention")).toHaveCount(0);
      await expect(page.getByTestId("receipt-review-questions")).toHaveCount(0);
      await expect(page.getByText(/^Se registró un gasto/)).toHaveCount(0);
      await expect(approve).toBeEnabled();
      await capture(page, `ready-approval-${viewport.width}`);
      await approve.focus();
      await page.keyboard.press("Enter");
      await confirmRncWarning(page);
      await expect(page.getByText("Se registró un gasto tras aprobar la revisión 3.", { exact: true })).toBeVisible();
      await expect(approve).toHaveCount(0);
      await expect(fact(page, "currency")).toHaveAttribute("data-standing", "default");
      await expect(page.getByText("Las correcciones después del registro no están disponibles en este primer flujo.", { exact: true })).toBeVisible();
      const history = await openHistory(page);
      await expect(history).toContainText("Ana Peña");
      await expect(page.getByTestId("business-record-review")).toContainText("permiso otorgado por Lucía Mateo");
      await showTab(page, "Original");
      await expect(page.getByRole("region", { name: "Revisiones en la web" })).toHaveCount(0);
      await capture(page, `approved-history-${viewport.width}`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });

    test("unknown activity can be reviewed as expense before separate approval", async ({ page }) => {
      await openRecord(page, dossierFixtureIds.unknownKind);
      await expect(approveButton(page)).toBeDisabled();
      await editField(page, "Actividad").click();
      await page.getByRole("combobox", { name: "Actividad", exact: true }).selectOption("expense");
      await saveRow(page, "Actividad").click();
      await expect(approveButton(page)).toBeEnabled();
      await expect(page.getByText(/^Se registró un gasto/)).toHaveCount(0);
      const history = await openHistory(page);
      const change = history.locator("li").first();
      await expect(change).toContainText("Actividad: Gasto");
      await expect(change).toContainText("Ana Peña");
      await showTab(page, "Original");
      await expect(page.getByRole("region", { name: "Revisiones en la web" })).toHaveCount(0);
    });

    test("fiscal facts and before-after changes stay readable in Spanish", async ({ page }) => {
      await openRecord(page, dossierFixtureIds.fiscal);
      const fiscal = page.getByTestId("receipt-facts-fiscal");
      await expect(fiscal.getByRole("heading", { name: "Fiscal", exact: true })).toBeVisible();
      await expect(fiscal).toContainText("RNC");
      await expect(fiscal).toContainText("1-31-99988-8");
      await expect(fiscal.getByRole("status", { name: "Estado del RNC: RNC sin verificar" })).toBeVisible();
      await expect(fiscal).toContainText("B0100000099");
      await expect(fiscal).toContainText("e-CF");
      await expect(fiscal).toContainText("526.27");
      await expect(fact(page, "itbis")).toHaveAttribute("data-standing", "verified");
      const history = await openHistory(page);
      await expect(history).toContainText("NCF cambiado de B0100000098 a B0100000099");
      await expect(history).toContainText("ITBIS cambiado de RD$ 100.01 a RD$ 526.27");
      await fiscal.scrollIntoViewIfNeeded();
      await capture(page, `fiscal-spanish-${viewport.width}`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });

    test("proposal-only original text is labelled as an agent proposal in Spanish", async ({ page }) => {
      await openRecord(page, dossierFixtureIds.proposal);
      await showTab(page, "Original");
      const proposal = page.getByRole("region", { name: "Propuestas del agente" });
      await expect(proposal).toContainText("Propuesta: gasto de 3,450 DOP");
      await expect(page.getByRole("region", { name: "Mensajes originales" })).toHaveCount(0);
      await expect(approveButton(page)).toBeVisible();
      await proposal.scrollIntoViewIfNeeded();
      await capture(page, `proposal-spanish-${viewport.width}`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });

    test("Spanish unknown funding saves and waits for explicit human approval", async ({ page }) => {
      await openRecord(page, dossierFixtureIds.unknown);
      await capture(page, `unknown-funding-spanish-${viewport.width}`);
      await editField(page, "Cómo se pagó").click();
      await page.getByRole("combobox", { name: "Cómo se pagó", exact: true }).selectOption("account:acct-ops");
      await saveRow(page, "Cómo se pagó").click();
      await expect(approveButton(page)).toBeEnabled();
      await expect(page.getByText(/^Se registró un gasto/)).toHaveCount(0);
      await capture(page, `ready-approval-spanish-${viewport.width}`);
      await approveButton(page).click();
      await confirmRncWarning(page);
      await expect(page.getByText("Se registró un gasto tras aprobar la revisión 3.", { exact: true })).toBeVisible();
      await expect(page.getByTestId("business-record-review")).toContainText("permiso otorgado por Lucía Mateo");
      await capture(page, `approved-history-spanish-${viewport.width}`);
    });

    test("unknown money is not rendered as zero", async ({ page }) => {
      await openRecord(page, dossierFixtureIds.unknownAmount);
      await expect(fact(page, "amount")).toHaveAttribute("data-standing", "empty");
      await expect(page.getByTestId("receipt-total")).toHaveCount(0);
      await expect(page.getByTestId("receipt-current-facts")).not.toContainText("RD$ 0.00");
    });
  });
}

test.describe("Server authority and uncertain outcomes", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("read-only grant has no edit or approval controls", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.readOnly);
    await expect(page.getByRole("button", { name: /^Editar detalles/ })).toHaveCount(0);
    await expect(approveButton(page)).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Agregar una nota a este registro" })).toHaveCount(0);
  });

  test("an untyped legacy candidate retains corrected receipt details and its source", async ({ page }) => {
    await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
    await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
    await page.goto("/dev/business-preview?receipt=rcpt-papeleria");
    await expect(page.getByLabel("Comercio o persona", { exact: true })).toHaveValue("Papelería Central");
    await expect(page.getByTestId("receipt-review-amount")).toHaveValue("980.50");
    await expect(page.getByTestId("receipt-original-source")).toBeVisible();
    await expect(recordArea(page).getByRole("alert")).toContainText("El movimiento preparado todavía no está disponible");
    await expect(approveButton(page)).toHaveCount(0);
    await page.getByTestId("receipt-review-amount").fill("1020.75");
    await saveButton(page).click();
    await expect(page.getByTestId("receipt-review-amount")).toHaveValue("1,020.75");
    await expect(recordArea(page).getByRole("alert")).toContainText("El movimiento preparado todavía no está disponible");
    await expect(approveButton(page)).toHaveCount(0);
  });

  test("a direct untyped draft shows the preparation blocker without guessing a receipt", async ({ page }) => {
    await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
    await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
    await page.goto(`/dev/business-preview?draft=${dossierFixtureIds.unprepared}`);
    await expect(recordArea(page).getByRole("alert")).toContainText("El movimiento preparado todavía no está disponible");
    await expect(approveButton(page)).toHaveCount(0);
    await expect(page.getByTestId("receipt-original-source")).toHaveCount(0);
  });

  test("a zero total cannot be submitted", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.ready);
    await editField(page, "Monto").click();
    const total = page.getByTestId("dossier-review-amount");
    await total.fill("0");
    const history = await openHistory(page);
    const events = await history.locator("li").count();
    await total.press("Enter");
    await expect(history.locator("li")).toHaveCount(events);
    await expect(total).toBeVisible();
    await expect(approveButton(page)).toBeDisabled();
  });

  test("owner uncertainty is saved explicitly and leaves approval blocked", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.unknown);
    await editField(page, "Cómo se pagó").click();
    await page.getByRole("combobox", { name: "Cómo se pagó", exact: true }).selectOption("owner_does_not_know");
    await saveRow(page, "Cómo se pagó").click();
    await expect(fact(page, "funding")).toContainText("El dueño no sabe");
    await expect(approveButton(page)).toBeDisabled();
  });

  test("stale version requires opening and reviewing the new revision", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.stale);
    await approveButton(page).click();
    await confirmRncWarning(page);
    await expect(recordArea(page).getByRole("alert")).toContainText("Este registro cambió");
    await capture(page, "stale-revision");
    await expect(approveButton(page)).toHaveCount(0);
    await page.getByRole("button", { name: "Reintentar", exact: true }).click();
    await expect(page.getByTestId("receipt-current-facts")).toContainText("3,550.00");
    await expect(page.getByText(/^Se registró un gasto/)).toHaveCount(0);
  });

  test("revoked grant removes action controls and the unavailable record", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.denied);
    await approveButton(page).click();
    await confirmRncWarning(page);
    await expect(recordArea(page).getByRole("alert")).toContainText("acceso actual");
    await capture(page, "denied-access");
    await expect(page.getByTestId("business-record-review")).toHaveCount(0);
    await expect(approveButton(page)).toHaveCount(0);
  });

  test("unknown approval outcome checks status without resubmitting", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.outcomeUnknown);
    await approveButton(page).click();
    await confirmRncWarning(page);
    await expect(recordArea(page).getByRole("alert")).toContainText("Todavía no se conoce el resultado");
    await expect(approveButton(page)).toBeDisabled();
    await page.getByRole("button", { name: "Consultar registro actual", exact: true }).click();
    await expect(page.getByText("Consultando resultado de aprobación", { exact: true })).toBeVisible();
    await capture(page, "unknown-approval-outcome");
    await expect(approveButton(page)).toBeDisabled();
    await expect(page.getByText(/^Se registró un gasto/)).toHaveCount(0);
  });

  test("a save with no answer keeps its correction, holds approval and retries once", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.saveUnknown);
    await editField(page, "Comercio o persona").click();
    const merchant = page.getByRole("textbox", { name: "Comercio o persona", exact: true });
    await merchant.fill("My retained correction");
    await saveRow(page, "Comercio o persona").click();
    const failure = page.getByTestId("row-save-failed");
    await expect(failure).toContainText("No pudimos confirmar si Comercio o persona se guardó.");
    await expect(failure.getByText(/^Ref\./)).toBeVisible();
    await expect(merchant).toHaveValue("My retained correction");
    await expect(approveButton(page)).toBeDisabled();
    await failure.getByRole("button", { name: "Reintentar", exact: true }).click();
    await expect(failure).toHaveCount(0);
    await expect(page.getByTestId("receipt-current-facts")).toContainText("My retained correction");
    const history = await openHistory(page);
    await expect(history.locator("li", { hasText: "Comercio o persona cambiado de Ferretería La Esquina a My retained correction" })).toHaveCount(1);
    await expect(approveButton(page)).toBeEnabled();
    await capture(page, "uncertain-saveUnknown-spanish");
  });

  test("a save another person overtook keeps its correction beside the current record", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.saveConcurrent);
    await editField(page, "Comercio o persona").click();
    const merchant = page.getByRole("textbox", { name: "Comercio o persona", exact: true });
    await merchant.fill("My retained correction");
    await saveRow(page, "Comercio o persona").click();
    const failure = page.getByTestId("row-save-failed");
    await expect(failure).toContainText("No pudimos confirmar si Comercio o persona se guardó.");
    await expect(approveButton(page)).toBeDisabled();
    await failure.getByRole("button", { name: "Reintentar", exact: true }).click();
    await expect(failure).toContainText("Este registro cambió mientras editabas.");
    await expect(merchant).toHaveValue("My retained correction");
    await expect(approveButton(page)).toBeDisabled();
    const history = await openHistory(page);
    await expect(history).toContainText("Comercio o persona cambiado de Ferretería La Esquina a Corrección de otra persona");
    await expect(history).toContainText("Elena Reyes");
    await capture(page, "uncertain-saveConcurrent-spanish");
  });

  test("an acknowledged save settles and the next one builds on its revision", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.ready);
    await editField(page, "Comercio o persona").click();
    await page.getByRole("textbox", { name: "Comercio o persona", exact: true }).fill("Acknowledged correction");
    await saveRow(page, "Comercio o persona").click();
    await expect(page.getByTestId("receipt-current-facts")).toContainText("Acknowledged correction");
    await expect(approveButton(page)).toBeEnabled();
    await editField(page, "Comercio o persona").click();
    await page.getByRole("textbox", { name: "Comercio o persona", exact: true }).fill("New correction");
    await saveRow(page, "Comercio o persona").click();
    await expect(page.getByTestId("receipt-current-facts")).toContainText("New correction");
  });

  test("income is not relabeled as an expense", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.income);
    await expect(approveButton(page)).toBeDisabled();
    await expect(page.getByRole("button", { name: /gasto/i })).toHaveCount(0);
    await expect(page.getByTestId("business-record-review")).toContainText("Esta actividad no admite aprobación en este primer flujo.");
  });

  test("the same current facts and approval action are localized", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.ready);
    await expect(approveButton(page)).toBeVisible();
    await expect(page.getByTestId("receipt-current-facts")).toContainText("Fecha de actividad");
  });

  test("a correction to a suggestion saves that one value as the reviewer's at a new revision", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.fiscal);
    const merchant = fact(page, "counterparty");
    await expect(merchant).toHaveAttribute("data-standing", "suggestion");

    await editField(page, "Comercio o persona").click();
    await page.getByRole("textbox", { name: "Comercio o persona", exact: true }).fill("Ferretería La Esquina SRL");
    await saveRow(page, "Comercio o persona").click();

    await expect(merchant).toHaveAttribute("data-standing", "person");
    await expect(merchant).toContainText("Ferretería La Esquina SRL");
    const history = await openHistory(page);
    await expect(history.locator("li").first()).toContainText("Comercio o persona cambiado de Ferretería La Esquina a Ferretería La Esquina SRL");
    await expect(history.locator("li").first()).toContainText("Ana Peña");
  });
});

for (const scenario of ["stale", "denied", "outcomeUnknown"] as const) {
  test(`Spanish authority evidence: ${scenario}`, async ({ page }) => {
    await openRecord(page, dossierFixtureIds[scenario]);
    await approveButton(page).click();
    await confirmRncWarning(page);
    const alert = recordArea(page).getByRole("alert");
    await expect(alert).toBeVisible();
    if (scenario === "stale") await expect(alert).toContainText("Este registro cambió");
    if (scenario === "denied") await expect(alert).toContainText("acceso actual");
    if (scenario === "outcomeUnknown") await expect(approveButton(page)).toBeDisabled();
    else await expect(approveButton(page)).toHaveCount(0);
    await capture(page, `${scenario}-spanish`);
  });
}

test("landing on a record, then opening Bandeja, Registros and Inicio, each loads from the Business-scoped source", async ({ page }) => {
  // The workspace derives its data source from the latch and the panel kind: the
  // first fetch after leaving the record is already scoped, so every panel loads.
  await atMidMonth(page);
  await openRecord(page, dossierFixtureIds.ready);
  const nav = page.getByTestId("business-sidebar-nav");
  const panel = page.getByTestId("workspace-panel-region");
  await nav.getByRole("button", { name: /^Bandeja/ }).click();
  await expect(page.getByRole("heading", { name: "Bandeja", exact: true, level: 1 })).toBeVisible();
  await expect(bandejaRows(page).getByRole("listitem").filter({ hasText: "Ferretería La Esquina" }).filter({ hasText: "Listo para revisar" })).toBeVisible();
  await expect(panel).not.toContainText("No pudimos cargar");
  await nav.getByRole("button", { name: /^Registros/ }).click();
  await expect(page.getByRole("heading", { name: "Registros", exact: true, level: 1 })).toBeVisible();
  await expect(panel.locator("[data-record-id]").filter({ hasText: "Nube Hosting" })).toBeVisible();
  await expect(panel).not.toContainText("No pudimos cargar");
  await nav.getByRole("button", { name: /^Inicio/ }).click();
  // The home is scoped to the Business from the first fetch: its checklist carries real counts.
  const review = panel.getByTestId("home-records-to-review");
  await expect(review).toContainText(/\d+ registros? por revisar/);
  expect(Number((await review.innerText()).match(/\d+/)![0])).toBeGreaterThan(0);
  await expect(panel).not.toContainText("No pudimos cargar");
});

test("after approving from the inbox, the inbox count changes without a reload", async ({ page }) => {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  await page.goto("/dev/business-preview");
  const nav = page.getByTestId("business-sidebar-nav");
  const panel = page.getByTestId("workspace-panel-region");
  const inbox = nav.getByRole("button", { name: /^Bandeja \d+/ });
  const badge = Number((await inbox.innerText()).match(/\d+/)![0]);
  expect(badge).toBeGreaterThan(0);
  await inbox.click();
  await reviewAction(page, /Ferretería La Esquina/).click();
  await page.getByLabel(/Pagado desde/).selectOption({ label: "Cuenta corriente · DOP" });
  await saveButton(page).click();
  await approveButton(page).click();
  await confirmRncWarning(page);
  await expect(page.getByTestId("business-record-review")).toContainText("Se registró un gasto");
  // No reload, no navigation beyond the panel switch: the home already knows.
  await nav.getByRole("button", { name: /^Inicio/ }).click();
  await expect(nav.getByRole("button", { name: `Bandeja ${badge - 1}`, exact: true })).toBeVisible();
  await nav.getByRole("button", { name: /^Registros/ }).click();
  await expect(panel.locator("[data-record-id]").filter({ hasText: "Ferretería La Esquina" })).toBeVisible();
});
