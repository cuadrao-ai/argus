import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import i18next from "i18next";
import { act, createElement, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { I18nextProvider } from "react-i18next";

import AuthForm from "../components/auth/AuthForm";
import es419 from "../public/locales/es-419/common.json";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function setNativeValue(element: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  await act(async () => {
    setter?.call(element, value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function renderSpanishSignup(props: {
  onConfirmEmailCode?: (input: { email: string; code: string }) => Promise<void>;
  onEmailConfirmed?: () => void | Promise<void>;
}) {
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: "es-419",
    fallbackLng: false,
    interpolation: { escapeValue: false },
    resources: { "es-419": { translation: es419 } },
  });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root: Root = createRoot(host);
  await act(async () => {
    root.render(
      createElement(
        I18nextProvider,
        { i18n },
        createElement(AuthForm, {
          mode: "signup",
          onSubmit: async () => ({ status: "email_confirmation_required" as const }),
          ...props,
        }) as ReactNode,
      ),
    );
  });

  const signupForm = host.querySelector("form");
  if (!signupForm) throw new Error("signup form missing");
  const fields = signupForm.querySelectorAll("input");
  await setNativeValue(fields[0] as HTMLInputElement, "Ada");
  await setNativeValue(fields[1] as HTMLInputElement, "ada@example.com");
  await setNativeValue(fields[2] as HTMLInputElement, "correct-horse");
  const signupButton = signupForm.querySelector("button[type='submit']");
  await act(async () => {
    signupForm.requestSubmit(signupButton as HTMLButtonElement);
  });
  return { host, root };
}

describe("signup confirmation code", () => {
  test("Spanish signup accepts the email code and still mentions the link", async () => {
    const confirmed: Array<{ email: string; code: string }> = [];
    let finished = 0;
    const page = await renderSpanishSignup({
      onConfirmEmailCode: async (input) => {
        confirmed.push(input);
      },
      onEmailConfirmed: () => {
        finished += 1;
      },
    });

    const state = page.host.querySelector("[data-testid='auth-check-email']");
    const heading = state?.querySelector("h2");
    const code = page.host.querySelector(
      "[data-testid='auth-confirmation-code']",
    ) as HTMLInputElement | null;
    expect(heading?.textContent).toBe("Revisa tu correo");
    expect(document.activeElement).toBe(heading);
    expect(code).not.toBeNull();
    expect(document.activeElement).not.toBe(code);
    expect(code?.getAttribute("autocomplete")).toBe("one-time-code");
    expect(code?.getAttribute("inputmode")).toBe("numeric");
    expect(state?.textContent).toContain("Abre el enlace que te enviamos y entrarás directo a Cuadrao.");
    expect(page.host.textContent).toContain("Código de confirmación");

    await setNativeValue(code as HTMLInputElement, "123 456");
    const confirmForm = code?.closest("form");
    await act(async () => {
      confirmForm?.requestSubmit(confirmForm.querySelector("button[type='submit']") as HTMLButtonElement);
    });

    expect(confirmed).toEqual([{ email: "ada@example.com", code: "123456" }]);
    expect(finished).toBe(1);
    await act(async () => {
      page.root.unmount();
    });
  });

  test("a rejected code stays on the confirmation step in Spanish", async () => {
    let finished = 0;
    const page = await renderSpanishSignup({
      onConfirmEmailCode: async () => {
        throw Object.assign(new Error("Token has expired or is invalid"), {
          code: "otp_rejected",
        });
      },
      onEmailConfirmed: () => {
        finished += 1;
      },
    });

    const code = page.host.querySelector(
      "[data-testid='auth-confirmation-code']",
    ) as HTMLInputElement;
    await setNativeValue(code, "000000");
    const confirmForm = code.closest("form");
    await act(async () => {
      confirmForm?.requestSubmit();
    });

    expect(page.host.textContent).toContain(
      "Ese código no fue aceptado. Revisa el correo e inténtalo de nuevo.",
    );
    expect(page.host.textContent).not.toContain("Token has expired");
    expect(finished).toBe(0);
    expect(page.host.querySelector("[data-testid='auth-check-email']")).not.toBeNull();
    await act(async () => {
      page.root.unmount();
    });
  });
});
