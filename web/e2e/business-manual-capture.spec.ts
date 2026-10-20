import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import type { BusinessCaptureInput } from "../lib/business-api";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "./support/breakpoint-fixture";

type CaptureMode = "ok" | "lost" | "denied" | "stale" | "business_action_unsettled" | "outcome_unknown" | "conflict";
async function setup(page: Page, draftId?: string, workspaceUnavailable = false) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const state = { mode: "ok" as CaptureMode, notesUnavailable: false, workspaceUnavailable, starts: 0, approvals: 0, captures: [] as { input: BusinessCaptureInput; key: string }[] };
  await page.route("**/api/v1/business/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.split("/business/")[1];
    const method = route.request().method();
    try {
      if (path === "space") { state.starts++; return route.fulfill({ json: { id: "fixture-space", name: "Negocio de prueba" } }); }
      if (path === "consent") return fulfillAcceptedBusinessConsent(route);
      if (path === "workspace") {
        if (state.workspaceUnavailable) return route.fulfill({ status: 403, json: { detail: { code: "permission_denied", status: 403, title: "Action refused", detail: "permission_denied", request_id: "capture-test" } } });
        return route.fulfill({ json: await source.workspace() });
      }
      if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
      if (path === "receipts") return route.fulfill({ json: { items: [] } });
      if (path === "search") return route.fulfill({ json: await source.search(url.searchParams.get("q") ?? "") });
      if (path === "captures" && method === "GET") {
        if (state.notesUnavailable) return route.fulfill({ status: 503, json: { code: "private-internal-payload" } });
        return route.fulfill({ json: { items: await source.captures(url.searchParams.get("q") ?? "") } });
      }
      if (path === "captures") {
        const input = route.request().postDataJSON() as BusinessCaptureInput;
        const key = route.request().headers()["idempotency-key"];
        state.captures.push({ input, key });
        if (state.mode === "denied") return route.fulfill({ status: 403, json: { detail: { code: "permission_denied", status: 403, title: "Action refused", detail: "permission_denied", request_id: "capture-test" } } });
        if (state.mode === "stale") return route.fulfill({ status: 409, json: { detail: { code: "stale_version", status: 409, title: "Action refused", detail: "stale_version", request_id: "capture-test" } } });
        if (state.mode === "conflict") return route.fulfill({ status: 409, json: { detail: { code: "idempotency_conflict", status: 409, title: "Action refused", detail: "idempotency_conflict", request_id: "capture-test" } } });
        const result = await source.captureNote(input, key);
        if (state.mode === "business_action_unsettled" || state.mode === "outcome_unknown") {
          const code = state.mode;
          state.mode = "ok";
          return route.fulfill({ status: 409, json: { detail: { type: `https://api.argus.app/problems/${code.replaceAll("_", "-")}`, title: "Capture outcome unknown", status: 409, detail: code, code, request_id: "capture-test" } } });
        }
        if (state.mode === "lost") { state.mode = "ok"; return route.abort("failed"); }
        return route.fulfill({ json: result });
      }
      const draft = path.match(/^drafts\/([^/]+)\/(dossier|approve|review)$/);
      if (draft) {
        if (draft[2] === "dossier") return route.fulfill({ json: await source.dossier(draft[1]) });
        const body = route.request().postDataJSON();
        if (draft[2] === "approve") { state.approvals++; return route.fulfill({ json: await source.approveDraft(draft[1], body.version, route.request().headers()["idempotency-key"]) }); }
        return route.fulfill({ json: await source.reviewDraft(draft[1], body.version, body.facts, route.request().headers()["idempotency-key"]) });
      }
      return route.fulfill({ json: { items: [] } });
    } catch (error) {
      const failure = error as { status?: number; code?: string };
      return route.fulfill({ status: failure.status ?? 500, json: { code: failure.code ?? "unknown" } });
    }
  });
  await page.goto(`/biz${draftId ? `?draft=${draftId}` : ""}`);
  await expect(page.getByTestId("workspace-panel-region")).toBeVisible();
  return { state, source };
}

async function newNote(page: Page) {
  const create = page.getByTestId("business-create");
  const compact = page.getByTestId("business-create-compact");
  await (await compact.isVisible() ? compact : create).click();
  await page.getByRole("menuitem", { name: "Guardar una nota", exact: true }).click();
  return page.getByRole("dialog", { name: "Guardar una nota", exact: true });
}
async function screenshot(page: Page, name: string) {
  if (process.env.CUADRAO_MANUAL_EVIDENCE_DIR) await page.screenshot({ path: `${process.env.CUADRAO_MANUAL_EVIDENCE_DIR}/${name}.png`, fullPage: true });
}

for (const width of [1280, 390]) {
  test.describe(`Spanish manual notes ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });
    test("original sparse note opens canonical review, appends and returns through note search", async ({ page }) => {
      const { state } = await setup(page);
      const dialog = await newNote(page);
      const original = "  Ayer compré pintura para el taller.\nNo sé cuánto pagué.  ";
      await dialog.getByRole("textbox", { name: "Nota original", exact: true }).fill("  ");
      await expect(dialog.getByRole("button", { name: "Guardar nota", exact: true })).toBeDisabled();
      await dialog.getByRole("textbox", { name: "Nota original", exact: true }).fill(original);
      const starts = state.starts;
      await dialog.getByRole("button", { name: "Guardar nota", exact: true }).click();
      const record = page.getByTestId("business-record-review");
      await expect(record).toBeVisible();
      await expect(record.getByRole("blockquote")).toHaveText(original);
      await expect(record).toContainText("Monto desconocido");
      expect(state.captures[0].input).toEqual({ text: original });
      expect(state.starts).toBe(starts);
      expect(state.approvals).toBe(0);
      await screenshot(page, `sparse-original-${width}`);
      await record.getByRole("button", { name: "Agregar una nota a este registro", exact: true }).click();
      const append = page.getByRole("dialog", { name: "Agregar una nota a este registro", exact: true });
      await append.getByRole("textbox", { name: "Nota original", exact: true }).fill("Pagué con mi dinero %_");
      await append.getByRole("button", { name: "Guardar nota", exact: true }).click();
      await expect(record).toContainText("Pagué con mi dinero %_");
      expect(state.captures[1].input.draft?.version).toBe(1);
      expect(state.captures[1].key).not.toBe(state.captures[0].key);
      expect(state.approvals).toBe(0);
      // From the tablet stop up search is the top bar's field; a phone keeps Buscar in its drawer.
      if (width < 720) {
        await page.getByRole("button", { name: "Abrir barra lateral", exact: true }).click();
        await page.getByRole("button", { name: /^(Buscar|Search)/ }).first().click();
      } else await page.getByTestId("header-search").click();
      await page.getByPlaceholder("Busca comercio, monto o nota").fill("pintura");
      const hit = page.getByTestId("workspace-search-results").getByRole("button", { name: /Ayer compré pintura/ });
      await expect(hit).toContainText("Nota original guardada");
      await hit.click();
      await expect(record).toContainText("Pagué con mi dinero %_");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
    test("lost append response retains verbatim intent across close and explicit same-key retry without approval", async ({ page }) => {
      const { state } = await setup(page, dossierFixtureIds.ready);
      await page.getByRole("button", { name: "Agregar una nota a este registro", exact: true }).click();
      const dialog = page.getByRole("dialog", { name: "Agregar una nota a este registro", exact: true });
      const text = "  Falta comprobar esta compra.\n  ";
      await dialog.getByRole("textbox", { name: "Nota original", exact: true }).fill(text);
      state.mode = "lost";
      await dialog.getByRole("button", { name: "Guardar nota", exact: true }).click();
      await expect(dialog.getByRole("alert")).toContainText("No pudimos confirmar");
      await expect(dialog.getByRole("textbox", { name: "Nota original", exact: true })).toHaveValue(text);
      await dialog.getByRole("button", { name: "Cerrar", exact: true }).last().click();
      await expect(page.getByRole("button", { name: "Aprobar gasto", exact: true })).toBeDisabled();
      expect(state.captures).toHaveLength(1);
      await page.getByRole("button", { name: "Volver a abrir la nota sin confirmar", exact: true }).click();
      await screenshot(page, `uncertain-retained-${width}`);
      await dialog.getByRole("button", { name: "Reintentar la misma nota", exact: true }).click();
      await expect(page.getByTestId("business-record-review")).toContainText(text.trim());
      expect(state.captures[1]).toEqual(state.captures[0]);
      expect(state.approvals).toBe(0);
    });
  });
}

test("denied and stale append preserve text, and read-only exposes no append", async ({ page }) => {
  const { state, source } = await setup(page, dossierFixtureIds.ready);
  await page.getByRole("button", { name: "Agregar una nota a este registro", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Agregar una nota a este registro", exact: true });
  await dialog.getByRole("textbox", { name: "Nota original", exact: true }).fill("Mi texto sin perder");
  state.mode = "stale";
  await dialog.getByRole("button", { name: "Guardar nota", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("Este registro cambió");
  await expect(dialog.getByRole("textbox", { name: "Nota original", exact: true })).toHaveValue("Mi texto sin perder");
  state.mode = "denied";
  await dialog.getByRole("button", { name: "Editar solicitud", exact: true }).click();
  await dialog.getByRole("button", { name: "Guardar nota", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("Tu acceso actual");
  await expect(dialog.getByRole("textbox", { name: "Nota original", exact: true })).toHaveValue("Mi texto sin perder");
  await expect(page.getByRole("button", { name: "Aprobar gasto", exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "Editar solicitud", exact: true })).toHaveCount(0);
  await dialog.getByRole("button", { name: "Cerrar", exact: true }).last().click();
  await page.getByRole("button", { name: "Volver a abrir la nota conservada", exact: true }).click();
  await expect(dialog.getByRole("textbox", { name: "Nota original", exact: true })).toHaveValue("Mi texto sin perder");
  await expect(dialog.getByRole("button", { name: "Guardar nota", exact: true })).toBeDisabled();
  expect(state.captures).toHaveLength(2);
  await page.goto(`/biz?draft=${dossierFixtureIds.readOnly}`);
  await expect(page.getByTestId("business-record-review")).toBeVisible();
  await expect(page.getByRole("button", { name: "Agregar una nota a este registro", exact: true })).toHaveCount(0);
  await source.approveDraft(dossierFixtureIds.ready, 2, "fixture-explicit-approval");
  await page.goto(`/biz?draft=${dossierFixtureIds.ready}`);
  await expect(page.getByTestId("business-record-review")).toContainText("Se registró un gasto");
  await expect(page.getByRole("button", { name: "Agregar una nota a este registro", exact: true })).toHaveCount(0);
});

test("new-note entry waits for successful own-workspace load", async ({ page }) => {
  const { state } = await setup(page, undefined, true);
  await expect(page.getByTestId("workspace-panel-region").getByRole("alert")).toBeVisible();
  await page.getByTestId("business-create").click();
  await expect(page.getByRole("menuitem", { name: "Guardar una nota", exact: true })).toHaveCount(0);
  expect(state.captures).toEqual([]);
});

test("notes unavailable preserves Spanish real record search and displays an honest partial error", async ({ page }) => {
  const { state } = await setup(page);
  state.notesUnavailable = true;
  await page.getByTestId("header-search").click();
  await page.getByPlaceholder("Busca comercio, monto o nota").fill("comedor");
  const results = page.getByTestId("workspace-search-results");
  await expect(results.getByRole("button", { name: /Comedor Doña Ana/ })).toBeVisible();
  await expect(results.getByRole("alert")).toContainText("Las notas no están disponibles");
  await expect(results).not.toContainText("private-internal-payload");
  await screenshot(page, "notes-outage-real-records-spanish");
});


for (const code of ["business_action_unsettled", "outcome_unknown"] as const) {
  test(`nested Problem 409 ${code} retains the original command until explicit same-key settlement`, async ({ page }) => {
    const { state, source } = await setup(page, dossierFixtureIds.ready);
    const before = await source.dossier(dossierFixtureIds.ready);
    await page.getByRole("button", { name: "Agregar una nota a este registro", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Agregar una nota a este registro", exact: true });
    const original = "  Nota que puede haberse guardado.\n  ";
    await dialog.getByRole("textbox", { name: "Nota original", exact: true }).fill(original);
    state.mode = code;
    await dialog.getByRole("button", { name: "Guardar nota", exact: true }).click();
    await expect(dialog.getByRole("alert")).toContainText("No pudimos confirmar");
    await expect(dialog.getByRole("textbox", { name: "Nota original", exact: true })).toHaveValue(original);
    await expect(dialog.getByRole("button", { name: "Editar solicitud", exact: true })).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: "Reintentar la misma nota", exact: true })).toBeEnabled();
    await dialog.getByRole("button", { name: "Cerrar", exact: true }).last().click();
    await expect(page.getByRole("button", { name: "Aprobar gasto", exact: true })).toBeDisabled();
    await page.getByRole("button", { name: "Consultar registro actual", exact: true }).click();
    await expect(page.getByRole("button", { name: "Aprobar gasto", exact: true })).toBeDisabled();
    expect(state.captures).toHaveLength(1);
    await page.getByRole("button", { name: "Volver a abrir la nota sin confirmar", exact: true }).click();
    await dialog.getByRole("button", { name: "Reintentar la misma nota", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(state.captures[1]).toEqual(state.captures[0]);
    const settled = await source.dossier(before.draft_id);
    expect(settled.version).toBe(before.version + 1);
    expect(settled.sources.filter((item) => "text" in item && item.text === original)).toHaveLength(1);
    expect(state.approvals).toBe(0);
  });
}

test("nested idempotency conflict is a refusal with editable retained text, not uncertain retry", async ({ page }) => {
  const { state } = await setup(page, dossierFixtureIds.ready);
  await page.getByRole("button", { name: "Agregar una nota a este registro", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Agregar una nota a este registro", exact: true });
  await dialog.getByRole("textbox", { name: "Nota original", exact: true }).fill("Texto conservado tras conflicto");
  state.mode = "conflict";
  await dialog.getByRole("button", { name: "Guardar nota", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("No se pudo guardar");
  await expect(dialog.getByRole("button", { name: "Editar solicitud", exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Reintentar la misma nota", exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("textbox", { name: "Nota original", exact: true })).toHaveValue("Texto conservado tras conflicto");
});
