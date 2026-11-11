import { expect, test } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { receiptCopy } from "../lib/receipt-copy";
import { installMobileShellFixture } from "./support/mobile-shell-fixture";

// Run the isolated scripts/qa/sharing_604_fixture.py first. These requests use
// production owner/public receipt routes; only unrelated chat shell data is stubbed.
const api = process.env.ARGUS_SHARING_FIXTURE_API;
test.skip(!api, "Requires the isolated provider-free receipt API.");
const cells = [
  { width: 390, height: 844, language: "en", theme: "dark" },
  { width: 720, height: 1024, language: "en", theme: "dark" },
  { width: 1024, height: 800, language: "en", theme: "dark" },
  { width: 1280, height: 844, language: "en", theme: "dark" },
  { width: 390, height: 844, language: "es-419", theme: "light" },
] as const;

test.describe.configure({ mode: "serial" });
for (const cell of cells) {
  test(`real receipt lifecycle ${cell.language} ${cell.theme} ${cell.width}`, async ({ page, request, browser }, testInfo) => {
    const { width, height, language, theme } = cell;
    const copy = receiptCopy(language);
    expect((await request.post(`${api}/__fixture/reset`)).ok()).toBe(true);
    const response = await request.get(`${api}/__fixture/${language}`);
    expect(response.ok()).toBe(true);
    const bundle = await response.json();
    const conversationId = bundle.conversation.id;
    await page.setViewportSize({ width, height });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: "no-preference" });
    await installMobileShellFixture(page, { account: "registered", language, theme });
    await page.route(/\/api\/v1\/conversations\/[^/]+\/messages(?:\?|$)/, route => route.fulfill({ json: { items: bundle.messages, next_cursor: null } }));
    await page.route(/\/api\/v1\/conversations(?:\?|$)/, route => route.fulfill({ json: { items: [bundle.conversation], next_cursor: null } }));
    // Registered user shell is seeded; privacy, snapshot and lifecycle are real.
    await page.route(/\/api\/v1\/(?:conversations\/[^/]+\/public-excerpt[^?]*|public-excerpts(?:\/[^?]+)?|public\/receipts\/[^?]+|public\/receipt-funnel)(?:\?|$)/, route => route.continue());
    await page.goto(`/chat?conversation=${conversationId}`);
    await page.getByRole("button", { name: copy.selection.title, exact: true }).click();
    const transcript = page.getByTestId("conversation-transcript-region");
    await expect(transcript.getByRole("checkbox")).toHaveCount(6);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: copy.selection.all, exact: true }).click();
    const checks = transcript.getByRole("checkbox");
    for (let index = 0; index < await checks.count(); index++) await expect(checks.nth(index)).toBeChecked();
    const prefix = `${language}-${theme}-${width}`;
    const directory = process.env.ARGUS_SHARING_EVIDENCE_DIR ? resolve(process.env.ARGUS_SHARING_EVIDENCE_DIR) : testInfo.outputDir;
    mkdirSync(directory, { recursive: true });
    await checks.first().scrollIntoViewIfNeeded();
    await page.screenshot({ animations: "allow", style: "nextjs-portal { display: none; }", path: resolve(directory, `${prefix}-selection.png`) });
    await page.getByRole("button", { name: copy.selection.continue, exact: true }).click();
    const dialog = page.getByRole("dialog", { name: copy.selection.title, exact: true });
    await expect(dialog).toBeVisible();
    const note = language === "en" ? "My monthly experiment." : "Mi experimento mensual.";
    await dialog.getByLabel(copy.owner.note_label).fill(note);
    await expect(dialog.getByRole("button", { name: copy.selection.preview, exact: true })).toBeInViewport();
    await page.screenshot({ animations: "allow", style: "nextjs-portal { display: none; }", path: resolve(directory, `${prefix}-note.png`) });
    const previewResponse = page.waitForResponse(r => r.url().endsWith("/public-excerpt-preview") && r.request().method() === "POST");
    await dialog.getByRole("button", { name: copy.selection.preview, exact: true }).click();
    const preview = await (await previewResponse).json();
    expect(preview.payload.turns).toHaveLength(6);
    expect(preview.payload.turns.some((turn: { answer?: string }) => (turn.answer?.length ?? 0) > 4000)).toBe(true);
    expect(new Set(preview.payload.turns.map((turn: { kind: string }) => turn.kind))).toEqual(new Set(["backtest", "calculation", "research_answer", "answer"]));
    await expect(dialog.getByTestId("receipt-chart-attribution").getByRole("link")).toHaveAttribute("href", "https://www.tradingview.com/");
    await expect(dialog.getByTestId("receipt-chart-attribution")).toBeVisible();
    await expect(dialog.getByRole("textbox", { name: copy.followup.label })).toBeDisabled();
    await expect(dialog.getByRole("button", { name: copy.owner.create, exact: true })).toBeEnabled();
    await page.screenshot({ animations: "allow", style: "nextjs-portal { display: none; }", path: resolve(directory, `${prefix}-preview.png`) });
    await dialog.getByTestId("receipt-chart-attribution").scrollIntoViewIfNeeded();
    await page.screenshot({ animations: "allow", style: "nextjs-portal { display: none; }", path: resolve(directory, `${prefix}-preview-chart.png`) });
    await dialog.getByRole("textbox", { name: copy.followup.label }).scrollIntoViewIfNeeded();
    await page.screenshot({ animations: "allow", style: "nextjs-portal { display: none; }", path: resolve(directory, `${prefix}-preview-bottom.png`) });
    const createdResponse = page.waitForResponse(r => r.url().endsWith("/public-excerpt") && r.request().method() === "POST");
    await dialog.getByRole("button", { name: copy.owner.create, exact: true }).click();
    const creation = await createdResponse;
    expect(creation.ok()).toBe(true);
    const { receipt } = await creation.json();
    await expect(dialog.getByRole("textbox", { name: copy.owner.copy, exact: true })).toHaveValue(new RegExp(`/r/${receipt.public_id}$`));
    await page.screenshot({ animations: "allow", style: "nextjs-portal { display: none; }", path: resolve(directory, `${prefix}-link.png`) });
    await dialog.getByRole("button", { name: copy.selection.close, exact: true }).click();
    if (width < 720) await page.getByTestId("chat-shell-menu-trigger").click();
    await page.getByRole("button", { name: /^(Settings|Ajustes)$/i }).click();
    await page.getByRole("button", { name: language === "en" ? "Data Controls" : "Controles de datos", exact: true }).click();
    await page.getByRole("button", { name: copy.list.menu, exact: true }).click();
    const sharedLinks = page.getByRole("dialog", { name: copy.list.title, exact: true });
    for (const control of [sharedLinks.getByRole("button", { name: copy.list.copy, exact: true }), sharedLinks.getByRole("link", { name: copy.list.open, exact: true }), sharedLinks.getByRole("button", { name: copy.list.revoke, exact: true })]) {
      await expect(control).toBeVisible();
      // Measure CSS layout pixels; sheet translation can round a 44px DOMRect to 43.99994.
      expect(await control.evaluate((node) => (node as HTMLElement).offsetHeight)).toBeGreaterThanOrEqual(44);
    }
    await page.screenshot({ animations: "allow", style: "nextjs-portal { display: none; }", path: resolve(directory, `${prefix}-shared-links.png`) });
    const publicResponse = await request.get(`${api}/api/v1/public/receipts/${receipt.public_id}`);
    const publicView = await publicResponse.json();
    expect(publicView.payload).toEqual(preview.payload);
    const publicBytes = JSON.stringify(publicView.payload);
    for (const id of [conversationId, bundle.user_id, ...bundle.messages.map((m: { id: string }) => m.id)]) expect(publicBytes).not.toContain(id);
    const visitor = await browser.newContext({ locale: language === "en" ? "en-US" : "es-419", colorScheme: theme, reducedMotion: "no-preference" });
    const publicPage = await visitor.newPage();
    const viewWrites: string[] = [];
    publicPage.on("request", (req) => { if (req.method() !== "GET") viewWrites.push(req.url()); });
    for (const publicWidth of [width]) {
      await publicPage.setViewportSize({ width: publicWidth, height: publicWidth === 390 ? 844 : 800 });
      await publicPage.goto(new URL(receipt.path, page.url()).toString());
      await expect(publicPage.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
      await expect(publicPage.getByText(note).first()).toBeVisible();
      await expect(publicPage.locator('a[href*="coca-cola-reports-second-quarter"]').first()).toBeVisible();
      expect(await publicPage.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await expect(publicPage.getByRole("textbox", { name: copy.followup.label })).toBeEnabled();
      await expect(publicPage.locator("[data-receipt-question]")).toHaveCount(6);
      await expect(publicPage.getByTestId("receipt-chart-attribution").getByRole("link")).toHaveAttribute("href", "https://www.tradingview.com/");
      await expect(publicPage.getByTestId("receipt-chart-attribution")).toBeVisible();
      expect(viewWrites).toEqual([]);
      await publicPage.screenshot({ animations: "allow", style: "nextjs-portal { display: none; }", path: resolve(directory, `${prefix}-public-${publicWidth}.png`), fullPage: true });
      await publicPage.screenshot({ animations: "allow", style: "nextjs-portal { display: none; }", path: resolve(directory, `${prefix}-public-top.png`) });
      await publicPage.getByTestId("receipt-chart-attribution").scrollIntoViewIfNeeded();
      await publicPage.screenshot({ animations: "allow", style: "nextjs-portal { display: none; }", path: resolve(directory, `${prefix}-public-chart.png`) });
      await publicPage.getByRole("textbox", { name: copy.followup.label }).scrollIntoViewIfNeeded();
      await publicPage.screenshot({ animations: "allow", style: "nextjs-portal { display: none; }", path: resolve(directory, `${prefix}-public-bottom.png`) });
    }
    if (width === 390 && language === "en") {
      const followup = "Why use monthly contributions?";
      const submitted: string[] = [];
      await publicPage.route("**/api/v1/chat/stream", async route => {
        const body = route.request().postDataJSON();
        submitted.push(body.message);
        await route.fulfill({ status: 200, contentType: "text/event-stream", body: `data: ${JSON.stringify({ type: "final", payload: { conversation_id: body.conversation_id, assistant_response: "Fixture follow-up accepted.", message_id: "fixture-followup" } })}\n\ndata: [DONE]\n\n` });
      });
      const forkResponse = publicPage.waitForResponse(r => r.url().endsWith("/fork") && r.request().method() === "POST");
      await publicPage.getByRole("textbox", { name: copy.followup.label }).fill(followup);
      await publicPage.getByRole("button", { name: copy.followup.send, exact: true }).click();
      const fork = await (await forkResponse).json();
      expect(fork.created).toBe(true);
      expect(fork.conversation.id).not.toBe(conversationId);
      await expect(publicPage.getByText("Fixture follow-up accepted.", { exact: true })).toBeVisible();
      expect(submitted).toEqual([followup]);
      const copied = await (await request.get(`${api}/api/v1/conversations/${fork.conversation.id}/messages`)).json();
      expect(copied.items).toHaveLength(preview.payload.turns.length * 2);
      expect(JSON.stringify(copied)).not.toContain(note);
      await publicPage.goto(new URL(receipt.path, page.url()).toString());
    }
    await sharedLinks.getByRole("button", { name: copy.list.revoke, exact: true }).click();
    const revokedResponse = page.waitForResponse(r => r.url().endsWith(`/public-excerpts/${receipt.id}`) && r.request().method() === "DELETE");
    await sharedLinks.getByRole("button", { name: copy.list.confirm_revoke, exact: true }).click();
    expect((await revokedResponse).ok()).toBe(true);
    await publicPage.reload();
    await expect(publicPage.getByText(copy.tombstone.title, { exact: true })).toBeVisible();
    await publicPage.screenshot({ animations: "allow", style: "nextjs-portal { display: none; }", path: resolve(directory, `${prefix}-revoked.png`) });
    await visitor.close();
    writeFileSync(resolve(directory, `${prefix}-proof.json`), JSON.stringify({
      fixture: "production receipt API, synthetic memory store; unrelated shell endpoints stubbed",
      language, theme, width, turns: preview.payload.turns.length,
      exact_preview_matches_public_payload: true, private_ids_absent: true,
      noindex: true, public_widths: [width], motion: "no-preference", revoked: true, provider_calls: 0,
    }, null, 2) + "\n");
  });
}
