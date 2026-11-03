import { expect, test, type Locator, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "./support/breakpoint-fixture";

test.skip(process.env.NEXT_PUBLIC_BUSINESS_PILOT_ENABLED !== "true", "/biz needs the Business pilot server");

const SPACE = "6038d05e-0000-4000-8000-000000000001";
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjdAAAAEUlEQVR4nGNkYPjPwMDAAAAECAEBT2vd0wAAAABJRU5ErkJggg==", "base64");
const FILLS: [string, string][] = [["Siena", "rgb(5, 31, 32)"], ["Liquen", "rgb(11, 43, 38)"], ["Enebro", "rgb(22, 56, 50)"], ["Laguna", "rgb(35, 83, 71)"], ["Iris", "rgb(142, 182, 155)"], ["Morera", "rgb(218, 241, 222)"]];

async function liveProfile(page: Page, theme: "light" | "dark") {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language: "es-419", theme, emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const state = { appearance: { kind: "default" } as Record<string, unknown>, revision: 1, uploads: 0, patches: [] as unknown[] };
  await page.route("**/fixture-image/**", (route) => route.fulfill({ contentType: "image/png", body: PNG }));
  await page.route("**/api/v1/business/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.split("/business/")[1];
    if (path === "consent") return fulfillAcceptedBusinessConsent(route);
    if (path === "spaces") return route.fulfill({ json: { spaces: [{ space_id: SPACE, name: "La Palma", grant_id: "owner-grant", role: "owner", business_role: "owner", permissions: ["read", "manage"], capabilities: ["read", "prepare", "approve"], access_seen: true }] } });
    if (path === "space") return route.fulfill({ json: { id: SPACE, name: "La Palma" } });
    if (path === "workspace") return route.fulfill({ json: await source.workspace() });
    if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
    if (path === "fiscal-profile") return route.fulfill({ json: { name: "La Palma", tax_id: null, can_edit: true } });
    if (path === "receipts" || path === "captures") return route.fulfill({ json: { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none" } } });
    if (path === "closed-spaces" || path === "owned-spaces") return route.fulfill({ json: { spaces: [] } });
    if (path === `spaces/${SPACE}/appearance/assets`) {
      state.uploads++;
      return route.fulfill({ json: { asset_id: "asset-1" } });
    }
    if (path === `spaces/${SPACE}/profile`) {
      if (request.method() === "PATCH") {
        state.appearance = request.postDataJSON().appearance;
        state.patches.push(state.appearance);
        state.revision++;
      }
      const origin = new URL(request.url()).origin;
      return route.fulfill({ json: { space_id: SPACE, name: "La Palma", country: "DO", currency: "DOP", revision: state.revision, details: {}, appearance: state.appearance, image: state.appearance.kind === "image" ? { asset_id: "asset-1", width: 2, height: 1, source_url: `${origin}/fixture-image/source.png`, rendered_url: `${origin}/fixture-image/rendered.png` } : null } });
    }
    return route.fulfill({ status: 404, json: { code: "fixture_only" } });
  });
  await page.goto("/biz?view=business");
  await expect(page.getByTestId("business-settings")).toBeVisible();
  return state;
}
async function openEditor(page: Page) {
  await page.getByRole("button", { name: "Cambiar imagen", exact: true }).click();
  const editor = page.getByTestId("identity-editor");
  await expect(editor).toBeVisible();
  return editor;
}
const tiles = (editor: Locator) => editor.locator('[data-testid="identity-upload"], [role="radiogroup"] label');
async function rowsOf(editor: Locator) {
  const boxes = await tiles(editor).evaluateAll((items) => items.map((item) => Math.round(item.getBoundingClientRect().top)));
  return [...new Set(boxes)].length;
}
async function capture(page: Page, name: string) {
  if (!process.env.CUADRAO_RECORD_EVIDENCE_DIR) return;
  await page.evaluate(() => Promise.all(document.getAnimations().map((animation) => animation.finished)));
  await page.screenshot({ path: `${process.env.CUADRAO_RECORD_EVIDENCE_DIR}/${name}.png` });
}
async function save(editor: Locator) {
  await editor.getByRole("button", { name: "Guardar imagen", exact: true }).click();
  await expect(editor).toHaveCount(0);
}

for (const theme of ["light", "dark"] as const) {
  for (const width of [1440, 390]) {
    const phone = width < 720;
    test.describe(`Cambiar imagen ${width}px ${theme}`, () => {
      test.use({ viewport: { width, height: 844 }, hasTouch: phone, isMobile: phone });

      test("eight even tiles hold their fills, and a color and a file save through the live profile", async ({ page }) => {
        const state = await liveProfile(page, theme);
        const editor = await openEditor(page);

        await expect(tiles(editor)).toHaveCount(8);
        expect(await rowsOf(editor)).toBe(phone ? 2 : 1);
        await expect(editor).not.toContainText("10 MB");
        await expect(editor.getByRole("button", { name: "Volver", exact: true })).toHaveCount(0);
        const border = await page.evaluate(() => {
          const probe = document.createElement("span");
          probe.style.color = "var(--segment-thumb-border)";
          document.body.append(probe);
          const color = getComputedStyle(probe).color;
          probe.remove();
          return color;
        });
        for (const tile of await tiles(editor).all()) await expect(tile).toHaveCSS("border-top-width", "1px");
        for (const tile of await tiles(editor).all()) await expect(tile).toHaveCSS("border-top-color", border);
        for (const [label, fill] of FILLS) {
          const tile = editor.locator("label", { has: page.getByRole("radio", { name: label, exact: true }) });
          await expect(tile.locator("span").first()).toHaveCSS("background-color", fill);
        }
        await capture(page, `tray-${width}-${theme}`);

        await editor.locator('input[type="file"]').setInputFiles({ name: "unsafe.svg", mimeType: "image/svg+xml", buffer: Buffer.from("<svg/>") });
        await expect(editor.getByRole("alert")).toHaveText("Elige una imagen JPG, PNG o WebP.");
        await capture(page, `wrong-file-${width}-${theme}`);

        await editor.locator("label", { has: page.getByRole("radio", { name: "Morera", exact: true }) }).click();
        await save(editor);
        expect(state.patches).toEqual([{ kind: "avatar", token: "plum", mark: "initials" }]);

        const reopenedColor = await openEditor(page);
        await expect(reopenedColor.getByRole("radio", { name: "Morera", exact: true })).toBeChecked();
        await expect(reopenedColor.getByRole("button", { name: "Guardar imagen", exact: true })).toBeDisabled();

        await reopenedColor.locator('input[type="file"]').setInputFiles({ name: "logo.png", mimeType: "image/png", buffer: PNG });
        const upload = reopenedColor.getByTestId("identity-upload");
        await expect(upload).toHaveAttribute("aria-pressed", "true");
        await expect(upload.locator("img")).toHaveCount(1);
        await expect(tiles(reopenedColor)).toHaveCount(8);
        await expect(upload.locator("span.absolute")).toHaveCSS("opacity", phone ? "1" : "0");
        await capture(page, `filled-${width}-${theme}`);
        if (!phone) {
          await upload.hover();
          await expect(upload.locator("span.absolute")).toHaveCSS("opacity", "1");
        }
        await save(reopenedColor);
        expect(state.uploads).toBe(1);
        expect(state.patches.at(-1)).toEqual({ kind: "image", asset_id: "asset-1", crop: { mode: "fit", zoom: 1, x: 0, y: 0 } });

        const reopenedImage = await openEditor(page);
        await expect(reopenedImage.getByTestId("identity-upload")).toHaveAttribute("aria-pressed", "true");
        await expect(reopenedImage.getByTestId("identity-preview").locator("img")).toHaveCount(1);
        await reopenedImage.getByRole("button", { name: "Quitar imagen", exact: true }).click();
        await save(reopenedImage);
        expect(state.patches.at(-1)).toEqual({ kind: "default" });

        const reopenedDefault = await openEditor(page);
        await expect(reopenedDefault.getByRole("radio", { name: "Ícono predeterminado", exact: true })).toBeChecked();
        await expect(reopenedDefault.getByTestId("identity-upload").locator("img")).toHaveCount(0);
        expect(state.uploads).toBe(1);
      });

      test("Añadir negocio uses the same tray and keeps the choice as a draft until the Business exists", async ({ page }) => {
        const state = await liveProfile(page, theme);
        await page.getByRole("button", { name: "La Palma", exact: true }).first().click();
        await page.getByText("Añadir negocio", { exact: true }).click();
        await page.getByRole("button", { name: "Añadir imagen · Opcional", exact: true }).click();
        const editor = page.getByTestId("identity-editor");
        await expect(tiles(editor)).toHaveCount(8);
        await capture(page, `add-business-${width}-${theme}`);
        await editor.locator("label", { has: page.getByRole("radio", { name: "Laguna", exact: true }) }).click();
        await save(editor);
        expect(state.patches).toEqual([]);
        await expect(page.getByRole("button", { name: "Cambiar imagen", exact: true }).last()).toBeVisible();
      });

      test("a saved image with a stored crop reopens as saved and writes nothing", async ({ page }) => {
        const state = await liveProfile(page, theme);
        const stored = { kind: "image", asset_id: "asset-1", crop: { mode: "fill", zoom: 2, x: 0.25, y: -0.5 } };
        state.appearance = stored;
        await page.reload();
        const editor = await openEditor(page);
        await expect(editor.getByTestId("identity-upload")).toHaveAttribute("aria-pressed", "true");
        await expect(editor.getByRole("button", { name: "Guardar imagen", exact: true })).toBeDisabled();
        await editor.locator("label", { has: page.getByRole("radio", { name: "Laguna", exact: true }) }).click();
        await editor.getByTestId("identity-upload").click();
        await expect(editor.getByRole("button", { name: "Guardar imagen", exact: true })).toBeDisabled();
        expect(state.patches).toEqual([]);
        expect(state.appearance).toEqual(stored);
      });
    });
  }
}
