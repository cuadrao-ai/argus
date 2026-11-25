import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium, expect } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { FREEZE_CSS, fulfillAcceptedBusinessConsent, installBreakpointFixture } from "../e2e/support/breakpoint-fixture";
import { fulfillSyntheticBusinessFallback } from "../e2e/support/synthetic-business-fallback";
import type { BusinessDossier, BusinessDuplicateCandidate } from "../lib/business-dossier";

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

/** A plain synthetic receipt drawing, so both previews open in the image viewer with its controls. */
const receiptImage = (ncf: string) => `<svg xmlns="http://www.w3.org/2000/svg" width="360" height="520"><rect width="360" height="520" fill="#fff"/><rect x="20" y="20" width="320" height="480" fill="none" stroke="#999"/><text x="40" y="70" font-family="sans-serif" font-size="20">Ferreteria de prueba</text><text x="40" y="110" font-family="sans-serif" font-size="16">03/11/2026</text><text x="40" y="150" font-family="sans-serif" font-size="16">NCF ${ncf}</text><text x="40" y="440" font-family="sans-serif" font-size="22">Total 1,180.00</text></svg>`;
const FILES: Record<string, string> = { "synthetic-file-new": receiptImage("B0100000456"), "synthetic-file-original": receiptImage("B0100000123") };

type State = "problems" | "compare" | "origin" | "same" | "readonly" | "pending" | "failure" | "success" | "deleted";
const STATES: State[] = ["problems", "compare", "origin", "same", "readonly", "pending", "failure", "success", "deleted"];

/** The server's candidate for each state: `same` is an RNC and NCF pair, which lists only same_purchase. */
function candidate(state: State): BusinessDuplicateCandidate {
  const same = state === "same";
  const document = { draft_id: "synthetic-new", counterparty: "Ferretería de prueba", occurred_on: "2026-11-03", amount: "1180.00", currency: "DOP", fiscal_number: same ? "B0100000123" : "B0100000456", file: { connection_id: "synthetic-file-new", filename: "factura-nueva.svg", media_type: "image/svg+xml", channel: "web" as const, received_at: "2026-11-04T12:00:00Z" }, received_at: "2026-11-04T12:00:00Z", approved_at: null, state: "open" as const };
  const other = { ...document, draft_id: "synthetic-original", fiscal_number: "B0100000123", file: { connection_id: "synthetic-file-original", filename: "factura.svg", media_type: "image/svg+xml", channel: "whatsapp" as const, received_at: "2026-11-03T12:00:00Z" }, received_at: "2026-11-03T12:00:00Z" };
  return {
    draft_id: "synthetic-original",
    version: 3,
    basis: same ? "fiscal_number" : "read_facts",
    decisions: state === "readonly" ? [] : same ? ["same_purchase"] : ["different_purchase", "same_purchase"],
    comparison: { document, other, differences: same ? ["file"] : ["fiscal_number", "file"], recommendation: same ? "same_purchase" : "different_purchase" },
  };
}

const browser = await chromium.launch({ headless: true });
try {
  for (const state of STATES) for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: width === 390 ? 844 : 1100 }, reducedMotion: "reduce" });
    const unexpected: string[] = [];
    page.on("pageerror", (error) => unexpected.push(error.message));
    await page.route("**/*", route => {
      if (new URL(route.request().url()).origin === new URL(baseURL).origin) return route.continue();
      unexpected.push(route.request().url());
      return route.abort();
    });
    await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
    let dossier: BusinessDossier = { ...base, draft_id: "synthetic-new", version: 7, sources: [], capabilities: state === "readonly" ? ["read"] : ["read", "prepare", "approve"], document_type_editable: state !== "readonly", approval_available: false, approval_action: null, blockers: [{ code: "possible_duplicate", field: null }, { code: "fact_required", field: "funding" }], bandeja_group: { group: "attention", reason: "duplicate", label: "needs_attention" }, listo_gaps: ["duplicate", "blocked"], duplicate_candidates: [candidate(state)], facts: { ...base.facts, funding: { state: "unknown", value: null, origin: null, verified: false, source_ids: [] } } };
    const decision = state === "deleted" ? "same_purchase" : "different_purchase";
    const writes: { body: unknown; key: string | undefined }[] = [];
    let release = () => {};
    const held = new Promise<void>((resolve) => { release = resolve; });
    await page.route("**/api/v1/business/**", async route => {
      const path = new URL(route.request().url()).pathname.split("/business/")[1];
      const file = /^receipts\/([^/]+)\/source$/.exec(path)?.[1];
      if (file && FILES[file]) return route.fulfill({ body: FILES[file], contentType: "image/svg+xml" });
      const id = /^receipts\/(synthetic-file-(?:new|original))$/.exec(path)?.[1];
      if (id && route.request().method() === "GET") {
        return route.fulfill({ json: { id, sent_by: { id, kind: "email", address: id === "synthetic-file-new" ? "nueva@example.test" : "anterior@example.test" } } });
      }
      if (path === "drafts/synthetic-new/duplicate-resolution") {
        if (route.request().method() !== "POST") {
          unexpected.push(`Unexpected synthetic method ${route.request().method()} for ${path}`);
          return route.fulfill({ status: 503, json: { code: "unexpected_synthetic_write" } });
        }
        writes.push({ body: route.request().postDataJSON(), key: route.request().headers()["idempotency-key"] });
        expect(writes[0].body).toEqual({ version: 7, other_draft_id: "synthetic-original", other_version: 3, decision });
        expect(writes[0].key).toBeTruthy();
        if (state === "pending") await held;
        if (state === "failure") return route.fulfill({ status: 409, json: { code: "stale_version" } });
        dossier = state === "deleted"
          ? { ...dossier, version: 8, duplicate_candidates: [], restore_available: true, deleted: { actor: { actor_id: "synthetic-owner", display_name: "Dueña de prueba", shown_as: "name" }, at: "2026-11-16T12:00:00Z", purge_at: "2026-11-23T12:00:00Z", key: "synthetic-key", previous_state: { state: "open", group: "attention" } } }
          : { ...dossier, version: 8, duplicate_candidates: [], blockers: [{ code: "fact_required", field: "funding" }], bandeja_group: { group: "attention", reason: "blocked", label: "needs_attention" }, listo_gaps: ["blocked"] };
        return route.fulfill({ json: dossier });
      }
      if (path === "drafts/synthetic-new/dossier" && route.request().method() === "GET") return route.fulfill({ json: dossier });
      try {
        return await fulfillSyntheticBusinessFallback(route, {
          source,
          owner,
          fulfillConsent: () => fulfillAcceptedBusinessConsent(route),
        });
      } catch (error) {
        unexpected.push(error instanceof Error ? error.message : String(error));
        return route.fulfill({ status: 503, json: { code: "unmapped_synthetic_endpoint" } });
      }
    });
    try {
      await page.goto(`${baseURL}/biz?draft=synthetic-new`);
      // The duplicate is one problem of the header's list, beside the other reasons; nothing else on the panel says it.
      const status = page.getByTestId("dossier-status");
      const problems = status.getByTestId("dossier-problems");
      const list = status.getByTestId("dossier-problem-list");
      const accept = page.getByTestId("receipt-review-footer").locator("[data-review-primary]");
      const entry = list.locator('[data-reason="duplicate"]');
      await expect(problems).toHaveText("2 por resolver");
      await page.addStyleTag({ content: FREEZE_CSS });
      await problems.click();
      await expect(list.getByRole("option")).toHaveCount(2);
      await expect(entry).toContainText("Parece repetido");
      await expect(entry).toContainText("Comparar");
      await expect(list.locator("[data-compare]")).toHaveCount(1);
      await expect(page.getByText(/Parece repetido/)).toHaveCount(1);
      await expect(page.getByText(/Parece un recibo/)).toHaveCount(0);
      await expect(list.locator('[data-reason="blocked"]')).toContainText("Cómo se pagó");
      const view = page.getByTestId("duplicate-compare");
      const footer = page.getByTestId("receipt-review-footer");
      const distinct = footer.getByRole("button", { name: "Son compras distintas", exact: true });
      const remove = footer.getByRole("button", { name: "Eliminar este duplicado", exact: true });
      if (state !== "problems") {
        await entry.click();
        await expect(view).toBeVisible();
        await expect(list).toHaveCount(0);
        await expect(view.getByTestId("duplicate-compare-row")).toHaveCount(5);
        await expect(view.locator('[data-testid="duplicate-compare-row"][data-state="different"]')).toHaveCount(state === "same" ? 0 : 1);
        await expect(view.locator('[data-testid="duplicate-compare-row"] td [data-compare-marker="different"]')).toHaveCount(state === "same" ? 0 : 1);
        await expect(view.locator('[data-testid="duplicate-compare-row"] td [data-compare-marker="same"][aria-label="Igual"]')).toHaveCount(state === "same" ? 5 : 4);
        const ncf = view.locator('[data-field="fiscal_number"] td[title]');
        expect(await ncf.evaluateAll(cells => cells.every(cell => cell.scrollWidth <= cell.clientWidth))).toBe(true);
        const frame = page.getByTestId("business-record-review");
        await expect(frame.getByRole("tab")).toHaveText(["General", "Detalles"]);
        await expect(view.getByRole("columnheader")).toContainText(["Dato", "Este", "Guardado antes"]);
        await expect(frame.getByTestId("receipt-original-source")).toHaveCount(1);
        await expect(frame.getByTestId("receipt-viewer")).toHaveCount(1);
        const original = frame.getByRole("radio", { name: "Guardado antes" });
        await original.check();
        await expect(frame.getByTestId("dossier-document-foot")).toContainText("factura.svg");
        if (state === "origin") {
          await frame.getByRole("tab", { name: "Detalles" }).click();
          const table = frame.getByTestId("duplicate-origin");
          await expect(table.getByRole("rowheader")).toHaveText(["Canal", "Enviado por", "Llegada", "Archivo"]);
          await expect(table.getByTitle("anterior@example.test")).toBeVisible();
        } else if (state === "compare") {
          await frame.getByRole("tab", { name: "General" }).scrollIntoViewIfNeeded();
        }
        await expect(footer.getByRole("button", { name: "Volver", exact: true })).toBeVisible();
        if (state === "same") {
          await expect(view.getByTestId("duplicate-recommendation")).toHaveText("Es el mismo documento.");
          await expect(remove).toBeVisible();
          await expect(distinct).toHaveCount(0);
        } else if (state === "readonly") {
          await expect(footer.getByRole("button")).toHaveCount(1);
        } else {
          await expect(view.getByTestId("duplicate-recommendation")).toHaveText("Mismo comercio, fecha, total y moneda. El NCF es distinto: probablemente son dos compras distintas.");
          await expect(distinct).toBeVisible();
          await expect(remove).toBeVisible();
        }
        if (["pending", "failure", "success"].includes(state)) {
          await distinct.click();
          if (state === "pending") { await expect(view).toHaveAttribute("aria-busy", "true"); await expect(distinct).toBeDisabled(); await expect(remove).toBeDisabled(); }
          if (state === "failure") await expect(footer.getByRole("alert")).toBeVisible();
          if (state === "success") {
            await expect(view).toHaveCount(0);
            await expect(problems).toHaveCount(0);
            await expect(page.getByText(/Parece repetido/)).toHaveCount(0);
            await expect(page.getByText("Marcado como compras distintas.", { exact: true })).toBeVisible();
            // Funding still blocks recording. The main action can explain it and receives focus again.
            await expect(status.getByTestId("dossier-reason")).toBeVisible();
            await expect(accept).toBeEnabled();
            await expect(accept).toBeFocused();
            await expect(page.getByText("Cómo se pagó", { exact: true }).first()).toBeVisible();
          }
        }
        if (state === "deleted") {
          await remove.click();
          await expect(view).toHaveCount(0);
          await expect(page.getByTestId("business-record-review")).toHaveCount(0);
          await expect(page.getByRole("button", { name: "Deshacer", exact: true })).toBeVisible();
        }
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      const file = `${state}-${width}.png`;
      await page.screenshot({ path: resolve(output, file), fullPage: true });
      if (state === "success") {
        // Moving off the success toast lets it dismiss before clicking the footer on a phone.
        await page.mouse.move(0, 0);
        await expect(page.getByTestId("toast")).toBeHidden({ timeout: 10_000 });
        await accept.click();
        await expect(list.getByRole("heading")).toHaveText("Corrige 1 dato antes de aceptar");
        const funding = list.getByRole("option");
        await expect(funding).toHaveCount(1);
        await expect(funding).toHaveAttribute("data-reason", "blocked");
        await expect(funding).toContainText("Cómo se pagó");
        await expect(funding).toBeFocused();
        await expect(list.getByRole("button", { name: "Aceptar de todos modos", exact: true })).toHaveCount(0);
        await page.keyboard.press("Escape");
        await expect(list).toHaveCount(0);
        await expect(accept).toBeFocused();
      }
      expect(writes.length).toBe(["problems", "compare", "origin", "same", "readonly"].includes(state) ? 0 : 1);
      expect(unexpected).toEqual([]);
      screenshots.push({ state, width, file, writes: writes.length, sha256: createHash("sha256").update(readFileSync(resolve(output, file))).digest("hex") });
    } finally { release(); await page.close(); }
  }
} finally { await browser.close(); }
if (git("rev-parse", "HEAD") !== head || git("status", "--porcelain", "--untracked-files=no")) throw new Error("Evidence head changed");
writeFileSync(resolve(output, "manifest.json"), JSON.stringify({ head, tree: git("rev-parse", "HEAD^{tree}"), source: "local synthetic browser routes", screenshots }, null, 2));
console.log(`Verified ${screenshots.length} screenshots at ${head}`);
