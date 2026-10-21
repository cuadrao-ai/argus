import { expect, test, type Locator, type Page } from "@playwright/test";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

const PREVIEW = "/dev/business-preview";
/** The Business build: the local recipe exports NEXT_PUBLIC_BUSINESS_PILOT_ENABLED=true for the dev server and for this runner alike. */
const BUSINESS_BUILD = process.env.NEXT_PUBLIC_BUSINESS_PILOT_ENABLED === "true";

async function openPreview(
  page: Page,
  url = PREVIEW,
  options: { sidebarMode?: "expanded" | "collapsed"; emptyChat?: boolean } = {},
) {
  await page.route("**/*", (route) => {
    const { hostname } = new URL(route.request().url());
    return ["127.0.0.1", "localhost"].includes(hostname)
      ? route.continue()
      : route.abort("blockedbyclient");
  });
  await installBreakpointFixture(page, {
    language: "es-419",
    theme: "light",
    emptyChat: options.emptyChat ?? true,
  });
  if (options.sidebarMode) {
    await page.addInitScript((mode) => {
      window.localStorage.setItem("cuadrao:business_sidebar_mode", mode);
    }, options.sidebarMode);
  }
  await page.goto(url);
}

/** The amount field's message region, the last id it is described by. */
async function amountMessage(page: Page, input: Locator) {
  const ids = ((await input.getAttribute("aria-describedby")) ?? "").split(" ");
  return page.locator(`[id="${ids[ids.length - 1]}"]`);
}

async function openRecordExpense(page: Page) {
  await page.getByTestId("business-create").click();
  await page.getByRole("menuitem", { name: "Record expense" }).click();
  return page.getByTestId("record-expense-amount");
}

const nav = (page: Page) => page.getByTestId("business-sidebar-nav");
const panelHeading = (page: Page, name: string) =>
  page.getByTestId("workspace-panel-region").getByRole("heading", { name, exact: true });
const tray = (page: Page) => page.getByTestId("side-drawer");
const trayHeading = (page: Page, name: string) => tray(page).getByRole("heading", { name, level: 2 });
const reviewField = (page: Page, label: string) => page.getByTestId("receipt-review-fields").getByLabel(label);

test.describe("Business preview", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("switching Business twelve times with a receipt open and a draft typed never shows the account-changed screen; the record and its address close on each switch", async ({ page }) => {
    test.setTimeout(180_000);
    const switchTo = async (name: string) => {
      await page.getByTestId("business-switcher").getByRole("button").click();
      await page.getByRole("menuitem", { name: "Cambiar de negocio" }).click();
      await page.getByRole("option", { name: new RegExp(name) }).click();
      await expect(page.getByTestId("business-current-name")).toHaveText(name);
      await expect(page.getByText("Tu cuenta cambió", { exact: false })).toHaveCount(0);
    };
    await openPreview(page, `${PREVIEW}?chat=on&receipt=rcpt-ferreteria`);
    for (let round = 0; round < 6; round += 1) {
      if (round > 0) await page.goto(`${PREVIEW}?chat=on&receipt=rcpt-ferreteria`);
      await expect(trayHeading(page, "Ferretería La Esquina")).toBeVisible();
      await switchTo("Colmado Peña");
      await expect(page).not.toHaveURL(/receipt=|expense=|draft=/);
      await expect(tray(page)).toHaveCount(0);
      await expect(page.getByTestId("business-client-cue")).toHaveText("Cliente: Colmado Peña");
      await page.getByTestId("chat-input").fill(`Pagué 850 en pintura ${round}`);
      await switchTo("Mi negocio");
      await expect(page.getByTestId("business-client-cue")).toHaveCount(0);
      await expect(page.getByTestId("chat-input")).toHaveText(`Pagué 850 en pintura ${round}`);
    }
  });

  test("an Overview draft survives a visit to the Inbox", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?chat=on`);
    await expect(panelHeading(page, "Hola")).toBeVisible();

    const composer = page.getByTestId("chat-input");
    await composer.click();
    await page.keyboard.type("¿Cuánto gasté en pintura?");

    await nav(page).getByRole("button", { name: /^Bandeja/ }).click();
    await expect(panelHeading(page, "Bandeja")).toBeVisible();
    await expect(page.getByTestId("chat-input")).toHaveCount(0);

    await nav(page).getByRole("button", { name: /^Inicio/ }).click();
    await expect(panelHeading(page, "Hola")).toBeVisible();
    await expect(page.getByTestId("chat-input")).toHaveText("¿Cuánto gasté en pintura?");
  });

  test("the Agregar menu opens from the collapsed rail inside the viewport", async ({ page }) => {
    await openPreview(page, PREVIEW, { sidebarMode: "collapsed" });
    await expect(panelHeading(page, "Hola")).toBeVisible();

    const trigger = page.getByTestId("add-menu-more");
    await expect(trigger).toHaveAccessibleName("Más acciones");
    const menu = page.getByRole("menu", { name: "Más acciones" });
    await trigger.click();
    await expect(menu.getByRole("menuitem")).toHaveCount(3);
    await trigger.click();
    await expect(menu).toHaveCount(0);

    await trigger.focus();
    await page.keyboard.press("Enter");
    await expect(menu).toBeVisible();
    const box = await menu.boundingBox();
    const viewport = page.viewportSize();
    expect(box && viewport).toBeTruthy();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(viewport!.width);
    expect(box!.y + box!.height).toBeLessThanOrEqual(viewport!.height);

    const items = menu.getByRole("menuitem");
    await expect(items).toHaveText(["Exportar registros", "Copiar dirección de reenvío", "Ver correos"]);
    await expect(items.nth(0)).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(items.nth(1)).toBeFocused();

    await page.keyboard.press("Escape");
    await expect(menu).toHaveCount(0);
    await expect(trigger).toBeFocused();

    await page.keyboard.press("Enter");
    await expect(items.nth(0)).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(menu).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });

  test("New chat has one entry point and Create sits on the nav row grid", async ({ page }) => {
    await openPreview(page, PREVIEW);
    await expect(page.getByRole("button", { name: /^New chat/ })).toHaveCount(1);

    const create = page.getByTestId("business-create");
    const overview = page.getByRole("button", { name: /^Overview/ }).first();
    const [createBox, overviewBox] = await Promise.all([create.boundingBox(), overview.boundingBox()]);
    expect(createBox!.height).toBe(overviewBox!.height);
    const [createIcon, overviewIcon] = await Promise.all([
      create.locator("svg").boundingBox(),
      overview.locator("svg").first().boundingBox(),
    ]);
    expect(createIcon!.width).toBe(overviewIcon!.width);
  });

  test("New chat from the Inbox shows the chat surface", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?view=inbox`);
    await expect(panelHeading(page, "Inbox")).toBeVisible();

    await page.getByRole("button", { name: /^New chat/ }).first().click();

    await expect(page.locator('[data-business-home="new_chat"]')).toBeVisible();
    await expect(page.getByTestId("workspace-panel-region")).toHaveCount(0);
    await expect(page).toHaveURL(/view=chat/);
  });

  test("leaving a conversation for a panel keeps the panel in the address bar", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?chat=on&conversation=conversation-alpha`, { emptyChat: false });
    await expect(page.getByTestId("workspace-panel-region")).toHaveCount(0);
    await expect(page.getByTestId("chat-input")).toBeVisible();

    await nav(page).getByRole("button", { name: /^Bandeja/ }).click();
    await expect(panelHeading(page, "Bandeja")).toBeVisible();
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveURL(/\/dev\/business-preview\?(chat=on&)?view=inbox$/);

    await page.reload();
    await expect(panelHeading(page, "Bandeja")).toBeVisible();
  });

  test("receipt entry marks missing fields and requires separate canonical approval", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?receipt=rcpt-ferreteria`);
    await expect(trayHeading(page, "Ferretería La Esquina")).toBeVisible();

    const needed = tray(page).getByText("Falta", { exact: true });
    await expect(needed).toHaveCount(1);
    const paidFrom = page.locator("label", { hasText: "Pagado desde" });
    await expect(paidFrom.getByText("Falta", { exact: true })).toBeVisible();
    const save = page.getByRole("button", { name: "Guardar detalles de revisión" });
    await expect(save).toBeDisabled();

    await paidFrom.locator("select").selectOption("acct-ops");
    await expect(needed).toHaveCount(0);
    await save.click();

    await expect(trayHeading(page, "Ferretería La Esquina")).toBeVisible();
    await expect(page.getByText("Se registró un gasto", { exact: false })).toHaveCount(0);
    await tray(page).getByRole("button", { name: "Aprobar", exact: true }).click();
    await expect(tray(page).getByRole("status").filter({ hasText: "Se registró un gasto" })).toBeVisible();
    await expect(panelHeading(page, "Gastos")).toBeVisible();
    await expect(page.getByTestId("workspace-panel-region")).toContainText("Ferretería La Esquina");
  });

  test("an unknown AI outcome offers a consented retry beside entry by hand", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?receipt=rcpt-unknown`);
    const attention = page.getByTestId("receipt-attention");
    await expect(attention).toContainText("No pudimos recuperar el resultado de la lectura con IA");
    await expect(attention).toContainText("Si reintentas, el recibo se envía a nuestro proveedor de IA.");
    await expect(page.getByRole("button", { name: "Preparar con IA" })).toHaveCount(0);
    await expect(reviewField(page, "Comercio o persona")).toBeEnabled();

    await attention.getByRole("button", { name: "Reintentar con IA" }).click();
    await expect(tray(page)).toContainText("Leyendo tu recibo");
    await expect(page.getByRole("button", { name: "Reintentar con IA" })).toHaveCount(0);
    await expect(reviewField(page, "Comercio o persona")).toHaveCount(0);
  });

  test("a read with no single purchase is entered by hand and keeps what was read", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?receipt=rcpt-ambiguous`);
    const attention = page.getByTestId("receipt-attention");
    await expect(attention).toContainText("Cuadrao no pudo asociar este recibo a una sola compra. Escribe los detalles tú mismo");
    await expect(page.getByRole("button", { name: /con IA/ })).toHaveCount(0);
    await expect(page.getByText("Lo que dice el recibo")).toBeVisible();

    await reviewField(page, "Comercio o persona").fill("Colmado Don Pedro");
    await reviewField(page, "Fecha de actividad").fill("05/10/2026");
    await page.locator("label", { hasText: "Moneda" }).locator("select").selectOption("DOP");
    await page.getByTestId("receipt-review-amount").fill("706.10");
    await page.locator("label", { hasText: "Pagado desde" }).locator("select").selectOption("acct-ops");
    await page.getByRole("button", { name: "Guardar detalles de revisión" }).click();

    await expect(trayHeading(page, "Colmado Don Pedro")).toBeVisible();
    await expect(page.getByTestId("receipt-attention")).toHaveCount(0);
    await expect(page.getByTestId("receipt-original-source")).toBeVisible();
    await tray(page).getByRole("button", { name: "Aprobar", exact: true }).click();
    await expect(tray(page).getByRole("status").filter({ hasText: "Se registró un gasto" })).toBeVisible();
  });

  test("an unreadable receipt offers entry by hand and no AI retry", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?receipt=rcpt-blurry`);
    await expect(page.getByTestId("receipt-attention")).toContainText("No pudimos leer este archivo");
    await expect(page.getByRole("button", { name: "Subir otro archivo" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Escribir datos" })).toBeVisible();
    await expect(page.getByRole("button", { name: /con IA/ })).toHaveCount(0);
    await expect(reviewField(page, "Comercio o persona")).toBeEnabled();
  });

  test("the review Total refuses letters, pads on blur and refuses a decimal comma paste", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await openPreview(page, `${PREVIEW}?receipt=rcpt-ferreteria`);
    await expect(trayHeading(page, "Ferretería La Esquina")).toBeVisible();

    const total = page.getByTestId("receipt-review-amount");
    await expect(total).toHaveValue("3,450.00");
    await expect(total).toHaveAccessibleName("Monto en DOP (RD$)");
    const message = await amountMessage(page, total);

    await total.click();
    await page.keyboard.press("End");
    await page.keyboard.type("wfr");
    await expect(total).toHaveValue("3,450.00");
    await expect(message).toHaveText("Usa solo números y un punto decimal.");

    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.type("1250.5");
    await expect(message).toHaveText("");
    await expect(total).toHaveValue("1,250.5");
    await page.keyboard.press("Tab");
    await expect(total).toHaveValue("1,250.50");

    await page.evaluate(() => navigator.clipboard.writeText("1.250,50"));
    await total.click();
    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.press("ControlOrMeta+v");
    await expect(total).toHaveValue("1,250.50");
    await expect(message).toContainText("Usa un punto para los decimales");
  });

  test("a bare $ pasted into a DOP field is refused as ambiguous", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await openPreview(page, `${PREVIEW}?receipt=rcpt-ferreteria`);
    const total = page.getByTestId("receipt-review-amount");
    await expect(total).toHaveValue("3,450.00");
    const message = await amountMessage(page, total);

    await page.evaluate(() => navigator.clipboard.writeText("$1,250.00"));
    await total.click();
    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.press("ControlOrMeta+v");
    await expect(total).toHaveValue("3,450.00");
    await expect(message).toHaveText("$ puede ser RD$ o US$. Escribe el monto sin símbolo o con RD$ o US$.");
  });

  test("a currency change keeps the digits and says there is no conversion", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?receipt=rcpt-ferreteria`);
    const total = page.getByTestId("receipt-review-amount");
    await expect(total).toHaveValue("3,450.00");
    const message = await amountMessage(page, total);

    await page.locator("label", { hasText: "Moneda" }).locator("select").selectOption("USD");
    await expect(total).toHaveAccessibleName("Monto en USD (US$)");
    await expect(total).toHaveValue("3,450.00");
    await expect(message).toHaveText("Mismo monto, sin conversión.");

    await total.click();
    await page.keyboard.press("End");
    await page.keyboard.press("Backspace");
    await expect(message).toHaveText("");
  });

  test("Total announces Needed when the backend lists the amount as missing", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?receipt=rcpt-saved`);
    const total = page.getByTestId("receipt-review-amount");
    await expect(total).toHaveAccessibleDescription(/Falta/);
    await total.click();
    await page.keyboard.type("80");
    await expect(total).not.toHaveAccessibleDescription(/Falta/);
  });

  test("an edit the browser does not let us cancel is read past the field's grouping", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?receipt=rcpt-ferreteria`);
    const total = page.getByTestId("receipt-review-amount");
    await expect(total).toHaveValue("3,450.00");
    const message = await amountMessage(page, total);

    const replaceWithoutBeforeInput = (next: string) =>
      total.evaluate((input: HTMLInputElement, value) => {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
        setter.call(input, value);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }, next);

    await replaceWithoutBeforeInput("1,500,000");
    await expect(total).toHaveValue("1,500,000");
    await expect(message).toHaveText("");

    await replaceWithoutBeforeInput("1,5,00,000");
    await expect(total).toHaveValue("1,500,000");
    await expect(message).toHaveText("Revisa las comas de miles, como en 1,250.50.");
  });

  test("the review maps the backend's amount_out_of_range onto its Total", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?receipt=rcpt-ferreteria`);
    const total = page.getByTestId("receipt-review-amount");
    await expect(total).toHaveValue("3,450.00");
    await page.locator("label", { hasText: "Pagado desde" }).locator("select").selectOption("acct-ops");

    await page.evaluate(() => {
      (globalThis as { __businessFixtureFailNextWrite?: string }).__businessFixtureFailNextWrite = "amount_out_of_range";
    });
    await page.getByRole("button", { name: "Guardar detalles de revisión" }).click();

    await expect(await amountMessage(page, total)).toHaveText("Este monto es demasiado grande para registrarlo.");
    await expect(total).toHaveAttribute("aria-invalid", "true");
    await expect(trayHeading(page, "Ferretería La Esquina")).toBeVisible();
  });

  test("Record expense guards the length and maps the backend's amount codes onto its Total", async ({ page }) => {
    await openPreview(page);
    const total = await openRecordExpense(page);
    const message = await amountMessage(page, total);
    await total.click();
    await page.keyboard.type("9999999999999999");
    await expect(total).toHaveValue("999,999,999,999,999");
    await expect(message).toHaveText("Use at most 15 digits before the decimal point.");

    for (const [code, text] of [
      ["amount_out_of_range", "This amount is too large to record."],
      ["amount_precision", "DOP allows up to 2 decimals."],
    ]) {
      await page.evaluate((next) => {
        (globalThis as { __businessFixtureFailNextWrite?: string }).__businessFixtureFailNextWrite = next;
      }, code);
      await page.getByRole("button", { name: "Save expense" }).click();
      await expect(message).toHaveText(text);
      await expect(page.getByRole("dialog", { name: "Record expense" })).toBeVisible();
    }
  });

  test("Record expense ignores a typed comma on a dot-decimal device", async ({ page }) => {
    await openPreview(page);
    await page.getByTestId("business-create").click();
    await page.getByRole("menuitem", { name: "Record expense" }).click();

    const total = page.getByTestId("record-expense-amount");
    await total.click();
    await page.keyboard.type("12,50");
    await expect(total).toHaveValue("1,250");
  });

  test("a reload of view=chat stays on the chat surface", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?chat=on&view=chat`);
    const home = page.locator('[data-business-home="new_chat"]');
    await expect(home).toBeVisible();

    await page.reload();
    await expect(home).toBeVisible();
    await expect(page.getByTestId("workspace-panel-region")).toHaveCount(0);
    await expect(page).toHaveURL(/view=chat/);
  });
});

test.describe("Business preview on a comma-decimal device", () => {
  test.use({ viewport: { width: 1280, height: 800 }, locale: "de-DE" });

  test("Record expense reads a typed comma as the decimal point", async ({ page }) => {
    await openPreview(page);
    await page.getByTestId("business-create").click();
    await page.getByRole("menuitem", { name: "Record expense" }).click();

    const total = page.getByTestId("record-expense-amount");
    await total.click();
    await page.keyboard.type("12,50");
    await expect(total).toHaveValue("12.50");
    await expect(page.getByRole("button", { name: "Save expense" })).toBeEnabled();
  });

  test("a pasted 1,250 is refused rather than read two ways", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await openPreview(page);
    const total = await openRecordExpense(page);

    await page.evaluate(() => navigator.clipboard.writeText("1,250"));
    await total.click();
    await page.keyboard.press("ControlOrMeta+v");
    await expect(total).toHaveValue("");
    await expect(await amountMessage(page, total)).toHaveText("Use a point for decimals, as in 1,250.50.");
  });
});

test.describe("Business preview on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the bottom tabs show the Business destinations with labels, and Agregar sits at the top of the screen", async ({ page }) => {
    await openPreview(page);
    await expect(panelHeading(page, "Hola")).toBeVisible();

    await expect(nav(page)).toHaveCount(0);
    const tabs = page.getByTestId("business-bottom-tabs");
    for (const label of ["Inicio", "Bandeja", "Gastos"]) {
      await expect(tabs.getByText(label, { exact: true })).toBeVisible();
    }
    await expect(tabs.getByRole("button", { name: /Bandeja$/ })).toContainText("4");
    await expect(page.getByTestId("add-menu-page").getByRole("button", { name: "Agregar" })).toBeVisible();
  });
});

test.describe("Argus chat without a workspace", () => {
  test.use({ viewport: { width: 1280, height: 800 } });
  // On a Business build /chat sends everyone to the Business shell by design; this is the consumer build's page.
  test.skip(BUSINESS_BUILD, "consumer build only: /chat is not a surface on a Business build");

  test("keeps the mention button and the legacy starter pills", async ({ page }) => {
    await page.route("**/*", (route) => {
      const { hostname } = new URL(route.request().url());
      return ["127.0.0.1", "localhost"].includes(hostname)
        ? route.continue()
        : route.abort("blockedbyclient");
    });
    await installBreakpointFixture(page, { language: "en", theme: "light", emptyChat: true });
    await page.goto("/chat");

    await expect(page.getByTestId("chat-input")).toBeVisible();
    await expect(page.getByRole("button", { name: "Mention an asset or indicator" })).toBeVisible();
    for (const pill of ["Test Apple vs SPY", "Test Bitcoin (BTC) hold", "Test weekly Nvidia buys"]) {
      await expect(page.getByRole("button", { name: pill })).toBeVisible();
    }
    await expect(page.getByTestId("business-sidebar-nav")).toHaveCount(0);
  });
});

test.describe("A conversation opens in the shell of its own surface", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  /** Full page loads after the first: a reload loop shows up here as a count that keeps growing. */
  function countDocumentLoads(page: Page) {
    const loads: string[] = [];
    page.on("request", (request) => { if (request.resourceType() === "document" && request.isNavigationRequest()) loads.push(request.url()); });
    return loads;
  }

  async function serveSurface(page: Page, surface: "personal" | "business", seen: string[]) {
    await page.route("**/api/v1/conversations/*/messages?**", (route) => {
      seen.push(new URL(route.request().url()).pathname);
      return route.fulfill({
        json: {
          items: [
            {
              id: "message-1",
              conversation_id: "conversation-alpha",
              role: "user",
              content: "Lunch with the supplier",
              created_at: "2026-10-08T12:00:00Z",
              metadata: {},
            },
          ],
          next_cursor: null,
          surface,
        },
      });
    });
  }


  test("a guest session on the Business shell makes at most two page loads and never loops", async ({ page }) => {
    test.skip(!BUSINESS_BUILD, "Business build only");
    // The evaluator's case: a guest whose latest Personal conversation used to be picked on every load.
    const seen: string[] = [];
    await page.route("**/*", (route) => ["127.0.0.1", "localhost"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
    await installBreakpointFixture(page, { language: "en", theme: "light", emptyChat: false, account: "guest" });
    await serveSurface(page, "personal", seen);
    const loads = countDocumentLoads(page);
    await page.goto(PREVIEW);
    await page.waitForTimeout(10000);
    expect(loads.length).toBeLessThanOrEqual(2);
    expect(seen.length).toBeLessThanOrEqual(1);
    await expect(page).not.toHaveURL(/notice=conversation_unavailable/);
  });

  test("a Personal chat opened on /biz on a Business build goes nowhere but the notice: one hop, no loop, one link", async ({ page }) => {
    test.skip(!BUSINESS_BUILD, "Business build only");
    const seen: string[] = [];
    await openPreview(page, PREVIEW, { emptyChat: false });
    await serveSurface(page, "personal", seen);
    const loads = countDocumentLoads(page);
    await page.goto(`${PREVIEW}?conversation=conversation-alpha&message=message-1`);

    const notice = page.getByTestId("conversation-unavailable");
    await expect(notice).toBeVisible();
    await expect(page).toHaveURL(/\/dev\/business-preview\?notice=conversation_unavailable$/);
    await expect(notice).toContainText("Esta conversación no está disponible en Cuadrao Business.");
    await expect(notice.getByRole("link", { name: "Ir a Cuadrao Business" })).toHaveAttribute("href", "/biz");
    // Give a loop time to show itself: no further page load, no further ask for the conversation.
    await page.waitForTimeout(3000);
    expect(loads.length).toBeLessThanOrEqual(2);
    expect(loads.filter((url) => url.includes("notice=conversation_unavailable")).length).toBe(1);
    expect(seen.length).toBeLessThanOrEqual(1);
    await expect(page).toHaveURL(/\/dev\/business-preview\?notice=conversation_unavailable$/);
  });

  test("a chat on its own surface stays and renders", async ({ page }) => {
    test.skip(BUSINESS_BUILD, "consumer build only: /chat hops to /biz on a Business build");
    const seen: string[] = [];
    await openPreview(page, "/chat", { emptyChat: false });
    await serveSurface(page, "personal", seen);
    await page.goto("/chat?conversation=conversation-alpha");

    await expect(page.getByText("Lunch with the supplier").first()).toBeVisible();
    await expect(page).toHaveURL(/\/chat\?conversation=conversation-alpha$/);
  });

  test("a Business chat opened on /chat moves to /biz with its id", async ({ page }) => {
    const seen: string[] = [];
    await openPreview(page, "/chat", { emptyChat: false });
    await serveSurface(page, "business", seen);
    await page.goto("/chat?conversation=conversation-alpha");

    await expect(page).toHaveURL(/\/biz\?conversation=conversation-alpha$/);
  });

  test("an old /chat link on a Business build hops once to the Business shell with its id and stops", async ({ page }) => {
    test.skip(!BUSINESS_BUILD, "Business build only");
    // The server-side hop. The shell's own handling of a Personal id (the notice, no loop) is
    // asserted above on the preview page; the live /biz needs the real API, which this fixture cannot serve.
    const seen: string[] = [];
    await openPreview(page, "/chat", { emptyChat: false });
    await serveSurface(page, "personal", seen);
    const loads = countDocumentLoads(page);
    await page.goto("/chat?conversation=conversation-alpha");

    await expect(page).toHaveURL(/\/biz\?conversation=conversation-alpha$/);
    await page.waitForTimeout(3000);
    expect(loads.length).toBeLessThanOrEqual(2);
    await expect(page).not.toHaveURL(/\/chat/);
  });
});

test.describe("Business preview while its chat is off", () => {
  test.use({ viewport: { width: 1280, height: 800 } });
  const CHAT_OFF = `${PREVIEW}?chat=off`;

  async function openLoaded(page: Page, url = CHAT_OFF) {
    await openPreview(page, url, { emptyChat: false });
    await expect(panelHeading(page, "Hola")).toBeVisible();
    // The month-close step comes with the workspace payload, so chat_available has been read.
    await expect(
      page.getByTestId("workspace-panel-region").getByRole("button", { name: "Revisar", exact: true }),
    ).toBeVisible();
  }

  test("the shell keeps its records and offers no way into a chat", async ({ page }) => {
    await openLoaded(page, `${PREVIEW}?chat=on`);
    await expect(page.getByTestId("chat-input")).toHaveCount(1);

    await openLoaded(page);
    await expect(page.getByTestId("chat-input")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Nuevo chat/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Recientes/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "¿Cuánto gasté este mes?" })).toHaveCount(0);

    await page.keyboard.press("ControlOrMeta+Shift+Period");
    await page.keyboard.press("ControlOrMeta+Shift+Comma");
    await expect(page.getByTestId("chat-input")).toHaveCount(0);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(panelHeading(page, "Hola")).toBeVisible();

    await page.getByTestId("business-primary-upload").click();
    await expect(page.getByRole("dialog", { name: "Agregar" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);

    for (const [label, heading] of [
      ["Bandeja", "Bandeja"],
      ["Gastos", "Gastos"],
      ["Inicio", "Hola"],
    ]) {
      await nav(page).getByRole("button", { name: new RegExp(`^${label}`) }).click();
      await expect(panelHeading(page, heading)).toBeVisible();
      await expect(page.getByTestId("chat-input")).toHaveCount(0);
    }
  });

  test("search finds Business records and no chats", async ({ page }) => {
    await page.route("**/api/v1/search?**", (route) =>
      route.fulfill({ json: { items: [], next_cursor: null, ledger_groups: [] } }),
    );
    await openLoaded(page);
    await page.getByTestId("header-search").click();
    const input = page.getByPlaceholder("Busca comercio, monto o nota");
    await expect(input).toBeFocused();
    await expect(page.getByText("No hay conversaciones aún")).toHaveCount(0);
    await expect(page.locator("[data-palette-row-index]")).toHaveCount(0);

    await input.fill("nube hosting");
    const expenses = page.getByTestId("workspace-search-results").getByRole("group", { name: "Gastos" });
    await expect(expenses.getByRole("button")).toContainText("Nube Hosting");
    await expect(page.locator("[data-palette-row-index]")).toHaveCount(0);

    await input.fill("no such merchant anywhere");
    await expect(page.getByText(/No encontramos nada con/)).toBeVisible();
    await expect(page.getByRole("button", { name: /^Preguntar/ })).toHaveCount(0);
  });

  test("a chat link lands on the workspace panel", async ({ page }) => {
    await page.route("**/api/v1/conversations/*/messages?**", (route) =>
      route.fulfill({
        json: {
          items: [
            {
              id: "message-1",
              conversation_id: "conversation-alpha",
              role: "user",
              content: "Lunch with the supplier",
              created_at: "2026-10-08T12:00:00Z",
              metadata: {},
            },
          ],
          next_cursor: null,
          surface: "business",
        },
      }),
    );
    for (const url of [`${CHAT_OFF}&conversation=conversation-alpha`, `${CHAT_OFF}&view=chat`]) {
      await openLoaded(page, url);
      await expect(page.getByTestId("chat-input")).toHaveCount(0);
      await expect(page.getByText("Lunch with the supplier")).toHaveCount(0);
    }
  });
});

test.describe("Business preview on a phone while its chat is off", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the bottom tabs keep the destinations and Agregar, with no New chat or Recents", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?chat=off`);
    await expect(panelHeading(page, "Hola")).toBeVisible();
    const tabs = page.getByTestId("business-bottom-tabs");
    for (const label of ["Inicio", "Bandeja", "Gastos"]) {
      await expect(tabs.getByText(label, { exact: true })).toBeVisible();
    }
    await expect(page.getByTestId("add-menu-page").getByRole("button", { name: "Agregar" })).toBeVisible();
    await expect(page.getByRole("button", { name: /^Nuevo chat/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Recientes/ })).toHaveCount(0);
  });
});
