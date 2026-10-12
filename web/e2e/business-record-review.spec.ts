import { expect, test, type Page } from "@playwright/test";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

async function capture(page: Page, name: string) {
  const directory = process.env.CUADRAO_RECORD_EVIDENCE_DIR;
  if (!directory) return;
  await page.screenshot({ path: `${directory}/${name}.png`, fullPage: true });
  const facts = page.getByTestId("receipt-current-facts").getByText(/^(How it was paid|Cómo se pagó)$/);
  if (await facts.count()) {
    await facts.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${directory}/${name}-current-facts.png`, fullPage: true });
  }
}

async function openRecord(page: Page, id: string, language: "en" | "es-419" = "en") {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language, theme: "light", emptyChat: true });
  await page.goto(`/dev/business-preview?draft=${id}`);
  await expect(page.getByTestId("business-record-review")).toBeVisible();
}

for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
  test.describe(`One record at ${viewport.width}px`, () => {
    test.use({ viewport });

    test("unknown funding stays beside its original and saves before explicit approval", async ({ page }) => {
      await openRecord(page, dossierFixtureIds.unknown);
      await expect(page.getByRole("note")).toContainText("sample data");
      await expect(page.getByRole("blockquote")).toContainText("No tengo recibo");
      await expect(page.getByTestId("receipt-current-facts")).toContainText("Unknown");
      await expect(page.getByTestId("receipt-current-facts")).toContainText("Default · not verified");
      await expect(page.getByTestId("receipt-review-questions")).toContainText("How was this paid?");
      await capture(page, `unknown-funding-${viewport.width}`);
      const approve = page.getByRole("button", { name: "Approve expense", exact: true });
      await expect(approve).toBeDisabled();
      await page.getByRole("button", { name: "Edit details", exact: true }).click();
      await page.getByRole("combobox", { name: "How it was paid", exact: true }).selectOption("account:acct-ops");
      await expect(approve).toBeDisabled();
      await page.getByRole("button", { name: "Save review details", exact: true }).click();
      await expect(page.getByText("Revision 3", { exact: true })).toBeVisible();
      await expect(page.getByText("Recorded", { exact: true })).toHaveCount(0);
      await expect(approve).toBeEnabled();
      await capture(page, `ready-approval-${viewport.width}`);
      await approve.focus();
      await page.keyboard.press("Enter");
      await expect(page.getByText("One expense was recorded after approval of revision 3.", { exact: true })).toBeVisible();
      await expect(approve).toHaveCount(0);
      await expect(page.getByText("Corrections after recording aren't available in this first flow.", { exact: true })).toBeVisible();
      await page.getByTestId("receipt-history").locator("summary").click();
      await expect(page.getByTestId("receipt-history")).toContainText("Ana Peña");
      await expect(page.getByTestId("receipt-history")).toContainText("Permission granted by Lucía Mateo");
      await expect(page.getByRole("region", { name: "Web review actions" })).toBeVisible();
      await capture(page, `approved-history-${viewport.width}`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });

    test("unknown activity can be reviewed as expense before separate approval", async ({ page }) => {
      await openRecord(page, dossierFixtureIds.unknownKind);
      await expect(page.getByRole("button", { name: "Approve expense", exact: true })).toHaveCount(0);
      await page.getByRole("button", { name: "Edit details", exact: true }).click();
      await page.getByRole("combobox", { name: "Activity", exact: true }).selectOption("expense");
      await page.getByRole("button", { name: "Save review details", exact: true }).click();
      await expect(page.getByText("Revision 3", { exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "Approve expense", exact: true })).toBeEnabled();
      await expect(page.getByText("Recorded", { exact: true })).toHaveCount(0);
      await page.getByTestId("receipt-history").locator("summary").click();
      const change = page.getByTestId("receipt-history").locator("li").first();
      await expect(change).toContainText("Unknown");
      await expect(change).toContainText("Expense");
      await expect(change).toContainText("Ana Peña");
      await expect(page.getByRole("region", { name: "Web review actions" })).toBeVisible();
    });

    test("fiscal facts and before-after changes stay readable in Spanish", async ({ page }) => {
      await openRecord(page, dossierFixtureIds.fiscal, "es-419");
      const fiscal = page.getByTestId("receipt-fiscal-facts");
      await expect(fiscal).toContainText("Datos fiscales");
      await expect(fiscal).toContainText("RNC");
      await expect(fiscal).toContainText("131999888");
      await expect(fiscal).toContainText("B0100000099");
      await expect(fiscal).toContainText("e-CF");
      await expect(fiscal).toContainText("El dueño no sabe");
      await expect(fiscal).toContainText("526.27");
      await expect(fiscal).toContainText("Verificado");
      await expect(fiscal).toContainText("sin verificar");
      await page.getByTestId("receipt-history").locator("summary").click();
      const history = page.getByTestId("receipt-history");
      await expect(history).toContainText("B0100000098");
      await expect(history).toContainText("B0100000099");
      await expect(history).toContainText("100.01");
      await expect(history).toContainText("526.27");
      await expect(history).toContainText("Sin verificar → Verificado");
      await fiscal.scrollIntoViewIfNeeded();
      await capture(page, `fiscal-spanish-${viewport.width}`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });

    test("proposal-only original text is labelled as an agent proposal in Spanish", async ({ page }) => {
      await openRecord(page, dossierFixtureIds.proposal, "es-419");
      const proposal = page.getByRole("region", { name: "Propuestas del agente" });
      await expect(proposal).toContainText("Propuesta: gasto de 3,450 DOP");
      await expect(page.getByRole("region", { name: "Mensajes originales" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Aprobar gasto", exact: true })).toBeVisible();
      await proposal.scrollIntoViewIfNeeded();
      await capture(page, `proposal-spanish-${viewport.width}`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });

    test("Spanish unknown funding saves and waits for explicit human approval", async ({ page }) => {
      await openRecord(page, dossierFixtureIds.unknown, "es-419");
      await expect(page.getByTestId("receipt-current-facts")).toContainText("Predeterminada · sin verificar");
      await capture(page, `unknown-funding-spanish-${viewport.width}`);
      await page.getByRole("button", { name: "Editar detalles", exact: true }).click();
      await page.getByRole("combobox", { name: "Cómo se pagó", exact: true }).selectOption("account:acct-ops");
      await page.getByRole("button", { name: "Guardar detalles de revisión", exact: true }).click();
      await expect(page.getByText("Revisión 3", { exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "Aprobar gasto", exact: true })).toBeEnabled();
      await expect(page.getByText("Registrado", { exact: true })).toHaveCount(0);
      await capture(page, `ready-approval-spanish-${viewport.width}`);
      await page.getByRole("button", { name: "Aprobar gasto", exact: true }).click();
      await expect(page.getByText("Se registró un gasto tras aprobar la revisión 3.", { exact: true })).toBeVisible();
      await page.getByTestId("receipt-history").locator("summary").click();
      await expect(page.getByTestId("receipt-history")).toContainText("Permiso otorgado por Lucía Mateo");
      await capture(page, `approved-history-spanish-${viewport.width}`);
    });

    test("unknown money is not rendered as zero", async ({ page }) => {
      await openRecord(page, dossierFixtureIds.unknownAmount);
      await expect(page.getByText("Amount unknown", { exact: true })).toBeVisible();
      await expect(page.getByTestId("receipt-current-facts")).not.toContainText("RD$ 0.00");
    });
  });
}

test.describe("Server authority and uncertain outcomes", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("read-only grant has no edit or approval controls", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.readOnly);
    await expect(page.getByRole("button", { name: "Edit details", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Approve expense", exact: true })).toHaveCount(0);
    await expect(page.getByText("Your permission allows viewing this record.", { exact: true })).toBeVisible();
  });

  test("an untyped legacy candidate retains corrected receipt details and its source", async ({ page }) => {
    await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
    await installBreakpointFixture(page, { language: "en", theme: "light", emptyChat: true });
    await page.goto("/dev/business-preview?receipt=rcpt-papeleria");
    await expect(page.getByLabel("Merchant", { exact: true })).toHaveValue("Papelería Central");
    await expect(page.getByTestId("receipt-review-amount")).toHaveValue("980.50");
    await expect(page.getByTestId("receipt-original-source")).toBeVisible();
    await expect(page.getByTestId("workspace-panel-region").getByRole("alert")).toContainText("prepared record isn't available");
    await expect(page.getByRole("button", { name: "Approve expense", exact: true })).toHaveCount(0);
    await page.getByTestId("receipt-review-amount").fill("1020.75");
    await page.getByRole("button", { name: "Save review details", exact: true }).click();
    await expect(page.getByTestId("receipt-review-amount")).toHaveValue("1,020.75");
    await expect(page.getByTestId("workspace-panel-region").getByRole("alert")).toContainText("prepared record isn't available");
    await expect(page.getByRole("button", { name: "Approve expense", exact: true })).toHaveCount(0);
  });

  test("a direct untyped draft shows the preparation blocker without guessing a receipt", async ({ page }) => {
    await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
    await installBreakpointFixture(page, { language: "en", theme: "light", emptyChat: true });
    await page.goto(`/dev/business-preview?draft=${dossierFixtureIds.unprepared}`);
    await expect(page.getByTestId("workspace-panel-region").getByRole("alert")).toContainText("prepared record isn't available");
    await expect(page.getByRole("button", { name: "Approve expense", exact: true })).toHaveCount(0);
    await expect(page.getByTestId("receipt-original-source")).toHaveCount(0);
  });

  test("a zero total cannot be submitted after entering a valid partial business share", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.ready);
    await page.getByRole("button", { name: "Edit details", exact: true }).click();
    await page.getByTestId("dossier-review-amount").fill("0");
    await page.getByRole("combobox", { name: "Business share", exact: true }).selectOption("partial");
    const share = page.getByRole("textbox", { name: /^Business amount in DOP/ });
    await share.fill("100.00");
    await expect(page.getByRole("button", { name: "Save review details", exact: true })).toBeDisabled();
    await share.press("Enter");
    await expect(page.getByText("Revision 2", { exact: true })).toBeVisible();
    await expect(page.getByText("Revision 3", { exact: true })).toHaveCount(0);
  });

  test("owner uncertainty is saved explicitly and leaves approval blocked", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.unknown);
    await page.getByRole("button", { name: "Edit details", exact: true }).click();
    await page.getByRole("combobox", { name: "How it was paid", exact: true }).selectOption("owner_does_not_know");
    await page.getByRole("button", { name: "Save review details", exact: true }).click();
    await expect(page.getByTestId("receipt-current-facts")).toContainText("Owner doesn't know");
    await expect(page.getByRole("button", { name: "Approve expense", exact: true })).toBeDisabled();
  });

  test("stale version requires opening and reviewing the new revision", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.stale);
    await page.getByRole("button", { name: "Approve expense", exact: true }).click();
    await expect(page.getByTestId("workspace-panel-region").getByRole("alert")).toContainText("This record changed");
    await capture(page, "stale-revision");
    await expect(page.getByRole("button", { name: "Approve expense", exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "Check current record", exact: true }).click();
    await expect(page.getByText("Revision 3", { exact: true })).toBeVisible();
    await expect(page.getByTestId("receipt-current-facts")).toContainText("3,550.00");
    await expect(page.getByText("Recorded", { exact: true })).toHaveCount(0);
  });

  test("revoked grant removes action controls and the unavailable record", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.denied);
    await page.getByRole("button", { name: "Approve expense", exact: true }).click();
    await expect(page.getByTestId("workspace-panel-region").getByRole("alert")).toContainText("current access");
    await capture(page, "denied-access");
    await expect(page.getByTestId("business-record-review")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Approve expense", exact: true })).toHaveCount(0);
  });

  test("unknown approval outcome checks status without resubmitting", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.outcomeUnknown);
    await page.getByRole("button", { name: "Approve expense", exact: true }).click();
    await expect(page.getByTestId("workspace-panel-region").getByRole("alert")).toContainText("outcome isn't known");
    await expect(page.getByRole("button", { name: "Approve expense", exact: true })).toBeDisabled();
    await page.getByRole("button", { name: "Check current record", exact: true }).click();
    await expect(page.getByText("Checking approval outcome", { exact: true })).toBeVisible();
    await capture(page, "unknown-approval-outcome");
    await expect(page.getByRole("button", { name: "Approve expense", exact: true })).toBeDisabled();
    await expect(page.getByText("Recorded", { exact: true })).toHaveCount(0);
  });

  for (const scenario of ["saveUnknown", "saveConcurrent"] as const) {
    test(`uncertain save retains its correction after status read: ${scenario}`, async ({ page }) => {
      await openRecord(page, dossierFixtureIds[scenario], "es-419");
      await page.getByRole("button", { name: "Editar detalles", exact: true }).click();
      const merchant = page.getByRole("textbox", { name: "Comercio o persona", exact: true });
      await merchant.fill("My retained correction");
      await page.getByRole("button", { name: "Guardar detalles de revisión", exact: true }).click();
      await expect(page.getByTestId("workspace-panel-region").getByRole("alert")).toContainText("resultado de la acción");
      await page.getByRole("button", { name: "Consultar registro actual", exact: true }).click();
      await expect(page.getByText("Revisión 3", { exact: true })).toBeVisible();
      await expect(merchant).toHaveValue("My retained correction");
      await expect(merchant).toBeDisabled();
      await expect(page.getByRole("button", { name: "Guardar detalles de revisión", exact: true })).toBeDisabled();
      await expect(page.getByRole("button", { name: "Aprobar gasto", exact: true })).toBeDisabled();
      await expect(page.getByTestId("workspace-panel-region").getByRole("alert")).toContainText("Tus cambios se conservan");
      await expect(page.getByTestId("receipt-current-facts")).toContainText(scenario === "saveUnknown" ? "My retained correction" : "Other human correction");
      await page.getByTestId("receipt-history").locator("summary").click();
      await expect(page.getByTestId("receipt-history").locator("li")).toHaveCount(3);
      if (scenario === "saveConcurrent") await expect(page.getByTestId("receipt-history")).toContainText("Elena Reyes");
      await page.getByRole("button", { name: "Consultar registro actual", exact: true }).click();
      await expect(page.getByText("Revisión 3", { exact: true })).toBeVisible();
      await expect(merchant).toHaveValue("My retained correction");
      await capture(page, `uncertain-${scenario}-spanish`);
    });
  }

  test("acknowledged own save settles and a status read preserves its canonical revision", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.ready);
    await page.getByRole("button", { name: "Edit details", exact: true }).click();
    await page.getByRole("textbox", { name: "Merchant or person", exact: true }).fill("Acknowledged correction");
    await page.getByRole("button", { name: "Save review details", exact: true }).click();
    await expect(page.getByText("Revision 3", { exact: true })).toBeVisible();
    await expect(page.getByTestId("receipt-current-facts")).toContainText("Acknowledged correction");
    await page.getByRole("button", { name: "Check current record", exact: true }).click();
    await expect(page.getByRole("button", { name: "Approve expense", exact: true })).toBeEnabled();
    await expect(page.getByTestId("receipt-current-facts")).toContainText("Acknowledged correction");
    await page.getByRole("button", { name: "Edit details", exact: true }).click();
    await page.getByRole("textbox", { name: "Merchant or person", exact: true }).fill("New correction");
    await page.getByRole("button", { name: "Save review details", exact: true }).click();
    await expect(page.getByText("Revision 4", { exact: true })).toBeVisible();
  });

  test("income is not relabeled as an expense", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.income);
    await expect(page.getByRole("button", { name: "Approve expense", exact: true })).toHaveCount(0);
    await expect(page.getByTestId("business-record-review")).toContainText("This activity isn't supported");
  });

  test("the same current facts and approval action are localized", async ({ page }) => {
    await openRecord(page, dossierFixtureIds.ready, "es-419");
    await expect(page.getByRole("button", { name: "Aprobar gasto", exact: true })).toBeVisible();
    await expect(page.getByTestId("receipt-current-facts")).toContainText("Predeterminada · sin verificar");
    await expect(page.getByTestId("receipt-current-facts")).toContainText("Fecha de actividad");
  });
});

for (const scenario of ["stale", "denied", "outcomeUnknown"] as const) {
  test(`Spanish authority evidence: ${scenario}`, async ({ page }) => {
    await openRecord(page, dossierFixtureIds[scenario], "es-419");
    await page.getByRole("button", { name: "Aprobar gasto", exact: true }).click();
    const alert = page.getByTestId("workspace-panel-region").getByRole("alert");
    await expect(alert).toBeVisible();
    if (scenario === "stale") await expect(alert).toContainText("Este registro cambió");
    if (scenario === "denied") await expect(alert).toContainText("acceso actual");
    if (scenario === "outcomeUnknown") await expect(page.getByRole("button", { name: "Aprobar gasto", exact: true })).toBeDisabled();
    else await expect(page.getByRole("button", { name: "Aprobar gasto", exact: true })).toHaveCount(0);
    await capture(page, `${scenario}-spanish`);
  });
}

test("after approving from the inbox, the home card and the inbox count change without a reload", async ({ page }) => {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language: "en", theme: "light", emptyChat: true });
  await page.goto("/dev/business-preview");
  const nav = page.getByTestId("business-sidebar-nav");
  const panel = page.getByTestId("workspace-panel-region");
  const inboxCard = panel.getByRole("button", { name: /In your inbox/ });
  await expect(inboxCard).toBeVisible();
  const before = Number((await inboxCard.innerText()).match(/\d+/)?.[0]);
  const expensesCard = panel.getByRole("button", { name: /Saved expenses/ });
  const dopBefore = Number((await expensesCard.innerText()).match(/RD\$[^\n]*\n?(\d+) expenses?/)?.[1] ?? 0);
  await nav.getByRole("button", { name: /^Inbox/ }).click();
  await panel.getByRole("button", { name: /Ferretería La Esquina/ }).first().click();
  await page.getByLabel(/Paid from/).selectOption({ label: "Operating account · DOP" });
  await page.getByRole("button", { name: "Save review details" }).click();
  await page.getByRole("button", { name: "Approve expense", exact: true }).click();
  await expect(panel).toContainText("One expense was recorded after approval");
  // No reload, no navigation beyond the panel switch: the home already knows.
  await nav.getByRole("button", { name: /^Overview/ }).click();
  await expect(panel.getByRole("button", { name: /In your inbox/ })).toContainText(String(before - 1));
  await expect(panel.getByRole("button", { name: /Saved expenses/ })).toContainText(new RegExp(`${dopBefore + 1} expenses?`));
});
