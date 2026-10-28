import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium, expect } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { FREEZE_CSS, fulfillAcceptedBusinessConsent, installBreakpointFixture } from "../e2e/support/breakpoint-fixture";
import { monthCloseWire } from "../e2e/support/month-close-wire";

const baseURL = process.env.EVIDENCE_BASE_URL ?? "http://127.0.0.1:3198";
if (!["127.0.0.1", "localhost"].includes(new URL(baseURL).hostname)) throw new Error("Evidence requires a local server");
const head = execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
const tree = execFileSync("git", ["rev-parse", "HEAD^{tree}"], { encoding: "utf8" }).trim();
if (execFileSync("git", ["status", "--porcelain", "--untracked-files=no"], { encoding: "utf8" }).trim()) throw new Error("Exact-head evidence requires a clean tracked tree");
const output = resolve(process.env.EVIDENCE_OUTPUT ?? "../temp/1222-sofia/lifecycle-evidence");
mkdirSync(output, { recursive: true });
const allCases = ["owner-datos", "close-download", "close-confirm", "close-uncertain", "transfer-picker", "accept-confirm", "accept-uncertain", "owner-closed", "member-closed", "closed-banner", "switcher", "deletion-owned", "deletion-closed"];
const cases = process.env.EVIDENCE_CASE ? allCases.filter(state => state === process.env.EVIDENCE_CASE) : allCases;
if (!cases.length) throw new Error("Unknown evidence case");
const owner = { space_id: "39d12d09-bebe-4992-b6dc-cb1a84d52438", grant_id: "af2d018e-6e6c-4fc7-9602-9b0b31ff9bc0", name: "Colmado Rosa", role: "owner", capabilities: ["read", "prepare", "approve"], access_seen: true };
const client = { ...owner, space_id: "49767c9c-9f8a-4af7-82e3-bcc065e09a19", grant_id: "b3acd38c-2e99-49aa-888f-4ee3a6268066", name: "Taller Sol", role: "accountant", capabilities: ["read", "prepare"] };
const closed = { ...owner, closed_at: "2026-10-21T17:45:00Z", reopen_until: "2026-11-20T17:45:00Z" };
const owned = { ...owner, member_count: 3, reopen_until: closed.reopen_until, export_windows: [{ start: "2025-01-01", end: "2025-12-31" }, { start: "2026-01-01", end: "2026-10-21" }], members: [
  { grant_id: "4100626b-f480-4249-97bd-04bdc03f1a15", name: "Rosa Pérez", eligible: true, reason: null },
  { grant_id: "3200626b-f480-4249-97bd-04bdc03f1a15", name: "Ana López", eligible: false, reason: "email_unconfirmed" },
  { grant_id: "2100626b-f480-4249-97bd-04bdc03f1a15", name: "Luis Díaz", eligible: false, reason: "owns_open_business" },
] };
const transfer = { id: "14ed5edb-9a72-428e-9a4a-52f5ab77c342", space_id: owner.space_id, grant_id: client.grant_id, business_name: owner.name, owner_name: "María Rosa", target_name: "Rosa Pérez", role: "target", status: "pending", expires_at: "2026-10-24T17:45:00Z" };
const evidence: { file: string; sha256: string; state: string; width: number; theme: string; posts: number; retryKeys?: string[] }[] = [];
const browser = await chromium.launch({ headless: true });
try {
  for (const state of cases) for (const width of [1440, 390]) for (const theme of ["light", "dark"] as const) {
    const page = await browser.newPage({ viewport: { width, height: width === 390 ? 844 : 1000 }, reducedMotion: "reduce", colorScheme: theme });
    const unexpected: string[] = [];
    const calls: { path: string; method: string; key: string | null }[] = [];
    await page.route("**/*", route => {
      const url = new URL(route.request().url());
      if (url.origin === new URL(baseURL).origin) return route.continue();
      unexpected.push(url.origin); return route.abort();
    });
    await installBreakpointFixture(page, { language: "es-419", theme, emptyChat: true });
    const source = createFixtureBusinessDataSource({ chatAvailable: false });
    await page.route("**/api/v1/business/**", async route => {
      const url = new URL(route.request().url());
      const path = url.pathname.split("/business/")[1];
      const method = route.request().method();
      calls.push({ path, method, key: route.request().headers()["idempotency-key"] ?? null });
      if (path.includes("/accept") || path.endsWith("/close")) return route.fulfill({ status: 503, json: { code: "internal_error", request_id: "4ea79978-ce17-4853-b232-b2a72f4c9ce7" } });
      if (path === "ownership-transfers") return route.fulfill({ json: { transfers: state.startsWith("accept-") ? [transfer] : [] } });
      if (path === "owned-spaces") return route.fulfill({ json: { spaces: state === "owner-closed" ? [] : [owned] } });
      if (path === "closed-spaces") return route.fulfill({ json: { spaces: state === "owner-closed" ? [closed] : [] } });
      if (path === "spaces") return route.fulfill({ json: { spaces: state === "owner-closed" || state === "member-closed" ? [] : state === "closed-banner" || state === "deletion-closed" ? [client] : [owner, client], closed_spaces: state === "member-closed" ? [{ ...closed, role: "accountant" }] : state === "owner-closed" || state === "closed-banner" || state === "switcher" || state === "deletion-closed" ? [closed] : [] } });
      if (path === "consent") return fulfillAcceptedBusinessConsent(route);
      if (path === "space/name-prompt") return route.fulfill({ json: { id: owner.space_id, name: owner.name, name_required: false, name_prompt_seen: true, show_prompt: false } });
      if (path === "space") return route.fulfill({ json: { id: owner.space_id, name: owner.name } });
      if (path === "workspace") return route.fulfill({ json: await source.workspace() });
      if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
      if (path === "fiscal-profile") return route.fulfill({ json: { ...await source.fiscalProfile(), name: owner.name } });
      if (path === "receipt-reading") return route.fulfill({ json: { enabled: false, available: true, can_change: true } });
      if (path === "email") return route.fulfill({ json: { enabled: true, receiving_address: "recibos@example.invalid" } });
      if (path === "captures" || path === "email/deliveries") return route.fulfill({ json: { items: [] } });
      if (path === "receipts") return route.fulfill({ json: { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 0, ready_to_review_count: 0, needs_attention_count: 0, confirmed_count: 0, dismissed_count: 0 } } });
      if (path === "month-close") return route.fulfill({ json: monthCloseWire("2026-10") });
      if (path === "open-items") { const none = { count: 0, totals: [], overdue: { count: 0, totals: [] }, items: [] }; return route.fulfill({ json: { today: "2026-10-21", cuentas_por_cobrar: none, cuentas_por_pagar: none } }); }
      if (path === "invitations") return route.fulfill({ json: [] });
      const profileSpace = path.match(/^spaces\/([^/]+)\/profile$/)?.[1];
      if (profileSpace) return route.fulfill({ json: { space_id: profileSpace, name: [owner, client, closed].find(space => space.space_id === profileSpace)?.name ?? owner.name, country: "DO", currency: "DOP", revision: 0, details: {}, appearance: { kind: "default" }, image: null } });
      throw new Error(`Unmapped synthetic endpoint ${path}`);
    });
    const query = state.startsWith("close-") ? `?lifecycle=close&business=${owner.space_id}` : state === "transfer-picker" ? `?lifecycle=transfer&business=${owner.space_id}` : state.startsWith("accept-") ? `?transfer=${transfer.id}` : state === "owner-datos" ? "?view=business&tab=datos" : "";
    try {
      await page.goto(`${baseURL}/biz${query}`);
      await page.addStyleTag({ content: FREEZE_CSS });
      if (state === "owner-datos") { await expect(page.getByTestId("business-lifecycle-controls")).toBeVisible(); await expect(page.getByTestId("business-profile-preview").getByRole("heading", { name: owner.name })).toBeVisible(); await page.getByTestId("business-lifecycle-controls").scrollIntoViewIfNeeded(); }
      if (state === "close-download") await expect(page.getByRole("button", { name: "Descargar comprobantes", exact: true })).toBeVisible();
      if (state === "close-confirm" || state === "close-uncertain") {
        await page.getByRole("button", { name: "Cerrar negocio", exact: true }).click();
        const alert = page.getByRole("alertdialog"); await expect(alert).toContainText("3"); await expect(alert).toContainText("hora de RD");
        expect(calls.filter(call => call.method === "POST")).toHaveLength(0);
        if (state === "close-uncertain") { await alert.getByRole("textbox").fill(owner.name); await alert.getByRole("button", { name: "Cerrar negocio", exact: true }).click(); await expect(alert.getByRole("alert")).toBeVisible(); }
      }
      if (state === "transfer-picker") { await expect(page.getByRole("radio", { name: /Rosa Pérez/ })).toBeVisible(); await expect(page.getByRole("radio", { name: /Ana López/ })).toBeDisabled(); }
      if (state.startsWith("accept-")) {
        await page.getByRole("button", { name: "Aceptar transferencia", exact: true }).click();
        await expect(page.getByRole("alertdialog")).toContainText("La lectura automática de recibos se apaga");
        expect(calls.filter(call => call.path.endsWith("/accept"))).toHaveLength(0);
        if (state === "accept-uncertain") { await page.getByRole("alertdialog").getByRole("button", { name: "Aceptar transferencia", exact: true }).click(); await expect(page.getByRole("button", { name: "Actualizar", exact: true })).toBeVisible(); await expect(page.getByRole("button", { name: "Aceptar transferencia", exact: true })).toHaveCount(0); }
      }
      if (state === "owner-closed") { await expect(page.getByRole("button", { name: "Reabrir negocio", exact: true })).toBeVisible(); await expect(page.getByText("Para descargar comprobantes, primero debes reabrir el negocio.")).toBeVisible(); }
      if (state === "member-closed") { await expect(page.getByTestId("business-member-closed")).toBeVisible(); expect(calls.every(call => call.method === "GET")).toBe(true); }
      if (state === "closed-banner") await expect(page.getByTestId("business-closed-owner-banner")).toBeVisible();
      if (state === "switcher") { await page.getByRole("button", { name: "Colmado Rosa", exact: true }).first().click(); await expect((width === 390 ? page.getByRole("dialog", { name: "Colmado Rosa", exact: true }) : page.getByRole("menu", { name: "Colmado Rosa", exact: true })).getByText("Cerrados", { exact: true })).toBeVisible(); }
      if (state.startsWith("deletion-")) {
        await page.getByTestId("header-profile-trigger").click();
        await page.getByRole("button", { name: "Controles de datos", exact: true }).click();
        await page.getByRole("button", { name: /^Eliminar cuenta/ }).click();
        const dialog = page.getByRole("dialog", { name: "¿Eliminar tu cuenta?", exact: true });
        await expect(dialog).toBeVisible();
        const submit = dialog.getByRole("button", { name: "Eliminar cuenta", exact: true });
        if (state === "deletion-owned") { await expect(submit).toBeDisabled(); await expect(dialog).toContainText("Primero transfiere o cierra tus negocios."); }
        else { await expect(submit).toBeEnabled(); await expect(dialog).toContainText("nadie podrá reabrirlo"); await expect(dialog).toContainText("hora de RD"); }
        await submit.scrollIntoViewIfNeeded();
      }
      await page.evaluate(label => { const stamp = document.createElement("div"); stamp.textContent = label; stamp.style.cssText = "position:fixed;bottom:4px;right:4px;background:#fff;color:#111;border:1px solid #999;padding:3px;z-index:99999;font:10px sans-serif"; document.body.append(stamp); }, `Synthetic fixture proof · ${head.slice(0, 7)}`);
      const file = `${state}-${width}-${theme}.png`;
      await page.screenshot({ path: resolve(output, file), fullPage: true });
      if (state === "transfer-picker") {
        await page.getByRole("radio", { name: /Rosa Pérez/ }).check();
        await page.getByRole("textbox").fill(owner.name);
        const submit = page.getByRole("button", { name: "Solicitar transferencia", exact: true });
        await expect(submit).toBeEnabled(); await submit.scrollIntoViewIfNeeded();
        const detail = `${state}-${width}-${theme}-confirmation.png`;
        await page.screenshot({ path: resolve(output, detail), fullPage: true });
        evidence.push({ file: detail, sha256: createHash("sha256").update(readFileSync(resolve(output, detail))).digest("hex"), state: "transfer-confirmation", width, theme, posts: calls.filter(call => call.method === "POST").length });
      }
      if (state === "close-uncertain") { await page.getByRole("alertdialog").getByRole("button", { name: "Cerrar negocio", exact: true }).click(); await expect.poll(() => calls.filter(call => call.path.endsWith("/close")).length).toBe(2); const keys = calls.filter(call => call.path.endsWith("/close")).map(call => call.key); expect(keys[0]).toBeTruthy(); expect(keys[1]).toBe(keys[0]); }
      if (state === "accept-uncertain") { await page.getByRole("button", { name: "Actualizar", exact: true }).click(); await expect(page.getByRole("button", { name: "Aceptar transferencia", exact: true })).toBeVisible(); expect(calls.filter(call => call.path.endsWith("/accept"))).toHaveLength(1); }
      expect(unexpected, "all requests stay local").toEqual([]);
      evidence.push({ file, sha256: createHash("sha256").update(readFileSync(resolve(output, file))).digest("hex"), state, width, theme, posts: calls.filter(call => call.method === "POST").length, retryKeys: state === "close-uncertain" ? calls.filter(call => call.path.endsWith("/close")).map(call => call.key!) : undefined });
      console.log(`Captured ${state} ${width} ${theme}`);
    } catch (error) { console.error(await page.locator("body").innerText()); throw error; }
    finally { await page.close(); }
  }
} finally {
  await browser.close();
  writeFileSync(resolve(output, "manifest.json"), JSON.stringify({ head, tree, proof: "synthetic local mocks only", generated_at: new Date().toISOString(), evidence }, null, 2));
}
console.log(`Captured ${evidence.length} synthetic screenshots at ${head}`);
