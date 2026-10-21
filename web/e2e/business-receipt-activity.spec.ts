import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "./support/breakpoint-fixture";
import type { ReceiptSummary } from "../lib/business-api";

const evidence = "../docs/reports/evidence/cuadrao-receipt-activity";

async function mockInbox(page: Page, language: "en" | "es-419", collapsed: boolean) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language, theme: "light", emptyChat: true });
  if (collapsed) await page.addInitScript(() => localStorage.setItem("argus:sidebar_mode", "collapsed"));
  await page.emulateMedia({ reducedMotion: "reduce" });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const seed = (await source.receipts("inbox")).slice(0, 2);
  const state: { phase: "saved" | "reading" | "ready"; enabled: boolean; reads: number } = { phase: "saved", enabled: false, reads: 0 };
  const receipts = (): ReceiptSummary[] => seed.map((receipt, index) => ({ ...receipt,
    status: state.phase === "saved" ? "saved" : state.phase === "reading" && index === 0 ? "queued" : "review_ready",
    read_pending: state.phase === "reading" && index === 0,
    activity: { state: state.phase === "saved" ? "saved_unread" : state.phase === "reading" && index === 0 ? "reading" : "ready", unread: state.phase !== "reading" || index !== 0, completion_cursor: state.phase === "ready" || index === 1 && state.phase === "reading" ? (index ? "b" : "a").repeat(64) : null },
  }));
  const reading = () => ({ scope_version: 1, enabled: state.enabled, available: true, can_change: true,
    disclosure: language === "en" ? "Synthetic disclosure. Email, WhatsApp and uploads are read only after this owner choice." : "Permiso de prueba. Correo, WhatsApp y archivos se leen solo después de esta decisión del dueño.",
    disclosure_token: "a".repeat(64), route: { gateway: "synthetic", interpretation: [{ model: "fixture-reader" }], reply: [] }, consented_at: state.enabled ? "2026-10-14T11:00:00Z" : null, revoked_at: null });
  await page.route("**/api/v1/business/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.split("/business/")[1];
    if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "Synthetic Business" } });
    if (path === "spaces") return route.fulfill({ json: { spaces: await source.spaces() } });
    if (path === "workspace") return route.fulfill({ json: await source.workspace() });
    if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
    if (path === "captures") return route.fulfill({ json: { items: [] } });
    if (path === "receipts") { state.reads++; return route.fulfill({ json: { items: receipts(), activity: { reading_count: state.phase === "reading" ? 1 : 0, unread_count: state.phase === "reading" ? 1 : 2, presentation: state.phase === "reading" ? "working" : "unread" } } }); }
    if (path === "receipt-reading") {
      if (request.method() === "POST") { expect(request.headers()["idempotency-key"]).toBeTruthy(); state.enabled = true; state.phase = "reading"; }
      return route.fulfill({ json: reading() });
    }
    if (path === "email") return route.fulfill({ json: { enabled: false, receiving_address: null } });
    if (path === "email/deliveries") return route.fulfill({ json: { items: [] } });
    if (path === "consent") return fulfillAcceptedBusinessConsent(route);
    return route.fulfill({ status: 404, json: { code: "fixture_only" } });
  });
  await page.goto("/biz?view=inbox");
  return state;
}

for (const options of [{ language: "en" as const, collapsed: false }, { language: "es-419" as const, collapsed: true }]) {
  test(`owner opt-in and automatic receipt attention ${options.language} collapsed=${options.collapsed}`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    const state = await mockInbox(page, options.language, options.collapsed);
    await mkdir(evidence, { recursive: true });
    await expect(page.getByTestId("receipt-reading-control")).toBeVisible();
    await expect(page.getByTestId("receipt-unread-dot")).toHaveCount(2);
    await expect(page.getByText(/Prepare with AI|Preparar con IA/)).toHaveCount(0);
    await page.screenshot({ path: `${evidence}/saved-${options.language}.png`, fullPage: true, animations: "disabled" });
    await page.getByRole("button", { name: options.language === "en" ? "Turn receipt reading on" : "Activar lectura de recibos", exact: true }).click();
    await expect(page.getByTestId("receipt-reading-ring")).toHaveCount(1);
    await expect(page.getByTestId("receipt-unread-dot")).toHaveCount(1);
    const nav = page.getByTestId("business-sidebar-nav");
    await expect(nav.locator('[data-sidebar-activity-overlay="true"]')).toHaveCount(1);
    await page.screenshot({ path: `${evidence}/reading-${options.language}.png`, fullPage: true, animations: "disabled" });
    const before = state.reads;
    state.phase = "ready";
    await expect(page.getByTestId("receipt-reading-ring")).toHaveCount(0, { timeout: 12000 });
    await expect(page.getByTestId("receipt-unread-dot")).toHaveCount(2);
    expect(state.reads).toBeGreaterThan(before);
    await expect(nav.locator('[data-sidebar-activity-overlay="true"]')).toHaveCount(1);
    await page.screenshot({ path: `${evidence}/ready-${options.language}.png`, fullPage: true, animations: "disabled" });
  });
}
