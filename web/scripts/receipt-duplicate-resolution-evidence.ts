import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium, expect } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { FREEZE_CSS, fulfillAcceptedBusinessConsent, installBreakpointFixture } from "../e2e/support/breakpoint-fixture";
import { monthCloseWire } from "../e2e/support/month-close-wire";
import type { BusinessDossier } from "../lib/business-dossier";

const baseURL = process.env.EVIDENCE_BASE_URL ?? "http://127.0.0.1:3198";
if (!["127.0.0.1", "localhost"].includes(new URL(baseURL).hostname)) throw new Error("Evidence requires localhost");
const git = (...args: string[]) => execFileSync("git", args, { encoding: "utf8" }).trim();
const head = git("rev-parse", "HEAD");
if (git("status", "--porcelain", "--untracked-files=no")) throw new Error("Evidence requires a clean tracked tree");
const output = resolve(process.env.EVIDENCE_OUTPUT ?? "../temp/duplicate-resolution-evidence");
mkdirSync(output, { recursive: true });
const screenshots: { state: string; width: number; file: string; sha256: string; writes: number }[] = [];
const source = createFixtureBusinessDataSource({ chatAvailable: false });
const owner = (await source.spaces())[0];
const base = await source.dossier(dossierFixtureIds.ready);
const browser = await chromium.launch({ headless: true });
try {
  for (const state of ["warning", "pending", "failure", "readonly", "success"]) for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: width === 390 ? 844 : 1100 }, reducedMotion: "reduce" });
    const unexpected: string[] = [];
    page.on("pageerror", (error) => unexpected.push(error.message));
    await page.route("**/*", route => {
      if (new URL(route.request().url()).origin === new URL(baseURL).origin) return route.continue();
      unexpected.push(route.request().url());
      return route.abort();
    });
    await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
    let dossier: BusinessDossier = { ...base, draft_id: "synthetic-new", version: 7, sources: [], capabilities: state === "readonly" ? ["read"] : ["read", "prepare", "approve"], document_type_editable: state !== "readonly", approval_available: false, approval_action: null, blockers: [{ code: "possible_duplicate", field: null }, { code: "fact_required", field: "funding" }], duplicate_candidates: [{ draft_id: "synthetic-original", version: 3 }], facts: { ...base.facts, funding: { state: "unknown", value: null, origin: null, verified: false, source_ids: [] } } };
    const writes: { body: unknown; key: string | undefined }[] = [];
    let release = () => {};
    const held = new Promise<void>((resolve) => { release = resolve; });
    await page.route("**/api/v1/business/**", async route => {
      const path = new URL(route.request().url()).pathname.split("/business/")[1];
      if (path === "drafts/synthetic-new/duplicate-resolution") {
        writes.push({ body: route.request().postDataJSON(), key: route.request().headers()["idempotency-key"] });
        expect(writes[0].body).toEqual({ version: 7, other_draft_id: "synthetic-original", other_version: 3, decision: "different_purchase" });
        expect(writes[0].key).toBeTruthy();
        if (state === "pending") await held;
        if (state === "failure") return route.fulfill({ status: 409, json: { code: "stale_version" } });
        dossier = { ...dossier, version: 8, duplicate_candidates: [], blockers: [{ code: "fact_required", field: "funding" }] };
        return route.fulfill({ json: dossier });
      }
      if (path === "space/name-prompt") return route.fulfill({ json: { id: owner.space_id, name: owner.name, name_required: false, name_prompt_seen: true, show_prompt: false } });
      if (route.request().method() !== "GET") {
        unexpected.push(`Unexpected synthetic write ${path}`);
        return route.fulfill({ status: 503, json: { code: "unexpected_synthetic_write" } });
      }
      if (path === "drafts/synthetic-new/dossier") return route.fulfill({ json: dossier });
      if (path === "spaces") return route.fulfill({ json: { spaces: [owner], closed_spaces: [] } });
      if (path === `spaces/${owner.space_id}/profile`) return route.fulfill({ json: { space_id: owner.space_id, name: owner.name, country: "DO", currency: "DOP", revision: 0, details: {}, appearance: { kind: "default" }, image: null } });
      if (path === "space") return route.fulfill({ json: { id: owner.space_id, name: owner.name } });
      if (path === "workspace") return route.fulfill({ json: await source.workspace() });
      if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
      if (path === "fiscal-profile/fields") return route.fulfill({ json: { "606": [], "607": [] } });
      if (path === "fiscal-profile") return route.fulfill({ json: await source.fiscalProfile() });
      if (path === "consent") return fulfillAcceptedBusinessConsent(route);
      if (path === "receipt-reading") return route.fulfill({ json: { enabled: false, available: true, can_change: false } });
      if (path === "email") return route.fulfill({ json: { enabled: true, receiving_address: "receipts@example.test" } });
      if (["captures", "email/deliveries", "ownership-transfers", "closed-spaces", "owned-spaces"].includes(path)) return route.fulfill({ json: { items: [], spaces: [], transfers: [] } });
      if (path === "receipts") return route.fulfill({ json: { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 0, ready_to_review_count: 0, needs_attention_count: 0, confirmed_count: 0, dismissed_count: 0 } } });
      if (path === "month-close") return route.fulfill({ json: monthCloseWire("2026-10") });
      if (path === "open-items") { const none = { count: 0, totals: [], overdue: { count: 0, totals: [] }, items: [] }; return route.fulfill({ json: { today: "2026-10-22", cuentas_por_cobrar: none, cuentas_por_pagar: none } }); }
      if (path === "invitations") return route.fulfill({ json: [] });
      unexpected.push(`Unmapped synthetic endpoint ${path}`);
      return route.fulfill({ status: 503, json: { code: "unmapped_synthetic_endpoint" } });
    });
    try {
      await page.goto(`${baseURL}/biz?draft=synthetic-new`);
      const card = page.getByTestId("receipt-duplicate-resolution");
      await expect(card).toBeVisible();
      await page.addStyleTag({ content: FREEZE_CSS });
      const button = card.getByRole("button", { name: "Es otra compra", exact: true });
      if (["pending", "failure", "success"].includes(state)) {
        await button.click();
        if (state === "pending") { await expect(card).toHaveAttribute("aria-busy", "true"); await expect(button).toBeDisabled(); }
        if (state === "failure") await expect(card.getByRole("alert")).toBeVisible();
        if (state === "success") await expect(card).toHaveCount(0);
      }
      if (state === "readonly") await expect(button).toHaveCount(0);
      if (state !== "success") {
        await expect(page.getByText("Parece un recibo que ya guardaste: mismo comercio, fecha y total. No se guardará como un segundo gasto.", { exact: true })).toBeVisible();
        await expect(card.getByRole("button", { name: "Ver el recibo ya guardado", exact: true })).toBeVisible();
        await card.scrollIntoViewIfNeeded();
      } else {
        await expect(page.getByRole("button", { name: "Aprobar", exact: true })).toBeDisabled();
        await expect(page.getByText("Cómo se pagó", { exact: true }).first()).toBeVisible();
      }
      expect(writes.length).toBe(["warning", "readonly"].includes(state) ? 0 : 1);
      expect(unexpected).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      const file = `${state}-${width}.png`;
      await page.screenshot({ path: resolve(output, file), fullPage: true });
      screenshots.push({ state, width, file, writes: writes.length, sha256: createHash("sha256").update(readFileSync(resolve(output, file))).digest("hex") });
    } finally { release(); await page.close(); }
  }
} finally { await browser.close(); }
if (git("rev-parse", "HEAD") !== head || git("status", "--porcelain", "--untracked-files=no")) throw new Error("Evidence head changed");
writeFileSync(resolve(output, "manifest.json"), JSON.stringify({ head, tree: git("rev-parse", "HEAD^{tree}"), source: "local synthetic browser routes", screenshots }, null, 2));
console.log(`Verified ${screenshots.length} screenshots at ${head}`);
