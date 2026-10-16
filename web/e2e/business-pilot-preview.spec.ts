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
    language: "en",
    theme: "light",
    emptyChat: options.emptyChat ?? true,
  });
  if (options.sidebarMode) {
    await page.addInitScript((mode) => {
      window.localStorage.setItem("cuadrao:business:sidebar_modes", JSON.stringify({ "breakpoint-user": mode }));
    }, options.sidebarMode);
  }
  await page.goto(url);
  await page.addStyleTag({ content: "nextjs-portal { display: none !important; }" });
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

test.describe("Business preview", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("switching Business twelve times with a receipt open and a draft typed never shows the account-changed screen; the record and its address close on each switch", async ({ page }) => {
    test.setTimeout(180_000);
    const switchTo = async (name: string) => {
      await page.getByTestId("business-switcher").getByRole("button").click();
      await page.getByRole("menuitem", { name: "Switch Business" }).click();
      await page.getByRole("option", { name: new RegExp(name) }).click();
      await expect(page.getByTestId("business-mark-trigger")).toHaveAccessibleName(new RegExp(name));
      await expect(page.getByText("Your account changed", { exact: false })).toHaveCount(0);
    };
    await openPreview(page, `${PREVIEW}?receipt=rcpt-ferreteria`);
    for (let round = 0; round < 6; round += 1) {
      // Each round: a receipt open in the own Business, a switch to the client, a draft typed, a switch back.
      if (round > 0) {
        await page.goto(`${PREVIEW}?receipt=rcpt-ferreteria`);
        await page.addStyleTag({ content: "nextjs-portal { display: none !important; }" });
      }
      await expect(panelHeading(page, "Review receipt")).toBeVisible();
      await switchTo("Colmado Peña");
      await expect(page).not.toHaveURL(/receipt=|expense=|draft=/);
      await expect(panelHeading(page, "Review receipt")).toHaveCount(0);
      await expect(page.getByTestId("business-client-cue")).toHaveText("Client: Colmado Peña");
      await page.getByTestId("chat-input").fill(`Pagué 850 en pintura ${round}`);
      await switchTo("Mi negocio");
      await expect(page.getByTestId("business-client-cue")).toHaveCount(0);
      // The typed draft is kept: a switch is a change of scope, not a navigation.
      await expect(page.getByTestId("chat-input")).toHaveText(`Pagué 850 en pintura ${round}`);
    }
  });

  test("an Overview draft survives a visit to the Inbox", async ({ page }) => {
    await openPreview(page);
    await expect(panelHeading(page, "Mi negocio")).toBeVisible();

    const composer = page.getByTestId("chat-input");
    await composer.click();
    await page.keyboard.type("How much did I spend on paint?");

    await nav(page).getByRole("button", { name: /^Inbox/ }).click();
    await expect(panelHeading(page, "Inbox")).toBeVisible();
    await expect(page.getByTestId("chat-input")).toHaveCount(0);

    await nav(page).getByRole("button", { name: /^Overview/ }).click();
    await expect(panelHeading(page, "Mi negocio")).toBeVisible();
    await expect(page.getByTestId("chat-input")).toHaveText("How much did I spend on paint?");
  });

  test("the Create menu opens from the collapsed rail inside the viewport", async ({ page }) => {
    await openPreview(page, PREVIEW, { sidebarMode: "collapsed" });
    await expect(panelHeading(page, "Mi negocio")).toBeVisible();

    const trigger = page.getByTestId("business-create");
    await expect(trigger).toHaveAccessibleName("Create");
    await trigger.focus();
    await page.keyboard.press("Enter");

    const menu = page.getByRole("menu", { name: "Create" });
    await expect(menu).toBeVisible();
    const box = await menu.boundingBox();
    const viewport = page.viewportSize();
    expect(box && viewport).toBeTruthy();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(viewport!.width);
    expect(box!.y + box!.height).toBeLessThanOrEqual(viewport!.height);

    const items = menu.getByRole("menuitem");
    await expect(items).toHaveText(["Upload receipt", "Record expense"]);
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
    await openPreview(page, `${PREVIEW}?conversation=conversation-alpha`, { emptyChat: false });
    await expect(page.getByTestId("workspace-panel-region")).toHaveCount(0);
    await expect(page.getByTestId("chat-input")).toBeVisible();

    await nav(page).getByRole("button", { name: /^Inbox/ }).click();
    await expect(panelHeading(page, "Inbox")).toBeVisible();
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveURL(/\/dev\/business-preview\?view=inbox$/);

    await page.reload();
    await expect(panelHeading(page, "Inbox")).toBeVisible();
  });

  test("receipt entry marks missing fields and requires separate canonical approval", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?receipt=rcpt-ferreteria`);
    await expect(panelHeading(page, "Review receipt")).toBeVisible();

    const needed = page.getByText("Needed", { exact: true });
    await expect(needed).toHaveCount(1);
    const paidFrom = page.locator("label", { hasText: "Paid from" });
    await expect(paidFrom.getByText("Needed", { exact: true })).toBeVisible();
    const save = page.getByRole("button", { name: "Save review details" });
    await expect(save).toBeDisabled();

    await paidFrom.locator("select").selectOption("acct-ops");
    await expect(needed).toHaveCount(0);
    await save.click();

    await expect(panelHeading(page, "Ferretería La Esquina")).toBeVisible();
    await expect(page.getByText("One expense was recorded", { exact: false })).toHaveCount(0);
    await page.getByRole("button", { name: "Approve expense", exact: true }).click();
    await expect(page.getByRole("status").filter({ hasText: "One expense was recorded" })).toBeVisible();
    await page.getByTestId("workspace-panel-region").getByRole("button", { name: "Expenses", exact: true }).click();
    await expect(panelHeading(page, "Expenses")).toBeVisible();
    await expect(page.getByTestId("workspace-panel-region")).toContainText("Ferretería La Esquina");
  });

  test("an unknown AI outcome offers a consented retry beside entry by hand", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?receipt=rcpt-unknown`);
    const attention = page.getByTestId("receipt-attention");
    await expect(attention).toContainText("We couldn't recover the AI reading result");
    await expect(attention).toContainText("Trying again sends this receipt to our AI provider.");
    await expect(page.getByRole("button", { name: "Prepare with AI" })).toHaveCount(0);
    await expect(page.getByLabel("Merchant")).toBeEnabled();

    await attention.getByRole("button", { name: "Try again with AI" }).click();
    await expect(page.getByTestId("workspace-panel-region")).toContainText("Reading your receipt");
    await expect(page.getByRole("button", { name: "Try again with AI" })).toHaveCount(0);
    await expect(page.getByLabel("Merchant")).toBeDisabled();
  });

  test("a read with no single purchase is entered by hand and keeps what was read", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?receipt=rcpt-ambiguous`);
    const attention = page.getByTestId("receipt-attention");
    await expect(attention).toContainText("couldn't match this receipt to one purchase. Enter the details yourself");
    await expect(page.getByRole("button", { name: /with AI/ })).toHaveCount(0);
    await expect(page.getByText("What the receipt says")).toBeVisible();

    await page.getByLabel("Merchant").fill("Colmado Don Pedro");
    await page.getByLabel("Date").fill("2026-10-05");
    await page.locator("label", { hasText: "Currency" }).locator("select").selectOption("DOP");
    await page.getByTestId("receipt-review-amount").fill("706.10");
    await page.locator("label", { hasText: "Paid from" }).locator("select").selectOption("acct-ops");
    await page.getByRole("button", { name: "Save review details" }).click();

    await expect(panelHeading(page, "Colmado Don Pedro")).toBeVisible();
    await expect(page.getByTestId("receipt-attention")).toHaveCount(0);
    await expect(page.getByTestId("receipt-original-source")).toBeVisible();
    await page.getByRole("button", { name: "Approve expense", exact: true }).click();
    await expect(page.getByRole("status").filter({ hasText: "One expense was recorded" })).toBeVisible();
  });

  test("an unreadable receipt offers entry by hand and no AI retry", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?receipt=rcpt-blurry`);
    await expect(page.getByTestId("receipt-attention")).toContainText(
      "We couldn't read this receipt. Enter the details yourself or send a clearer photo.",
    );
    await expect(page.getByRole("button", { name: /with AI/ })).toHaveCount(0);
    await expect(page.getByLabel("Merchant")).toBeEnabled();
  });

  test("the review Total refuses letters, pads on blur and refuses a decimal comma paste", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await openPreview(page, `${PREVIEW}?receipt=rcpt-ferreteria`);
    await expect(panelHeading(page, "Review receipt")).toBeVisible();

    const total = page.getByTestId("receipt-review-amount");
    await expect(total).toHaveValue("3,450.00");
    await expect(total).toHaveAccessibleName("Total in DOP (RD$)");
    const message = await amountMessage(page, total);

    await total.click();
    await page.keyboard.press("End");
    await page.keyboard.type("wfr");
    await expect(total).toHaveValue("3,450.00");
    await expect(message).toHaveText("Use digits and one decimal point.");

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
    await expect(message).toContainText("Use a point for decimals");
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
    await expect(message).toHaveText("$ could mean RD$ or US$. Enter the amount without a symbol, or with RD$ or US$.");
  });

  test("a currency change keeps the digits and says there is no conversion", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?receipt=rcpt-ferreteria`);
    const total = page.getByTestId("receipt-review-amount");
    await expect(total).toHaveValue("3,450.00");
    const message = await amountMessage(page, total);

    await page.locator("label", { hasText: "Currency" }).locator("select").selectOption("USD");
    await expect(total).toHaveAccessibleName("Total in USD (US$)");
    await expect(total).toHaveValue("3,450.00");
    await expect(message).toHaveText("Same amount, no conversion.");

    await total.click();
    await page.keyboard.press("End");
    await page.keyboard.press("Backspace");
    await expect(message).toHaveText("");
  });

  test("Total announces Needed when the backend lists the amount as missing", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?receipt=rcpt-saved`);
    const total = page.getByTestId("receipt-review-amount");
    await expect(total).toHaveAccessibleDescription(/Needed/);
    await total.click();
    await page.keyboard.type("80");
    await expect(total).not.toHaveAccessibleDescription(/Needed/);
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
    await expect(message).toHaveText("Check the thousands commas, as in 1,250.50.");
  });

  test("the review maps the backend's amount_out_of_range onto its Total", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?receipt=rcpt-ferreteria`);
    const total = page.getByTestId("receipt-review-amount");
    await expect(total).toHaveValue("3,450.00");
    await page.locator("label", { hasText: "Paid from" }).locator("select").selectOption("acct-ops");

    await page.evaluate(() => {
      (globalThis as { __businessFixtureFailNextWrite?: string }).__businessFixtureFailNextWrite = "amount_out_of_range";
    });
    await page.getByRole("button", { name: "Save review details" }).click();

    await expect(await amountMessage(page, total)).toHaveText("This amount is too large to record.");
    await expect(total).toHaveAttribute("aria-invalid", "true");
    await expect(panelHeading(page, "Review receipt")).toBeVisible();
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
    await openPreview(page, `${PREVIEW}?view=chat`);
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

  test("the drawer shows the Business destinations with labels and Create", async ({ page }) => {
    await openPreview(page);
    await expect(panelHeading(page, "Mi negocio")).toBeVisible();

    await page.getByTestId("chat-shell-menu-trigger").click();

    const drawerNav = nav(page);
    for (const label of ["Overview", "Inbox", "Expenses", "Updates"]) {
      await expect(drawerNav.getByText(label, { exact: true })).toBeVisible();
    }
    await expect(drawerNav.getByRole("button", { name: /^Inbox/ })).toContainText("5");
    await expect(page.getByTestId("business-create")).toHaveText("Create");
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
    await expect(notice).toContainText("This conversation isn't available in Cuadrao Business.");
    await expect(notice.getByRole("link", { name: "Go to Cuadrao Business" })).toHaveAttribute("href", "/biz");
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
    await expect(panelHeading(page, "Mi negocio")).toBeVisible();
    // The inbox chip comes with the workspace payload, so chat_available has been read.
    await expect(
      page.getByTestId("workspace-panel-region").getByRole("button", { name: /^Review \d+ receipts/ }),
    ).toBeVisible();
  }

  test("the shell keeps its records and offers no way into a chat", async ({ page }) => {
    await openLoaded(page, PREVIEW);
    await expect(page.getByTestId("chat-input")).toHaveCount(1);
    await expect(page.getByRole("button", { name: /^New chat/ })).toHaveCount(1);
    await expect(page.getByRole("button", { name: /^Recents/ })).toHaveCount(1);

    await openLoaded(page);
    await expect(page.getByTestId("chat-input")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^New chat/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Recents/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "What did I spend this month?" })).toHaveCount(0);

    await page.keyboard.press("ControlOrMeta+Shift+Period");
    await page.keyboard.press("ControlOrMeta+Shift+Comma");
    await expect(page.getByTestId("chat-input")).toHaveCount(0);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(panelHeading(page, "Mi negocio")).toBeVisible();

    await page.getByTestId("business-create").click();
    await expect(page.getByRole("menu", { name: "Create" }).getByRole("menuitem")).toHaveText([
      "Upload receipt",
      "Record expense",
      "Save a note",
    ]);
    await page.keyboard.press("Escape");

    for (const [label, heading] of [
      ["Inbox", "Inbox"],
      ["Expenses", "Expenses"],
      ["Updates", "Updates"],
      ["Overview", "Mi negocio"],
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
    await page.getByRole("button", { name: /^Search/ }).first().click();
    const input = page.getByPlaceholder("Search expenses and receipts");
    await expect(input).toBeFocused();
    await expect(page.getByText("No conversations yet")).toHaveCount(0);
    await expect(page.locator("[data-palette-row-index]")).toHaveCount(0);

    await input.fill("nube hosting");
    const expenses = page.getByTestId("workspace-search-results").getByRole("group", { name: "Expenses" });
    await expect(expenses.getByRole("button")).toContainText("Nube Hosting");
    await expect(page.locator("[data-palette-row-index]")).toHaveCount(0);

    await input.fill("no such merchant anywhere");
    await expect(page.getByText("No results found")).toBeVisible();
    await expect(page.getByRole("button", { name: /^Ask/ })).toHaveCount(0);
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

  test("the drawer keeps the destinations and Create, with no New chat or Recents", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?chat=off`);
    await expect(panelHeading(page, "Mi negocio")).toBeVisible();
    await page.getByTestId("chat-shell-menu-trigger").click();
    for (const label of ["Overview", "Inbox", "Expenses", "Updates"]) {
      await expect(nav(page).getByText(label, { exact: true })).toBeVisible();
    }
    await expect(page.getByTestId("business-create").first()).toBeVisible();
    await expect(page.getByRole("button", { name: /^New chat/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Recents/ })).toHaveCount(0);
  });
});
