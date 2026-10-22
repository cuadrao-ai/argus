import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import i18next from "i18next";
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import AuthForm, { type AuthFormSubmission } from "../components/auth/AuthForm";
import en from "../public/locales/en/common.json";
import es419 from "../public/locales/es-419/common.json";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function setValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  await act(async () => {
    setter?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function renderSignup(language = "es-419") {
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: language, fallbackLng: false,
    resources: { en: { translation: en }, "es-419": { translation: es419 } },
  });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const submissions: AuthFormSubmission[] = [];
  await act(async () => {
    root.render(createElement(I18nextProvider, { i18n }, createElement(AuthForm, {
      mode: "signup", onSubmit: async (submission) => { submissions.push(submission); },
    })));
  });
  return {
    host, submissions,
    async close() { await act(async () => root.unmount()); host.remove(); },
  };
}

describe("signup names", () => {
  test.each([
    ["es-419", "Nombre", "Apellido"],
    ["en", "First name", "Last name"],
  ])("%s names have translated accessible labels and autofill purposes", async (language, first, last) => {
    const page = await renderSignup(language);
    try {
      const given = page.host.querySelector<HTMLInputElement>('input[autocomplete="given-name"]');
      const family = page.host.querySelector<HTMLInputElement>('input[autocomplete="family-name"]');
      expect(given?.labels?.[0]?.textContent).toContain(first);
      expect(family?.labels?.[0]?.textContent).toContain(last);
      expect(given?.required).toBe(false);
      expect(family?.required).toBe(false);
    } finally { await page.close(); }
  });

  test.each([
    ["  María José  ", "  De la Cruz Peña  ", "María José De la Cruz Peña"],
    ["Ada", "", "Ada"],
    ["", "Peña", "Peña"],
    ["", "", ""],
  ])("submits %s and %s through the existing displayName contract", async (first, last, expected) => {
    const page = await renderSignup();
    try {
      const given = page.host.querySelector<HTMLInputElement>('input[autocomplete="given-name"]');
      const family = page.host.querySelector<HTMLInputElement>('input[autocomplete="family-name"]');
      expect(given).not.toBeNull();
      expect(family).not.toBeNull();
      await setValue(given!, first);
      await setValue(family!, last);
      await setValue(page.host.querySelector<HTMLInputElement>('input[type="email"]')!, "synthetic@example.com");
      await setValue(page.host.querySelector<HTMLInputElement>('input[autocomplete="new-password"]')!, "synthetic-password");
      await act(async () => page.host.querySelector("form")!.requestSubmit());
      expect(page.submissions).toEqual([{
        mode: "signup", displayName: expected,
        email: "synthetic@example.com", password: "synthetic-password",
      }]);
    } finally { await page.close(); }
  });
});
