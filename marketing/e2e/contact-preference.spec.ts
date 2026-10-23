import { expect, test } from "@playwright/test";

const locales = {
  es: {
    path: "/contacto",
    send: "Enviar mensaje",
    phoneErrors: {
      empty: "Escribe tu número de WhatsApp.",
      length: "Escribe los 10 dígitos de tu número, incluido el código de área.",
      format: "Revisa el código de área y los demás dígitos de tu número.",
      region: "Usa un número de República Dominicana o Estados Unidos.",
    },
    emailSuccess: "Te responderemos al correo que escribiste.",
    whatsappSuccess: "Te responderemos por WhatsApp al número que escribiste.",
    phone: "Número de WhatsApp",
  },
  en: {
    path: "/en/contact",
    send: "Send message",
    phoneErrors: {
      empty: "Enter your WhatsApp number.",
      length: "Enter all 10 digits of your number, including the area code.",
      format: "Check the area code and the remaining digits of your number.",
      region: "Use a number from the Dominican Republic or the United States.",
    },
    emailSuccess: "We’ll reply to the email address you entered.",
    whatsappSuccess: "We’ll reply on WhatsApp at the number you entered.",
    phone: "WhatsApp number",
  },
} as const;

for (const locale of ["es", "en"] as const) {
  const copy = locales[locale];

  test.describe(`contact preference ${locale}`, () => {
    let submissions: Record<string, string>[];

    test.beforeEach(async ({ page }) => {
      submissions = [];
      await page.route("**/api/inquiries", async (route) => {
        submissions.push(route.request().postDataJSON());
        await route.fulfill({ status: 202, contentType: "application/json", body: "{}" });
      });
      await page.goto(copy.path);
      await page.locator("#contact-name").fill("Ana Peña");
      await page.locator("#contact-email").fill("ana@example.test");
    });

    test("phone errors explain each failure without moving Send", async ({ page, isMobile }) => {
      await page.getByRole("radio", { name: "WhatsApp" }).check();
      const phone = page.locator("#contact-phone");
      const error = page.locator("#contact-phone-error");
      const send = page.getByRole("button", { name: copy.send });
      const sendTop = async () => send.evaluate((button) => button.getBoundingClientRect().top + window.scrollY);
      const originalTop = await sendTop();
      await expect(phone).toHaveAttribute("placeholder", "+1 809 555 0123");
      await expect(error).toBeHidden();
      await expect(phone).toHaveAttribute("aria-invalid", "false");
      if (isMobile) await send.tap();
      else await send.click();
      await expect(error).toHaveText(copy.phoneErrors.empty);
      await expect(error).toBeVisible();
      await expect(phone).toBeFocused();
      expect(submissions).toHaveLength(0);
      expect(await sendTop()).toBeCloseTo(originalTop, 0);
      await phone.fill("8095550123");
      await phone.fill("");
      await expect(error).toBeHidden();
      await phone.focus();
      await page.locator("#contact-name").click();
      await expect(error).toHaveText(copy.phoneErrors.empty);
      await expect(error).toBeVisible();
      await expect(phone).toHaveAttribute("aria-invalid", "true");
      await expect(phone).toHaveAttribute("aria-describedby", "contact-phone-error");
      expect(await sendTop()).toBeCloseTo(originalTop, 0);
      await expect(phone).toHaveAttribute("required", "");
      if (isMobile) await send.tap();
      else await send.click();
      await expect(phone).toBeFocused();
      expect(submissions).toHaveLength(0);

      for (const [value, reason] of [
        ["1234", "length"],
        ["23123123123123", "length"],
        ["+1 809 555 012", "length"],
        ["+1 809 555 01234", "length"],
        ["0095550123", "format"],
        ["8091550123", "format"],
        ["+995550123", "region"],
        ["4165550123", "region"],
        ["+14165550123", "region"],
      ] as const) {
        await phone.fill(value);
        await expect(error).toBeHidden();
        await expect(phone).toHaveAttribute("aria-invalid", "false");
        expect(await sendTop()).toBeCloseTo(originalTop, 0);
        if (isMobile) await send.tap();
        else await send.click();
        await expect(phone).toBeFocused();
        await expect(error).toHaveText(copy.phoneErrors[reason]);
        await expect(error).toBeVisible();
        await expect(phone).toHaveAttribute("aria-invalid", "true");
        await expect(phone).toHaveAttribute("aria-describedby", "contact-phone-error");
        expect(await sendTop()).toBeCloseTo(originalTop, 0);
        expect(submissions).toHaveLength(0);
      }
    });

    test("WhatsApp submission sends a normalized number and confirms that channel", async ({ page }) => {
      await page.getByRole("radio", { name: "WhatsApp" }).check();
      await page.locator("#contact-phone").fill("(809) 555-0123");
      await page.getByRole("button", { name: copy.send }).click();
      await expect(page.getByText(copy.whatsappSuccess)).toBeVisible();
      await expect(page.getByRole("term").filter({ hasText: copy.phone })).toBeVisible();
      await expect(page.getByText("+1 809 555 0123", { exact: true })).toBeVisible();
      expect(submissions).toHaveLength(1);
      expect(submissions[0].description).toContain("Prefiere: WhatsApp +1 809 555 0123");
      expect(submissions[0].email).toBe("ana@example.test");
    });

    test("United States WhatsApp number is accepted", async ({ page }) => {
      await page.getByRole("radio", { name: "WhatsApp" }).check();
      await page.locator("#contact-phone").fill("+1 202 555 0123");
      await page.getByRole("button", { name: copy.send }).click();
      await expect(page.getByText(copy.whatsappSuccess)).toBeVisible();
      expect(submissions).toHaveLength(1);
      expect(submissions[0].description).toContain("Prefiere: WhatsApp +1 202 555 0123");
      await expect(page.getByRole("definition").filter({ hasText: "+1 202 555 0123" })).toBeVisible();
    });

    test("an unselected preference keeps the email confirmation", async ({ page }) => {
      await page.getByRole("button", { name: copy.send }).click();
      await expect(page.getByText(copy.emailSuccess)).toBeVisible();
      await expect(page.getByRole("term").filter({ hasText: copy.phone })).toHaveCount(0);
      await expect(page.getByText("+1 809 555 0123", { exact: true })).toHaveCount(0);
      expect(submissions).toHaveLength(1);
      expect(submissions[0].description).not.toContain("Prefiere:");
    });

    test("switching from WhatsApp to email clears the phone error and submitted number", async ({ page }) => {
      await page.getByRole("radio", { name: "WhatsApp" }).check();
      await page.locator("#contact-phone").fill("1234");
      await page.getByRole("button", { name: copy.send }).click();
      await expect(page.locator("#contact-phone-error")).toBeVisible();
      await page.getByRole("radio", { name: locale === "es" ? "Correo" : "Email" }).check();
      await expect(page.locator("#contact-phone-error")).toHaveCount(0);
      await page.getByRole("button", { name: copy.send }).click();
      await expect(page.getByText(copy.emailSuccess)).toBeVisible();
      expect(submissions).toHaveLength(1);
      expect(submissions[0].description).toContain("Prefiere: correo");
      expect(submissions[0].description).not.toContain("1234");
      await expect(page.getByRole("term").filter({ hasText: copy.phone })).toHaveCount(0);
    });
  });
}
