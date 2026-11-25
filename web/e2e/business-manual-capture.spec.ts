import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import type { BusinessCaptureInput } from "../lib/business-api";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "./support/breakpoint-fixture";

const LISTED_NOTE = "Nota que pone el registro en la Bandeja";
type CaptureMode = "ok" | "lost" | "denied" | "stale" | "business_action_unsettled" | "outcome_unknown" | "conflict";
async function setup(page: Page, draftId?: string, workspaceUnavailable = false, listedDraftId?: string) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const state = { mode: "ok" as CaptureMode, notesUnavailable: false, workspaceUnavailable, starts: 0, approvals: 0, workspaceLoads: 0, captures: [] as { input: BusinessCaptureInput; key: string }[] };
  if (listedDraftId) await source.captureNote({ text: LISTED_NOTE, draft: { draft_id: listedDraftId, version: (await source.dossier(listedDraftId)).version } }, "fixture-listed-note");
  await page.route("**/api/v1/business/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.split("/business/")[1];
    const method = route.request().method();
    try {
      if (path === "space") { state.starts++; return route.fulfill({ json: { id: "fixture-space", name: "Negocio de prueba" } }); }
      if (path === "consent") return fulfillAcceptedBusinessConsent(route);
      if (path === "fiscal-profile/fields") return route.fulfill({ json: { "606": [], "607": [] } });
      if (path === "spaces") return route.fulfill({ json: { spaces: await source.spaces() } });
      if (path === "workspace") {
        state.workspaceLoads++;
        if (state.workspaceUnavailable) return route.fulfill({ status: 403, json: { detail: { code: "permission_denied", status: 403, title: "Action refused", detail: "permission_denied", request_id: "capture-test" } } });
        return route.fulfill({ json: { ...await source.workspace(), typed_notes_available: true } });
      }
      if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
      if (path === "receipts") return route.fulfill({ json: { items: [] } });
      if (path === "search") return route.fulfill({ json: await source.search(url.searchParams.get("q") ?? "") });
      if (path === "captures" && method === "GET") {
        if (state.notesUnavailable) return route.fulfill({ status: 503, json: { code: "private-internal-payload" } });
        return route.fulfill({ json: await source.captures(url.searchParams.get("q") ?? "") });
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
        if (draft[2] === "approve") {
          state.approvals++;
          const options = { acceptGaps: body.accept_gaps, suggestions: body.suggestions };
          return route.fulfill({ json: await source.approveDraft(draft[1], body.version, route.request().headers()["idempotency-key"], body.action, options) });
        }
        return route.fulfill({ json: await source.reviewDraft(draft[1], body.version, body.facts, route.request().headers()["idempotency-key"]) });
      }
      return route.fulfill({ json: { items: [] } });
    } catch (error) {
      const failure = error as { status?: number; code?: string; context?: unknown };
      return route.fulfill({ status: failure.status ?? 500, json: { code: failure.code ?? "unknown", context: failure.context } });
    }
  });
  await page.goto(`/biz${draftId ? `?draft=${draftId}` : ""}`);
  await expect(page.getByTestId("workspace-panel-region")).toBeVisible();
  return { state, source };
}

/** A record keeps "Agregar nota" in its Más menu. */
async function openAppend(page: Page) {
  await openMore(page);
  await page.getByRole("menuitem", { name: "Agregar nota", exact: true }).click();
}
/** The Bandeja row of the record `setup` listed. A record opened from its list has the workspace answer behind it. */
async function openListed(page: Page) {
  await page.getByRole("button", { name: /Bandeja/ }).first().click();
  await page.getByTestId("reception-row").filter({ hasText: LISTED_NOTE }).getByRole("button").first().click();
  await expect(page.getByTestId("business-record-review")).toBeVisible();
}
/** The approve button. A wide screen adds its keyboard shortcut to the name. */
function approveButton(page: Page) {
  return page.getByTestId("receipt-review-footer").getByRole("button", { name: /^Aceptar(?: (?:Ctrl ↵|⌘↵))?$/ });
}
async function openMore(page: Page) {
  await page.getByTestId("receipt-more").getByRole("button", { name: "Más", exact: true }).click();
}
async function screenshot(page: Page, name: string) {
  if (process.env.CUADRAO_MANUAL_EVIDENCE_DIR) await page.screenshot({ path: `${process.env.CUADRAO_MANUAL_EVIDENCE_DIR}/${name}.png`, fullPage: true });
}

for (const width of [1280, 390]) {
  test.describe(`Spanish manual notes ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });
    test("lost append response retains verbatim intent across close and explicit same-key retry without approval", async ({ page }) => {
      const { state } = await setup(page, undefined, false, dossierFixtureIds.ready);
      await openListed(page);
      await openAppend(page);
      const dialog = page.getByRole("dialog", { name: "Agregar una nota a este registro", exact: true });
      const text = "  Falta comprobar esta compra.\n  ";
      await dialog.getByRole("textbox", { name: "Nota original", exact: true }).fill(text);
      state.mode = "lost";
      await dialog.getByRole("button", { name: "Guardar nota", exact: true }).click();
      await expect(dialog.getByRole("alert")).toContainText("No pudimos confirmar");
      await expect(dialog.getByRole("textbox", { name: "Nota original", exact: true })).toHaveValue(text);
      await dialog.getByRole("button", { name: "Cerrar", exact: true }).last().click();
      await expect(approveButton(page)).toBeDisabled();
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

test.describe("a phone that lands on a record link", () => {
  test.use({ viewport: { width: 390, height: 900 } });
  test("offers no Agregar nota while the workspace answer is not loaded", async ({ page }) => {
    const { state } = await setup(page, dossierFixtureIds.ready);
    await expect(page.getByTestId("business-record-review")).toBeVisible();
    await openMore(page);
    await expect(page.getByRole("menu", { name: "Más", exact: true })).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "Agregar nota", exact: true })).toHaveCount(0);
    expect(state.workspaceLoads).toBe(0);
  });
});

test("denied and stale append preserve text, and read-only exposes no append", async ({ page }) => {
  const { state, source } = await setup(page, dossierFixtureIds.ready);
  await expect(approveButton(page)).toBeEnabled();
  await openAppend(page);
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
  await expect(approveButton(page)).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "Editar solicitud", exact: true })).toHaveCount(0);
  await dialog.getByRole("button", { name: "Cerrar", exact: true }).last().click();
  await page.getByRole("button", { name: "Volver a abrir la nota conservada", exact: true }).click();
  await expect(dialog.getByRole("textbox", { name: "Nota original", exact: true })).toHaveValue("Mi texto sin perder");
  await expect(dialog.getByRole("button", { name: "Guardar nota", exact: true })).toBeDisabled();
  expect(state.captures).toHaveLength(2);
  await page.goto(`/biz?draft=${dossierFixtureIds.readOnly}`);
  await expect(page.getByTestId("business-record-review")).toBeVisible();
  await openMore(page);
  await expect(page.getByRole("menuitem", { name: "Agregar nota", exact: true })).toHaveCount(0);
  await source.approveDraft(dossierFixtureIds.ready, 2, "fixture-explicit-approval", "record_expense");
  await page.goto(`/biz?draft=${dossierFixtureIds.ready}`);
  // An accepted record says where it went in its Historial and shows no status pill.
  await expect(page.getByTestId("receipt-review-history").getByTestId("history-sub")).toHaveText("Pasó a Registros");
  await expect(page.getByTestId("status-pill")).toHaveCount(0);
  await openMore(page);
  await expect(page.getByRole("menuitem", { name: "Agregar nota", exact: true })).toHaveCount(0);
});

test("Agregar has no door to a typed note", async ({ page }) => {
  const { state } = await setup(page);
  await page.getByTestId("business-primary-upload").click();
  const upload = page.getByRole("dialog", { name: "Agregar documentos", exact: true });
  await expect(upload.getByTestId("intake-drop-zone")).toBeVisible();
  await expect(upload).not.toContainText("Escríbelo");
  await expect(page.getByTestId("intake-write-open")).toHaveCount(0);
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
    await openAppend(page);
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
    await expect(approveButton(page)).toBeDisabled();
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
  await openAppend(page);
  const dialog = page.getByRole("dialog", { name: "Agregar una nota a este registro", exact: true });
  await dialog.getByRole("textbox", { name: "Nota original", exact: true }).fill("Texto conservado tras conflicto");
  state.mode = "conflict";
  await dialog.getByRole("button", { name: "Guardar nota", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("No se pudo guardar");
  await expect(dialog.getByRole("button", { name: "Editar solicitud", exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Reintentar la misma nota", exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("textbox", { name: "Nota original", exact: true })).toHaveValue("Texto conservado tras conflicto");
});
