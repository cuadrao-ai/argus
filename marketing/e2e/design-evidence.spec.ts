import { expect, test } from "@playwright/test";

const cases = [
  {
    locale: "es",
    home: "/",
    contact: "/contacto",
    language: "Idioma",
    contactAction: "Hablemos de tu negocio",
    login: "Iniciar sesión",
    menu: "Abrir menú",
    send: "Enviar mensaje",
    email: "Correo",
    emptyPhone: "Escribe tu número de WhatsApp.",
    unsupportedPhone: "Usa un número de República Dominicana o Estados Unidos.",
    emailSuccess: "Te responderemos al correo que escribiste.",
    whatsappSuccess: "Te responderemos por WhatsApp al número que escribiste.",
  },
  {
    locale: "en",
    home: "/en",
    contact: "/en/contact",
    language: "Language",
    contactAction: "Let’s talk about your business",
    login: "Log in",
    menu: "Open menu",
    send: "Send message",
    email: "Email",
    emptyPhone: "Enter your WhatsApp number.",
    unsupportedPhone: "Use a number from the Dominican Republic or the United States.",
    emailSuccess: "We’ll reply to the email address you entered.",
    whatsappSuccess: "We’ll reply on WhatsApp at the number you entered.",
  },
] as const;

for (const copy of cases) {
  test(`${copy.locale} Business header evidence`, async ({ page }, info) => {
    await page.goto(copy.home);
    const header = page.locator("header");
    const menu = header.getByRole("button", { name: copy.menu });
    if (await menu.isVisible()) await menu.click();
    const nav = header.locator("nav:visible");
    const screenshot = { path: info.outputPath(`design-evidence-${copy.locale}-header-mock.png`), animations: "disabled" as const };
    if (info.project.name === "mobile") await page.screenshot(screenshot);
    else await header.screenshot(screenshot);

    const language = nav.getByRole("group", { name: copy.language });
    const contact = nav.getByRole("link", { name: copy.contactAction, exact: true });
    const login = nav.getByRole("button", { name: copy.login, exact: true });
    await expect(language).toBeVisible();
    await expect(contact).toHaveAttribute("href", "/contacto");
    await expect(login).toHaveAttribute("data-preview-unwired", "true");
    const boxes = await Promise.all([language, contact, login].map((item) => item.boundingBox()));
    if (info.project.name === "mobile") {
      expect(boxes[0]!.y).toBeLessThan(boxes[1]!.y);
      expect(boxes[1]!.y).toBeLessThan(boxes[2]!.y);
    } else {
      expect(boxes[0]!.x).toBeLessThan(boxes[1]!.x);
      expect(boxes[1]!.x).toBeLessThan(boxes[2]!.x);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  });

  test(`${copy.locale} selected phone errors evidence`, async ({ page }, info) => {
    let submissions = 0;
    await page.route("**/api/inquiries", async (route) => {
      submissions += 1;
      await route.fulfill({ status: 202, contentType: "application/json", body: "{}" });
    });
    await page.goto(copy.contact);
    await page.locator("#contact-name").fill("Ana Peña");
    await page.locator("#contact-email").fill("ana@example.test");
    await page.getByRole("radio", { name: "WhatsApp" }).check();
    const send = page.getByRole("button", { name: copy.send });
    const sendTop = await send.evaluate((button) => button.getBoundingClientRect().top + scrollY);

    await send.click();
    const error = page.locator("#contact-phone-error");
    await expect(error).toHaveText(copy.emptyPhone);
    await page.screenshot({ path: info.outputPath(`design-evidence-${copy.locale}-phone-empty-mock.png`), fullPage: true, animations: "disabled" });
    await page.locator("#contact-phone").fill("+1 416 555 0123");
    await send.click();
    await expect(error).toHaveText(copy.unsupportedPhone);
    await page.screenshot({ path: info.outputPath(`design-evidence-${copy.locale}-phone-region-mock.png`), fullPage: true, animations: "disabled" });
    expect(submissions).toBe(0);
    expect(await send.evaluate((button) => button.getBoundingClientRect().top + scrollY)).toBeCloseTo(sendTop, 0);
  });

  test(`${copy.locale} email confirmation evidence`, async ({ page }, info) => {
    const submissions: Record<string, string>[] = [];
    await page.route("**/api/inquiries", async (route) => {
      submissions.push(route.request().postDataJSON());
      await route.fulfill({ status: 202, contentType: "application/json", body: "{}" });
    });
    await page.goto(copy.contact);
    await page.locator("#contact-name").fill("Ana Peña");
    await page.locator("#contact-email").fill("ana@example.test");
    await page.getByRole("radio", { name: copy.email }).check();
    await page.getByRole("button", { name: copy.send }).click();
    await expect(page.getByText(copy.emailSuccess)).toBeVisible();
    await page.screenshot({ path: info.outputPath(`design-evidence-${copy.locale}-email-success-mock.png`), fullPage: true, animations: "disabled" });
    expect(submissions).toHaveLength(1);
    expect(submissions[0].email).toBe("ana@example.test");
    expect(submissions[0].description).not.toContain("WhatsApp");
    await expect(page.getByRole("term").filter({ hasText: /WhatsApp number|Número de WhatsApp/ })).toHaveCount(0);
  });

  test(`${copy.locale} WhatsApp confirmation evidence`, async ({ page }, info) => {
    const submissions: Record<string, string>[] = [];
    await page.route("**/api/inquiries", async (route) => {
      submissions.push(route.request().postDataJSON());
      await route.fulfill({ status: 202, contentType: "application/json", body: "{}" });
    });
    await page.goto(copy.contact);
    await page.locator("#contact-name").fill("Ana Peña");
    await page.locator("#contact-email").fill("ana@example.test");
    await page.getByRole("radio", { name: "WhatsApp" }).check();
    await page.locator("#contact-phone").fill("(809) 555-0123");
    await page.getByRole("button", { name: copy.send }).click();
    await expect(page.getByText(copy.whatsappSuccess)).toBeVisible();
    await page.screenshot({ path: info.outputPath(`design-evidence-${copy.locale}-whatsapp-success-mock.png`), fullPage: true, animations: "disabled" });
    expect(submissions).toHaveLength(1);
    expect(submissions[0].description).toContain("Prefiere: WhatsApp +1 809 555 0123");
    await expect(page.getByText("+1 809 555 0123", { exact: true })).toBeVisible();
  });
}
