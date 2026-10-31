import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium, expect } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "../e2e/support/breakpoint-fixture";
import { monthCloseWire } from "../e2e/support/month-close-wire";
import { fulfillSyntheticBusinessFallback } from "../e2e/support/synthetic-business-fallback";
import { designServerFieldsReception } from "../e2e/support/design-server-fields-reception";

const baseURL = process.env.EVIDENCE_BASE_URL ?? "http://127.0.0.1:3198";
if (!["127.0.0.1", "localhost"].includes(new URL(baseURL).hostname)) throw new Error("Evidence requires a local server");
const stage = process.env.EVIDENCE_STAGE ?? "after";
const head = execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
const output = resolve(process.env.EVIDENCE_OUTPUT ?? "../temp/lucas-design-server-fields", stage);
mkdirSync(output, { recursive: true });
const cases = process.env.EVIDENCE_CASE === "receipt" ? ["inicio-receipts-failed"] : ["inicio-business-refused", "inicio-month-500", "inicio-open-items-refused", "inicio-month-refused", "bandeja-al-dia", "bandeja-mixed", "bandeja-refused", "inicio-receipts-failed", "inicio-known-zero", "inicio-receipts-loading", "inicio-receipts-refused", "inicio-receipts-unknown", "inicio-receipts-tasks"];
const receiptChecks: { state: string; width: number; retry: boolean; recovered?: boolean; reads_before?: number; reads_after?: number }[] = [];
const retryChecks: { width: number; notes_before: number; notes_after: number; emails_before: number; emails_after: number }[] = [];
const evidence: { file: string; sha256: string; state: string; width: number; ready: boolean; close: boolean }[] = [];
const browser = await chromium.launch({ headless: true });
try {
  for (const state of cases) {
    for (const width of [1440, 390]) {
      const page = await browser.newPage({ viewport: { width, height: width === 390 ? 844 : 1000 }, reducedMotion: "reduce" });
      const unexpected: string[] = [];
      await page.route("**/*", (route) => {
        const url = new URL(route.request().url());
        if (url.origin === new URL(baseURL).origin) return route.continue();
        unexpected.push(url.origin);
        return route.abort();
      });
      await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
      const source = createFixtureBusinessDataSource({ chatAvailable: false });
      const spaces = (await source.spaces()).slice(0, 1);
      const calls = { notes: 0, emails: 0, receipts: 0 };
      let receiptsDown = true;
      let releaseReceipts = () => {};
      const receiptRead = new Promise<void>((resolve) => { releaseReceipts = resolve; });
      let emailsDown = true;
      await page.route("**/api/v1/business/**", async (route) => {
        const url = new URL(route.request().url());
        const path = url.pathname.split("/business/")[1];
        const refuse = (status = 404, code = "business_unavailable") => route.fulfill({ status, json: { code, request_id: "4ea79978-ce17-4853-b232-b2a72f4c9ce7" } });
        if (state === "inicio-business-refused" && path === "overview") return refuse();
        if (state === "inicio-month-refused" && path === "month-close") return refuse();
        if (state === "inicio-month-500" && path === "month-close") return refuse(500, "internal_error");
        if (state === "inicio-open-items-refused" && path === "open-items") return refuse();
        if (path === "receipts") {
          calls.receipts += 1;
          if ((state === "inicio-receipts-failed" || state === "inicio-receipts-tasks") && receiptsDown) return route.abort("connectionfailed");
          if (state === "inicio-receipts-refused") return refuse();
          if (state === "inicio-receipts-loading") await receiptRead;
          if (state === "inicio-receipts-unknown") return route.fulfill({ json: { items: [], activity: null } });
        }
        if ((state === "bandeja-refused" || state === "bandeja-mixed") && path === "captures") { calls.notes += 1; return refuse(); }
        if (state === "bandeja-refused" && path === "email/deliveries") return refuse(503, "email_capture_unavailable");
        if (state === "bandeja-mixed" && path === "email/deliveries") { calls.emails += 1; return emailsDown ? refuse(500, "internal_error") : route.fulfill({ json: { items: [] } }); }
        if (path === "workspace") return route.fulfill({ json: await source.workspace() });
        if (path === "space/name-prompt") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de prueba", name_required: false, name_prompt_seen: true, show_prompt: false } });
        if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de prueba" } });
        if (path === "spaces") return route.fulfill({ json: { spaces } });
        if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
        if (state === "bandeja-al-dia" && path === "receipts") return route.fulfill({ json: { items: [await source.receipt("rcpt-confirmed")], activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 0, ready_to_review_count: 0, needs_attention_count: 0, confirmed_count: 1, dismissed_count: 0 } } });
        if (path === "receipts") return route.fulfill({ json: { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 0, ready_to_review_count: 0, needs_attention_count: 0, confirmed_count: 0, dismissed_count: 0 } } });
        if (path === "receipt-reading") return route.fulfill({ json: { enabled: true, available: true, can_change: false } });
        if (path === "email") return route.fulfill({ json: { enabled: true, receiving_address: "recibos@example.test" } });
        if (path === "email/inbox" && route.request().method() === "GET") return route.fulfill({ json: { groups: [{ id: "remitentes_nuevos", items: [] }, { id: "bandeja", items: [] }] } });
        if (path === "captures" || path === "email/deliveries") return route.fulfill({ json: { items: [] } });
        if (path === "consent") return fulfillAcceptedBusinessConsent(route);
        if (path === "month-close") {
          const wire = monthCloseWire(url.searchParams.get("month") ?? "2026-10");
          if (state === "inicio-receipts-tasks") return route.fulfill({ json: wire });
          return route.fulfill({ json: { ...wire, cuentas_por_cobrar: [], currencies: wire.currencies.map((block) => ({ ...block, net_result_final: true, by_status: { invoices: { pendiente: { count: 0, before_itbis_minor: 0 }, cobrado: { count: 1, before_itbis_minor: 5000000 } }, receipts: { pendiente: { count: 0, before_itbis_minor: 0 }, pagado: { count: 0, before_itbis_minor: 0 } } } })) } });
        }
        if (path === "open-items") {
          const none = { count: 0, totals: [], overdue: { count: 0, totals: [] }, items: [] };
          return route.fulfill({ json: { today: "2026-10-21", cuentas_por_cobrar: none, cuentas_por_pagar: none } });
        }
        if (path === "invitations") return route.fulfill({ json: [] });
        if (path === "spaces/fixture-space/profile") return route.fulfill({ json: { space_id: "fixture-space", name: "Colmado de prueba", country: "DO", currency: "DOP", revision: 0, details: {}, appearance: { kind: "default" }, image: null } });
        return fulfillSyntheticBusinessFallback(route);
      });
      const selectedSources = state === "bandeja-mixed" ? Promise.all(
        ([["captures", 404], ["email/deliveries", 500]] as const).map(([path, status]) => page.waitForResponse(response =>
          new URL(response.url()).pathname === `/api/v1/business/${path}`
          && response.request().method() === "GET"
          && response.request().headers()["x-business-grant"] === spaces[0].grant_id
          && response.status() === status)),
      ) : null;
      await page.goto(`${baseURL}/biz${state.startsWith("bandeja") ? "?view=inbox" : ""}`);
      const reception = page.locator(designServerFieldsReception.root);
      const receptionViews = reception.locator(designServerFieldsReception.views);
      const receptionAlert = reception.locator(designServerFieldsReception.alert);
      if (state.startsWith("bandeja")) {
        await expect(reception).toBeVisible();
        await expect(reception).toHaveAttribute("data-mode", "live");
        await expect(receptionViews).toBeVisible();
      } else {
        await expect(page.getByTestId("month-close")).toBeVisible();
      }
      if (state === "inicio-business-refused" || state === "inicio-receipts-failed") await expect(page.getByTestId("inicio-error")).toBeVisible();
      if (state === "inicio-month-refused" || state === "inicio-month-500") await expect(page.getByTestId("month-close-error")).toBeVisible();
      if (state === "inicio-open-items-refused") await expect(page.getByTestId("month-close-money-error")).toBeVisible();
      if (state === "bandeja-al-dia") {
        const all = receptionViews.locator(designServerFieldsReception.tabs.all);
        const review = receptionViews.locator(designServerFieldsReception.tabs.review);
        const rows = reception.locator(designServerFieldsReception.row);
        const empty = reception.locator(designServerFieldsReception.empty);
        await expect(all).toHaveAttribute("aria-selected", "true");
        await expect(receptionAlert).toHaveCount(0);
        await expect(rows).toHaveCount(1);
        await expect(rows).toContainText("Nube Hosting");
        await expect(rows).toBeVisible();
        await expect(empty).toHaveCount(0);
        for (const [key, label] of [["review", "Por revisar"], ["processing", "En proceso"], ["attention", "Necesitan atención"]] as const) {
          await expect(receptionViews.locator(designServerFieldsReception.tabs[key])).toHaveText(new RegExp(`^${label}\\s*0$`));
        }
        await review.click();
        await expect(review).toHaveAttribute("aria-selected", "true");
        await expect(empty).toBeVisible();
        await expect(empty).toHaveAttribute("data-empty-kind", "filtered");
        await expect(empty.getByRole("heading")).toHaveText("No hay contenido en esta vista");
        await expect(empty).toContainText("Prueba otra vista o cambia los filtros.");
        await expect(rows).toHaveCount(0);
        await empty.getByRole("button", { name: "Limpiar filtros", exact: true }).click();
        await expect(all).toHaveAttribute("aria-selected", "true");
        await expect(empty).toHaveCount(0);
        await expect(rows).toHaveCount(1);
        await expect(rows).toContainText("Nube Hosting");
        await expect(rows).toBeVisible();
      }
      if (state === "bandeja-mixed") {
        await expect(receptionAlert).toContainText("No pudimos cargar tus notas ni tus correos.");
        await expect(receptionAlert.getByRole("button", { name: "Reintentar", exact: true })).toBeVisible();
        await expect(receptionAlert).not.toContainText("hola@cuadrao.ai");
      }
      if (state === "bandeja-refused") {
        await expect(receptionAlert).toContainText("No pudimos cargar tus notas ni tus correos.");
        await expect(receptionAlert.getByText(/hola@cuadrao.ai/)).toBeVisible();
        await expect(receptionAlert).not.toContainText("conexión");
        await expect(receptionAlert.getByRole("button", { name: "Reintentar", exact: true })).toHaveCount(0);
      }
      if (state === "inicio-receipts-failed") {
        await expect(page.getByTestId("month-close-checklist")).toBeVisible();
        await expect(page.getByTestId("month-close-checklist-ready")).toHaveCount(stage === "before" ? 1 : 0);
        await expect(page.getByTestId("month-close-close")).toHaveCount(stage === "before" ? 1 : 0);
      }
      if (state.startsWith("inicio-receipts-") && stage !== "before") {
        const status = page.getByTestId("month-close-receipts-status");
        await expect(status).toBeVisible();
        const retry = status.getByRole("button", { name: "Reintentar", exact: true });
        const failed = state === "inicio-receipts-failed" || state === "inicio-receipts-tasks";
        await expect(retry).toHaveCount(failed ? 1 : 0);
        await expect(status).toContainText(state === "inicio-receipts-loading" ? "Cargando el conteo de recibos." : state === "inicio-receipts-refused" ? "Cuadrao Business aún no está disponible para tu cuenta." : state === "inicio-receipts-unknown" ? "El conteo de recibos no está disponible." : "No pudimos cargar el conteo de recibos.");
        await expect(page.getByTestId("month-close-close")).toHaveCount(0);
        await expect(page.getByTestId("month-close-checklist-ready")).toHaveCount(0);
        if (width === 390) {
          const box = await status.boundingBox();
          expect(box).not.toBeNull();
          expect(box!.y).toBeGreaterThanOrEqual(0);
          expect(box!.y + box!.height, "receipt reason and retry stay on the first phone screen").toBeLessThanOrEqual(780);
        }
        if (failed) await expect(page.getByTestId("inicio-error")).toHaveCount(1);
        if (state === "inicio-receipts-tasks") {
          const checklist = page.getByTestId("month-close-checklist");
          const disclosure = checklist.getByRole("button", { name: "Ver cuáles", exact: true });
          await expect(disclosure).toHaveAttribute("aria-expanded", "false");
          await disclosure.click();
          await expect(checklist.getByRole("button", { name: "Ocultar", exact: true })).toHaveAttribute("aria-expanded", "true");
          await expect(page.getByTestId("month-close-task-settle")).toBeVisible();
          await expect(page.getByTestId("month-close-steps-note")).toHaveCount(0);
        }
        receiptChecks.push({ state, width, retry: failed });
      }
      if (state === "inicio-known-zero") {
        await expect(page.getByTestId("month-close-checklist-ready")).toBeVisible();
        await expect(page.getByTestId("month-close-close")).toBeVisible();
      }
      for (const id of ["inicio-error", "month-close-error", "month-close-money-error"]) {
        const error = page.getByTestId(id);
        if (state.includes("refused") && await error.count()) {
          await expect(error).not.toContainText("conexión");
          await expect(error.getByRole("button", { name: "Reintentar", exact: true })).toHaveCount(0);
        }
      }
      if (state === "inicio-month-500") await expect(page.getByTestId("month-close-error").getByRole("button", { name: "Reintentar", exact: true })).toBeVisible();
      if (state === "bandeja-refused" || state === "bandeja-mixed") {
        for (const [key, label] of [["review", "Por revisar"], ["processing", "En proceso"], ["attention", "Necesitan atención"]] as const) {
          await expect(receptionViews.locator(designServerFieldsReception.tabs[key])).toHaveText(new RegExp(`^${label}\\s*-$`));
        }
        await expect(reception.locator(designServerFieldsReception.empty)).toHaveCount(0);
      }
      await page.evaluate((label) => {
        const stamp = document.createElement("div");
        stamp.textContent = label;
        stamp.style.cssText = "position:fixed;bottom:8px;right:8px;background:#fff;color:#111;border:1px solid #999;padding:4px 8px;z-index:99999;font:11px sans-serif";
        document.body.append(stamp);
      }, `Synthetic fixture proof · ${head.slice(0, 7)}`);
      const file = `${state}-${width}.png`;
      await page.screenshot({ path: resolve(output, file), fullPage: true });
      evidence.push({ file, sha256: createHash("sha256").update(readFileSync(resolve(output, file))).digest("hex"), state, width, ready: await page.getByTestId("month-close-checklist-ready").count() > 0, close: await page.getByTestId("month-close-close").count() > 0 });
      if (state === "inicio-receipts-failed") {
        await page.getByTestId("inicio-error").scrollIntoViewIfNeeded();
        const detail = `${state}-${width}-error-detail.png`;
        await page.screenshot({ path: resolve(output, detail), fullPage: true });
        evidence.push({ file: detail, sha256: createHash("sha256").update(readFileSync(resolve(output, detail))).digest("hex"), state, width, ready: await page.getByTestId("month-close-checklist-ready").count() > 0, close: await page.getByTestId("month-close-close").count() > 0 });
      }
      if (state === "inicio-receipts-failed" && stage !== "before") {
        const before = calls.receipts;
        receiptsDown = false;
        await page.getByTestId("month-close-receipts-status").getByRole("button", { name: "Reintentar", exact: true }).click();
        await expect(page.getByTestId("month-close-receipts-status")).toHaveCount(0);
        await expect(page.getByTestId("month-close-checklist-ready")).toBeVisible();
        await expect(page.getByTestId("month-close-close")).toBeVisible();
        expect(calls.receipts).toBeGreaterThan(before);
        receiptChecks.push({ state, width, retry: true, recovered: true, reads_before: before, reads_after: calls.receipts });
        const recovered = `${state}-${width}-recovered.png`;
        await page.screenshot({ path: resolve(output, recovered), fullPage: true });
        evidence.push({ file: recovered, sha256: createHash("sha256").update(readFileSync(resolve(output, recovered))).digest("hex"), state: "inicio-receipts-recovered", width, ready: true, close: true });
      }
      releaseReceipts();
      if (state === "inicio-receipts-loading") await expect(page.getByTestId("month-close-checklist-ready")).toBeVisible();
      if (state === "bandeja-mixed") {
        await selectedSources;
        const before = { ...calls };
        emailsDown = false;
        await receptionAlert.getByRole("button", { name: "Reintentar", exact: true }).click();
        await expect(receptionAlert).toContainText("No pudimos cargar tus notas.");
        await expect(receptionAlert).not.toContainText("correos");
        await expect(receptionAlert).toContainText("hola@cuadrao.ai");
        await expect(receptionAlert).not.toContainText("conexión");
        await expect(receptionAlert.getByRole("button", { name: "Reintentar", exact: true })).toHaveCount(0);
        expect(calls.notes, "permanently refused notes are not retried").toBe(before.notes);
        expect(calls.emails, "only transient email failure is retried").toBeGreaterThan(before.emails);
        retryChecks.push({ width, notes_before: before.notes, notes_after: calls.notes, emails_before: before.emails, emails_after: calls.emails });
      }
      expect(unexpected, "all requests stay local").toEqual([]);
      await page.close();
    }
  }
} catch (error) {
  for (const context of browser.contexts()) for (const page of context.pages()) console.error(await page.locator("body").innerText());
  throw error;
} finally {
  await browser.close();
  writeFileSync(resolve(output, "manifest.json"), JSON.stringify({ head, stage, proof: "synthetic fixture proof", generated_at: new Date().toISOString(), retryChecks, receiptChecks, evidence }, null, 2));
}
console.log(`Captured ${evidence.length} synthetic screenshots at ${head}`);
