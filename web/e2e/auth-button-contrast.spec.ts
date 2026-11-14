import { expect, test, type Locator, type Page } from "@playwright/test";
import { installBreakpointFixture } from "./support/breakpoint-fixture";
import { labelContrast, type PointerState } from "./support/label-contrast";

const pointerStates: PointerState[] = ["rest", "hover", "focus-visible", "active"];
const minimum = 4.5;

async function measure(page: Page, rows: string[], control: string, target: Locator, states: PointerState[] = pointerStates) {
  await expect(target).toBeVisible();
  await page.mouse.move(0, 0);
  for (const state of states) {
    const result = await labelContrast(page, target, state);
    rows.push(`${result.ratio >= minimum ? "ok  " : "FAIL"} ${result.ratio.toFixed(2)} ${control} ${state} label ${result.label} on ${result.background}`);
  }
}

for (const theme of ["light", "dark"] as const) {
  test(`every auth button state keeps a readable label in ${theme}`, async ({ page }) => {
    const rows: string[] = [];
    await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
    await page.setViewportSize({ width: 390, height: 844 });
    await installBreakpointFixture(page, { language: "es-419", theme });
    await page.clock.install();
    let release = () => {};
    await page.route("**/api/auth/recovery", async (route) => {
      await new Promise<void>((resolve) => { release = resolve; });
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });

    await page.goto("/auth/forgot-password?email=synthetic@example.test");
    const send = page.locator("form button[type=\"submit\"]");
    await measure(page, rows, "submit primary", send);
    await measure(page, rows, "back link", page.getByRole("link", { name: "Volver a iniciar sesión" }));
    await measure(page, rows, "language", page.getByRole("button", { name: "English" }));
    await send.click();
    await expect(send).toHaveAttribute("aria-busy", "true");
    await measure(page, rows, "submit primary busy", send, ["rest", "hover"]);
    release();

    await expect(page.getByRole("heading", { name: "Revisa tu correo" })).toBeVisible();
    const resend = page.locator("button.auth-primary");
    await expect(resend).toBeDisabled();
    await measure(page, rows, "resend primary waiting", resend, ["rest", "hover"]);
    await page.clock.fastForward(61_000);
    await expect(page.getByRole("button", { name: "Enviar otro enlace" })).toBeEnabled();
    await measure(page, rows, "resend primary", resend);
    await resend.click();
    await expect(resend).toHaveAttribute("aria-busy", "true");
    await measure(page, rows, "resend primary busy", resend, ["rest", "hover"]);
    release();
    await expect(resend).toHaveAttribute("aria-busy", "false");
    await page.clock.fastForward(61_000);
    await measure(page, rows, "change email", page.getByRole("button", { name: "Corregir correo" }));

    await page.unroute("**/api/auth/recovery");
    await page.route("**/api/auth/recovery", (route) => route.fulfill({ status: 429, headers: { "Retry-After": "60" }, body: "{}" }));
    await page.getByRole("button", { name: "Corregir correo" }).click();
    await send.click();
    await expect(send).toHaveAttribute("aria-busy", "false");
    await expect(send).toBeDisabled();
    await measure(page, rows, "submit primary waiting", send, ["rest", "hover"]);

    await page.goto("/auth/recovery");
    await measure(page, rows, "new link primary", page.locator("a.auth-primary"));

    await page.route("**/api/v1/me", (route) => route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "unauthorized" }) }));
    for (const [mode, other] of [["login", "Registrarse"], ["signup", "Iniciar sesión"]] as const) {
      await page.goto(`/?auth=${mode}`);
      await measure(page, rows, `${mode} submit primary`, page.locator('[data-auth-brand="cuadrao"] form button[type="submit"]'));
      await measure(page, rows, `${mode} switch`, page.getByRole("button", { name: other, exact: true }));
      await measure(page, rows, `${mode} language`, page.locator('[data-auth-brand="cuadrao"]').getByRole("button", { name: "English" }));
    }

    console.log(`${theme}\n${rows.join("\n")}`);
    expect(rows.filter((row) => row.startsWith("FAIL")), rows.join("\n")).toEqual([]);
  });
}
