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
      if (path === "fiscal-profile/fields") return route.fulfill({ json: { "606": [], "607": [] } });
      if (path === "spaces") return route.fulfill({ json: { spaces: await source.spaces() } });
      if (path === "workspace") {
        if (state.workspaceUnavailable) return route.fulfill({ status: 403, json: { detail: { code: "permission_denied", status: 403, title: "Action refused", detail: "permission_denied", request_id: "capture-test" } } });
        return route.fulfill({ json: await source.workspace() });
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
        if (draft[2] === "approve") { state.approvals++; return route.fulfill({ json: await source.approveDraft(draft[1], body.version, route.request().headers()["idempotency-key"], body.action) }); }
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

async function screenshot(page: Page, name: string) {
  if (process.env.CUADRAO_MANUAL_EVIDENCE_DIR) await page.screenshot({ path: `${process.env.CUADRAO_MANUAL_EVIDENCE_DIR}/${name}.png`, fullPage: true });
}

test("Agregar and a ready record do not offer a note entry", async ({ page }) => {
  const { state } = await setup(page);
  await page.getByTestId("business-primary-upload").click();
  const upload = page.getByRole("dialog", { name: "Agregar", exact: true });
  await expect(upload).toBeVisible();
  await expect(upload.getByTestId("intake-choose")).toBeVisible();
  await expect(upload.getByTestId("intake-write-open")).toHaveCount(0);
  await expect(upload.getByTestId("intake-write")).toHaveCount(0);
  await expect(upload.getByRole("textbox", { name: "Escríbelo" })).toHaveCount(0);
  expect(state.captures).toEqual([]);
  await page.keyboard.press("Escape");
  await page.goto(`/biz?draft=${dossierFixtureIds.ready}`);
  const record = page.getByTestId("business-record-review");
  await expect(record).toBeVisible();
  await expect(record).toContainText("Ferretería La Esquina");
  await expect(page.getByRole("button", { name: "Agregar una nota a este registro", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Guardar una nota", exact: true })).toHaveCount(0);
  await expect(page.getByRole("dialog", { name: "Agregar una nota a este registro" })).toHaveCount(0);
  await expect(record.getByRole("button", { name: "Aprobar", exact: true })).toBeVisible();
});

test("an unavailable workspace still opens Agregar without a note entry", async ({ page }) => {
  const { state } = await setup(page, undefined, true);
  await expect(page.getByTestId("workspace-panel-region").getByRole("heading", { name: "Cuadrao Business aún no está disponible para tu cuenta." })).toBeVisible();
  await page.getByTestId("business-primary-upload").click();
  await expect(page.getByRole("dialog", { name: "Agregar", exact: true })).toBeVisible();
  await expect(page.getByTestId("intake-write-open")).toHaveCount(0);
  await expect(page.getByTestId("intake-write")).toHaveCount(0);
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


