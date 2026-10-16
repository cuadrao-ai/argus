import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { installBreakpointFixture } from "./support/breakpoint-fixture";
const baseline = process.env.CUADRAO_PERSONAL_BASELINE === "true";
const evidence = process.env.CUADRAO_PERSONAL_EVIDENCE_DIR;
async function setup(page: Page, options: { editable?: boolean; personal?: boolean; owner?: boolean; needsAttention?: boolean } = {}) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const original = await source.receipt("rcpt-ferreteria");
  const receipt = { ...original, draft_id: "fixture-draft", personal: options.personal ?? false, personal_editable: options.editable ?? true, status: options.needsAttention ? "needs_attention" as const : original.status, preparable: options.needsAttention ?? original.preparable, enterable: options.needsAttention ?? original.enterable, version: 7 };
  const state = { preparations: 0, writes: [] as { version: number; personal: boolean; key: string | null }[], reads: 0, failed: false, release: null as (() => void) | null, hold: false };
  await page.route("**/api/v1/business/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.split("/business/")[1];
    if (path === "workspace") return route.fulfill({ json: await source.workspace() });
    if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de prueba" } });
    if (path === "spaces") return route.fulfill({ json: { spaces: (await source.spaces()).slice(0, 1).map((space) => ({ ...space, role: options.owner === false ? "accountant" : space.role })) } });
    if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
    if (path === "receipts") return route.fulfill({ json: { items: [receipt], activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 1, needs_attention_count: 0 } } });
    if (path === `receipts/${receipt.id}/prepare`) { state.preparations++; return route.fulfill({ status: 503, json: { code: "synthetic_failure" } }); }
    if (path === `receipts/${receipt.id}`) { state.reads++; return route.fulfill({ json: receipt }); }
    if (path === `drafts/${receipt.draft_id}/personal`) {
      const body = request.postDataJSON();
      state.writes.push({ ...body, key: request.headers()["idempotency-key"] ?? null });
      if (state.hold) await new Promise<void>((resolve) => { state.release = resolve; });
      if (state.failed) return route.fulfill({ status: 503, json: { code: "synthetic_failure" } });
      expect(body.version).toBe(receipt.version);
      receipt.personal = body.personal;
      receipt.version++;
      return route.fulfill({ json: { version: receipt.version, personal: receipt.personal } });
    }
    if (path === "receipt-reading") return route.fulfill({ json: { enabled: true, available: true, can_change: false } });
    if (path === "email") return route.fulfill({ json: { enabled: true, receiving_address: "recibos@example.test" } });
    if (["email/deliveries", "captures", "updates"].includes(path)) return route.fulfill({ json: { items: [] } });
    return route.fulfill({ status: 404, json: { code: "fixture_only" } });
  });
  return { state, receipt };
}
const rowFor = (page: Page) => page.getByTestId("business-inbox-receipts").locator("li").first();
async function capture(page: Page, name: string) {
  if (evidence) await page.screenshot({ path: `${evidence}/${baseline ? "before" : "after"}-${name}.png`, fullPage: true });
}
for (const width of [1280, 390]) {
  test(`row action stays separate from status at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const { state } = await setup(page);
    await page.goto("/biz?view=inbox");
    const row = rowFor(page);
    await expect(row).toContainText("Ferretería");
    await capture(page, `inbox-${width}`);
    if (!baseline) {
      const name = row.locator("button > span.min-w-0 > span").first();
      expect(await name.evaluate((element) => element.scrollLeft)).toBe(0);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (baseline) {
      const toggle = row.getByRole("button", { name: "Marcar como personal", exact: true });
      await expect(toggle).toHaveText("Personal");
      if (width === 390) expect((await toggle.boundingBox())!.y).toBeGreaterThanOrEqual((await row.getByRole("button").first().boundingBox())!.y + (await row.getByRole("button").first().boundingBox())!.height);
      return;
    }
    await expect(row.getByRole("button", { name: "Marcar como personal", exact: true })).toHaveCount(0);
    const more = row.getByRole("button", { name: "Más acciones", exact: true });
    const box = (await more.boundingBox())!;
    expect(box.width).toBeGreaterThanOrEqual(44);
    expect(box.height).toBeGreaterThanOrEqual(44);
    const openBox = (await row.getByRole("button").first().boundingBox())!;
    expect(box.y).toBeLessThan(openBox.y + openBox.height);
    await more.focus();
    expect(await more.evaluate((element) => getComputedStyle(element).boxShadow)).not.toBe("none");
    await capture(page, `focus-${width}`);
    await page.keyboard.press("Enter");
    const mark = page.getByRole("menuitem", { name: "Marcar como personal", exact: true });
    await expect(mark).toBeFocused();
    for (const key of ["ArrowDown", "ArrowUp", "Home", "End"]) {
      await page.keyboard.press(key);
      await expect(mark).toBeFocused();
    }
    expect((await mark.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await capture(page, `menu-${width}`);
    await page.keyboard.press("Escape");
    await expect(more).toBeFocused();
    expect(state.writes).toHaveLength(0);
    await more.click();
    await page.getByRole("heading", { name: "Bandeja", exact: true }).click();
    await expect(mark).toHaveCount(0);
    expect(state.writes).toHaveLength(0);
    await row.getByRole("button").first().click();
    await expect(page).toHaveURL(/receipt=rcpt-ferreteria/);
  });
}
for (const owner of [true, false]) {
  test(`${owner ? "owner" : "preparer"} marks, reads saved status, undoes, and unmarks`, async ({ page }) => {
    test.skip(baseline);
    const { state } = await setup(page, { owner });
    await page.goto("/biz?view=inbox");
    const row = rowFor(page);
    const choose = async (label: string) => { await row.getByRole("button", { name: "Más acciones", exact: true }).click(); await page.getByRole("menuitem", { name: label, exact: true }).click(); };
    await choose("Marcar como personal");
    await expect(row.locator('[data-mark="personal"]')).toHaveText("Personal");
    await expect(page.getByTestId("undo-toast")).toContainText("No cuenta en los totales del negocio");
    expect(state.writes[0]).toMatchObject({ version: 7, personal: true });
    expect(state.reads).toBe(1);
    await page.getByRole("button", { name: "Deshacer", exact: true }).click();
    await expect(row.locator('[data-mark="personal"]')).toHaveCount(0);
    expect(state.writes[1]).toMatchObject({ version: 8, personal: false });
    await choose("Marcar como personal");
    await expect(row.locator('[data-mark="personal"]')).toBeVisible();
    await page.reload();
    await expect(row.locator('[data-mark="personal"]')).toBeVisible();
    await choose("Ya no es personal");
    await expect(row.locator('[data-mark="personal"]')).toHaveCount(0);
    await expect(page.getByTestId("undo-toast")).toContainText("Vuelve a contar en los totales");
    expect(state.writes.map((write) => write.version)).toEqual([7, 8, 9, 10]);
    expect(new Set(state.writes.map((write) => write.key)).size).toBe(4);
    for (const write of state.writes) expect(write.key).toMatch(/^[0-9a-f-]{36}$/);
  });
}
test("read-only actor sees the Personal status without the action", async ({ page }) => {
  test.skip(baseline);
  const { state } = await setup(page, { editable: false, personal: true, owner: false });
  await page.goto("/biz?view=inbox");
  const row = rowFor(page);
  await expect(row.locator('[data-mark="personal"]')).toHaveText("Personal");
  await expect(row.getByRole("button", { name: "Más acciones", exact: true })).toHaveCount(0);
  expect(state.writes).toHaveLength(0);
});
test("pending and failed saves do not claim a Personal change", async ({ page }) => {
  test.skip(baseline);
  const { state } = await setup(page);
  state.hold = true;
  state.failed = true;
  await page.goto("/biz?view=inbox");
  const row = rowFor(page);
  await row.getByRole("button", { name: "Más acciones", exact: true }).click();
  await page.getByRole("menuitem", { name: "Marcar como personal", exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  await expect(page.getByRole("menu")).toHaveCount(0);
  await expect(row.locator('[data-mark="personal"]')).toHaveCount(0);
  await expect(page.getByTestId("undo-toast")).toHaveCount(0);
  state.release!();
  await expect(page.getByTestId("undo-toast")).toContainText("No pudimos guardar el cambio");
  await expect(row.locator('[data-mark="personal"]')).toHaveCount(0);
  expect(state.writes).toHaveLength(1);
});

for (const width of [1280, 390]) {
  test(`failed receipt keeps its recovery actions at ${width}px`, async ({ page }) => {
    test.skip(baseline);
    await page.setViewportSize({ width, height: 900 });
    const { state } = await setup(page, { needsAttention: true });
    await page.goto("/biz?view=inbox");
    const row = rowFor(page);
    await expect(row).toContainText("Necesita atención");
    const retry = row.getByRole("button", { name: "Reintentar", exact: true });
    const manual = row.getByRole("button", { name: "Escribir datos", exact: true });
    for (const button of [retry, manual, row.getByRole("button", { name: "Más acciones", exact: true })]) {
      await expect(button).toBeVisible();
      expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
    await retry.click();
    await expect(row.getByRole("alert")).toContainText("Tu recibo está guardado");
    expect(state.preparations).toBe(1);
    expect(state.writes).toHaveLength(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await capture(page, `recovery-${width}`);
    await manual.click();
    await expect(page).toHaveURL(/receipt=rcpt-ferreteria/);
  });
}
