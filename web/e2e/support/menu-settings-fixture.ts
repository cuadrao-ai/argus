import { expect, type Page } from "@playwright/test";
import { FREEZE_CSS, installBreakpointFixture, type Account, type Language } from "./breakpoint-fixture";

export type Cell = { width: number; account: Account; language: Language; theme?: "dark" | "light"; motion?: "on" };
export const AUDIT_CELLS: Cell[] = (["guest", "registered"] as Account[]).flatMap((account) => [
  ...[390, 720, 900, 1024, 1280].map((width): Cell => ({ width, account, language: "en", theme: "dark" })),
  { width: 390, account, language: "es-419", theme: "light" },
]);
export function auditTag(cell: Cell) { return `${cell.account}-${cell.language}-${cell.theme ?? "dark"}-${cell.width}`; }

export async function openFixture(page: Page, cell: Cell, url = "/chat?conversation=conversation-alpha") {
  await page.setViewportSize({ width: cell.width, height: 900 });
  await page.emulateMedia({ colorScheme: cell.theme ?? "dark", reducedMotion: cell.motion === "on" ? "no-preference" : "reduce" });
  // Deny all external requests; the fixture installed afterwards owns API reads.
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    return ["127.0.0.1", "localhost"].includes(url.hostname)
      ? route.continue()
      : route.abort("blockedbyclient");
  });
  await installBreakpointFixture(page, { ...cell, emptyChat: true });
  // Keep an existing conversation reachable without coupling menu captures to
  // historical result-card fixtures. This lane is strategy-agnostic.
  await page.route("**/api/v1/conversations/*/messages*", (route) => route.request().method() === "GET" ? route.fulfill({
    json: { items: [{
      id: "menu-audit-message", role: "user", created_at: "2026-09-14T12:00:00Z",
      content: cell.language === "en" ? "My saved conversation." : "Mi conversación guardada.",
      metadata: {},
    }], next_cursor: null },
  }) : route.fallback());
  // A menu walk must never submit a turn, a simulation, or a mutation.
  await page.route("**/api/v1/**", (route) => {
    const method = route.request().method();
    if (method !== "GET" && !route.request().url().endsWith("/read")) {
      throw new Error(`Unexpected API write in menu audit: ${method} ${route.request().url()}`);
    }
    return route.fallback();
  });
  await page.goto(url, { waitUntil: "networkidle" });
  if (cell.motion !== "on") await page.addStyleTag({ content: FREEZE_CSS });
  if (url.startsWith("/chat")) await expect(page.getByTestId("chat-input")).toBeVisible();
}

export async function openSettings(page: Page, cell: Cell) {
  if (cell.width < 720) await page.getByTestId("chat-shell-menu-trigger").click();
  await page.getByRole("button", {
    name: cell.account === "guest"
      ? /^(guest settings|ajustes de invitado|configuración de invitado)$/i
      : /^(settings|ajustes|configuración)$/i,
  }).first().click();
}
