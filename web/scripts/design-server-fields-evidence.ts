import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium, expect } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "../e2e/support/breakpoint-fixture";
import { monthCloseWire, OPEN_ITEMS_WIRE } from "../e2e/support/month-close-wire";
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
const monthChecks: { width: number; reads_before: number; reads_after: number }[] = [];
const retryChecks: { width: number; notes_before: number; notes_after: number; emails_before: number; emails_after: number }[] = [];
const evidence: { file: string; sha256: string; state: string; width: number }[] = [];
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
      const calls = { notes: 0, emails: 0, receipts: 0, month: 0 };
      let receiptsDown = true;
      let releaseReceipts = () => {};
      const receiptRead = new Promise<void>((resolve) => { releaseReceipts = resolve; });
      let emailsDown = true;
      let monthDown = true;
      // Por cobrar and Por pagar exist only while the server's settlement is on.
      const settles = state === "inicio-open-items-refused" || state === "inicio-receipts-tasks";
      await page.route("**/api/v1/business/**", async (route) => {
        const url = new URL(route.request().url());
        const path = url.pathname.split("/business/")[1];
        const refuse = (status = 404, code = "business_unavailable") => route.fulfill({ status, json: { code, request_id: "4ea79978-ce17-4853-b232-b2a72f4c9ce7" } });
        if (state === "inicio-business-refused" && path === "overview") return refuse();
        if (state === "inicio-month-refused" && path === "month-close") return refuse();
        if (state === "inicio-month-500" && path === "month-close") { calls.month += 1; if (monthDown) return refuse(500, "internal_error"); }
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
        if (path === "workspace") return route.fulfill({ json: settles ? { ...await source.workspace(), settlement_available: true } : await source.workspace() });
        if (path === "space/name-prompt") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de prueba", name_required: false, name_prompt_seen: true, show_prompt: false } });
        if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de prueba" } });
        if (path === "spaces") return route.fulfill({ json: { spaces } });
        if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
        if (state === "bandeja-al-dia" && path === "receipts") return route.fulfill({ json: { items: [await source.receipt("rcpt-confirmed")], activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 0, ready_to_review_count: 0, needs_attention_count: 0, confirmed_count: 1, dismissed_count: 0, bandeja_listo_count: 0, bandeja_attention_count: 0 } } });
        if (path === "receipts") return route.fulfill({ json: { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 0, ready_to_review_count: 0, needs_attention_count: 0, confirmed_count: 0, dismissed_count: 0, bandeja_listo_count: 0, bandeja_attention_count: 0 } } });
        if (path === "receipt-reading") return route.fulfill({ json: { enabled: true, available: true, can_change: false } });
        if (path === "email") return route.fulfill({ json: { enabled: true, receiving_address: "recibos@example.test" } });
        if (path === "captures" || path === "email/deliveries" || path === "email/senders") return route.fulfill({ json: { items: [] } });
        if (path === "consent") return fulfillAcceptedBusinessConsent(route);
        if (path === "month-close") {
          const wire = monthCloseWire(url.searchParams.get("month") ?? "2026-10");
          if (state === "inicio-receipts-tasks") return route.fulfill({ json: wire });
          return route.fulfill({ json: { ...wire, cuentas_por_cobrar: [], currencies: wire.currencies.map((block) => ({ ...block, net_result_final: true, by_status: { invoices: { pendiente: { count: 0, before_itbis_minor: 0 }, cobrado: { count: 1, before_itbis_minor: 5000000 } }, receipts: { pendiente: { count: 0, before_itbis_minor: 0 }, pagado: { count: 0, before_itbis_minor: 0 } } } })) } });
        }
        if (path === "open-items") {
          if (state === "inicio-receipts-tasks") return route.fulfill({ json: OPEN_ITEMS_WIRE });
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
      const attention = page.getByTestId("home-attention");
      const attentionError = page.getByTestId("home-attention-error");
      const attentionRetry = attentionError.getByRole("button", { name: "Reintentar", exact: true });
      const attentionClear = page.getByTestId("home-attention-clear");
      const attentionLoading = page.getByTestId("home-attention-loading");
      const monthBody = page.getByTestId("home-month-body");
      const monthRetry = monthBody.getByRole("button", { name: "Reintentar", exact: true });
      const moneyError = page.getByTestId("month-close-money-error");
      const receiptsFail = state === "inicio-receipts-failed" || state === "inicio-receipts-tasks";
      const attentionFails = receiptsFail || state === "inicio-business-refused" || state === "inicio-receipts-refused";
      const monthFails = state === "inicio-month-refused" || state === "inicio-month-500";
      // Inicio never claims a count, "Todo al día" or a first day the server did not send.
      const noAttentionClaim = async () => {
        for (const id of ["home-attention-count", "home-attention-clear", "home-attention-first-day", "home-attention-rows"]) await expect(page.getByTestId(id)).toHaveCount(0);
      };
      if (state.startsWith("bandeja")) {
        await expect(reception).toBeVisible();
        await expect(receptionViews).toBeVisible();
      } else {
        await expect(page.getByTestId("home-overview")).toBeVisible();
        await expect(attention).toBeVisible();
        await expect(page.getByTestId("home-month")).toBeVisible();
      }
      if (state === "bandeja-al-dia") {
        const all = receptionViews.locator(designServerFieldsReception.tabs.all);
        const listos = receptionViews.locator(designServerFieldsReception.tabs.listos);
        const rows = reception.locator(designServerFieldsReception.row);
        const empty = reception.locator(designServerFieldsReception.empty);
        await expect(all).toHaveAttribute("aria-selected", "true");
        await expect(receptionAlert).toHaveCount(0);
        await expect(rows).toHaveCount(1);
        await expect(rows).toContainText("Nube Hosting");
        await expect(rows).toBeVisible();
        await expect(empty).toHaveCount(0);
        for (const [key, label] of [["attention", "Necesitan atención"], ["listos", "Listos"]] as const) {
          await expect(receptionViews.locator(designServerFieldsReception.tabs[key])).toHaveText(new RegExp(`^${label}\\s*0$`));
        }
        await listos.click();
        await expect(listos).toHaveAttribute("aria-selected", "true");
        await expect(empty).toBeVisible();
        await expect(empty).toHaveAttribute("data-empty-kind", "done");
        await expect(empty.getByRole("heading")).toHaveText("No hay recibos listos");
        await expect(empty).toContainText("Cuando un recibo tenga todo confirmado, aparece aquí para aprobarlo.");
        await expect(rows).toHaveCount(0);
        await empty.getByRole("button", { name: "Ver todo", exact: true }).click();
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
      if (state.startsWith("inicio")) {
        if (attentionFails) {
          await expect(attentionError).toBeVisible();
          await expect(attentionError).toHaveAttribute("role", "alert");
          await expect(attentionError).toContainText("No pudimos cargar lo pendiente.");
          await expect(attentionRetry).toHaveCount(receiptsFail ? 1 : 0);
          if (receiptsFail) await expect(attentionError).not.toContainText("hola@cuadrao.ai");
          else {
            await expect(attentionError).toContainText("Si crees que es un error, escríbenos a hola@cuadrao.ai.");
            await expect(attentionError).not.toContainText("conexión");
          }
          await expect(attentionLoading).toHaveCount(0);
          await noAttentionClaim();
          if (width === 390) {
            const box = await attentionError.boundingBox();
            expect(box).not.toBeNull();
            expect(box!.y).toBeGreaterThanOrEqual(0);
            expect(box!.y + box!.height, "the failed read and its way out stay on the first phone screen").toBeLessThanOrEqual(780);
          }
          receiptChecks.push({ state, width, retry: receiptsFail });
        } else await expect(attentionError).toHaveCount(0);
        if (state === "inicio-receipts-loading" || state === "inicio-receipts-unknown") {
          await expect(attentionLoading).toBeVisible();
          await expect(attentionLoading).toHaveAttribute("aria-busy", "true");
          await expect(attentionLoading).toContainText("Cargando la Bandeja");
          await noAttentionClaim();
          receiptChecks.push({ state, width, retry: false });
        }
        if (state === "inicio-known-zero" || monthFails || state === "inicio-open-items-refused") {
          await expect(attentionClear).toBeVisible();
          await expect(attentionClear).toContainText("Todo al día");
          await expect(attentionLoading).toHaveCount(0);
          await expect(page.getByTestId("home-attention-count")).toHaveCount(0);
        }
        if (monthFails) {
          await expect(monthBody).toHaveAttribute("data-state", "error");
          await expect(monthBody.getByRole("alert")).toContainText("No pudimos cargar el mes");
          await expect(page.getByTestId("home-month-net")).toHaveCount(0);
          await expect(monthRetry).toHaveCount(state === "inicio-month-500" ? 1 : 0);
          if (state === "inicio-month-refused") {
            await expect(monthBody).toContainText("Si crees que es un error, escríbenos a hola@cuadrao.ai.");
            await expect(monthBody).not.toContainText("conexión");
          } else await expect(monthBody).toContainText("Tus datos siguen guardados. Revisa tu conexión e inténtalo otra vez.");
        } else {
          await expect(monthBody).toHaveAttribute("data-state", "ready");
          await expect(page.getByTestId("home-month-income")).toHaveAttribute("data-amount", "48500.00");
          await expect(page.getByTestId("home-month-expenses")).toHaveAttribute("data-amount", "12300.00");
          // The server's net: final once nothing is left to mark, unknown (never a guess) while a document waits.
          if (state === "inicio-receipts-tasks") await expect(page.getByTestId("home-month-net")).toHaveAttribute("data-state", "unknown");
          else await expect(page.getByTestId("home-month-net")).toHaveAttribute("data-amount", "36200.00");
        }
        if (state === "inicio-open-items-refused") {
          await expect(moneyError).toBeVisible();
          await expect(moneyError.getByRole("alert")).toContainText("No pudimos cargar lo que falta por cobrar y por pagar");
          await expect(moneyError).toContainText("Si crees que es un error, escríbenos a hola@cuadrao.ai.");
          await expect(moneyError).not.toContainText("conexión");
          await expect(moneyError.getByRole("button", { name: "Reintentar", exact: true })).toHaveCount(0);
          for (const id of ["month-close-receivable", "month-close-payable", "month-close-nothing-open"]) await expect(page.getByTestId(id)).toHaveCount(0);
        } else await expect(page.getByTestId("month-close-money")).toHaveCount(0);
      }
      if (state === "bandeja-refused" || state === "bandeja-mixed") {
        for (const [key, label] of [["attention", "Necesitan atención"], ["listos", "Listos"]] as const) {
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
      evidence.push({ file, sha256: createHash("sha256").update(readFileSync(resolve(output, file))).digest("hex"), state, width });
      if (state === "inicio-receipts-failed") {
        await attentionError.scrollIntoViewIfNeeded();
        const detail = `${state}-${width}-error-detail.png`;
        await page.screenshot({ path: resolve(output, detail), fullPage: true });
        evidence.push({ file: detail, sha256: createHash("sha256").update(readFileSync(resolve(output, detail))).digest("hex"), state, width });
      }
      if (receiptsFail) {
        const before = calls.receipts;
        receiptsDown = false;
        await attentionRetry.click();
        await expect(attentionError).toHaveCount(0);
        await expect(attentionClear).toBeVisible();
        expect(calls.receipts).toBeGreaterThan(before);
        if (state === "inicio-receipts-tasks") {
          // The same read brings the workspace: with settlement on, the document still to mark shows once it lands.
          const receivable = page.getByTestId("month-close-receivable");
          await expect(receivable.getByTestId("month-close-row")).toHaveCount(1);
          await expect(receivable).toContainText("Colmado La Esquina");
          await expect(receivable.getByTestId("month-close-receivable-total")).toHaveAttribute("data-currency", "DOP");
          await expect(moneyError).toHaveCount(0);
          await expect(page.getByTestId("home-month-net")).toHaveAttribute("data-state", "unknown");
        }
        receiptChecks.push({ state, width, retry: true, recovered: true, reads_before: before, reads_after: calls.receipts });
        const recovered = `${state}-${width}-recovered.png`;
        await page.screenshot({ path: resolve(output, recovered), fullPage: true });
        evidence.push({ file: recovered, sha256: createHash("sha256").update(readFileSync(resolve(output, recovered))).digest("hex"), state: `${state}-recovered`, width });
      }
      if (state === "inicio-month-500") {
        const before = calls.month;
        monthDown = false;
        await monthRetry.click();
        await expect(monthBody).toHaveAttribute("data-state", "ready");
        await expect(monthBody.getByRole("alert")).toHaveCount(0);
        await expect(page.getByTestId("home-month-net")).toHaveAttribute("data-amount", "36200.00");
        expect(calls.month).toBeGreaterThan(before);
        monthChecks.push({ width, reads_before: before, reads_after: calls.month });
        const recovered = `${state}-${width}-recovered.png`;
        await page.screenshot({ path: resolve(output, recovered), fullPage: true });
        evidence.push({ file: recovered, sha256: createHash("sha256").update(readFileSync(resolve(output, recovered))).digest("hex"), state: "inicio-month-recovered", width });
      }
      releaseReceipts();
      if (state === "inicio-receipts-loading") {
        await expect(attentionLoading).toHaveCount(0);
        await expect(attentionClear).toBeVisible();
      }
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
  writeFileSync(resolve(output, "manifest.json"), JSON.stringify({ head, stage, proof: "synthetic fixture proof", generated_at: new Date().toISOString(), retryChecks, receiptChecks, monthChecks, evidence }, null, 2));
}
console.log(`Captured ${evidence.length} synthetic screenshots at ${head}`);
