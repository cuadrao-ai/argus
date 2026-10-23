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
  await setNativeValue(signupForm.querySelector('input[autocomplete="given-name"]') as HTMLInputElement, "Ada");
  await setNativeValue(signupForm.querySelector('input[autocomplete="family-name"]') as HTMLInputElement, "Peña");
  await setNativeValue(signupForm.querySelector('input[type="email"]') as HTMLInputElement, "ada@example.com");
  await setNativeValue(signupForm.querySelector('input[autocomplete="new-password"]') as HTMLInputElement, "correct-horse");
  const signupButton = signupForm.querySelector("button[type='submit']");
  await act(async () => {
    signupForm.requestSubmit(signupButton as HTMLButtonElement);
  });
  return { host, root };
}

describe("signup confirmation code", () => {
  test.each(["12345678", "1234 5678", "0123 4567"])("Spanish signup accepts code %s and names the address", async (enteredCode) => {
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
    expect(code?.type).toBe("text");
    expect(state?.querySelectorAll("[data-otp-slot]").length).toBe(8);
    expect(state?.querySelectorAll("input").length).toBe(1);
    expect(state?.querySelector("[data-confirmation-illustration]")?.getAttribute("aria-hidden")).toBe("true");
    expect(state?.textContent).toContain("¿No ves el correo? Revisa la carpeta de spam.");
    expect(state?.getAttribute("role")).not.toBe("status");
    expect(state?.textContent).toContain("Escribe el código que te enviamos a ada@example.com.");
    expect(page.host.textContent).toContain("Código de confirmación");

    await setNativeValue(code as HTMLInputElement, enteredCode);
    const confirmForm = code?.closest("form");
    await act(async () => {
      confirmForm?.requestSubmit(confirmForm.querySelector("button[type='submit']") as HTMLButtonElement);
    });

    expect(confirmed).toEqual([{ email: "ada@example.com", code: enteredCode.replaceAll(" ", "") }]);
    expect(finished).toBe(1);
    expect(code?.readOnly).toBe(true);
    expect(state?.querySelector("[data-otp-status]")?.getAttribute("data-otp-status")).toBe("verified");
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
    await setNativeValue(code, "00000000");
    const confirmForm = code.closest("form");
    await act(async () => {
      confirmForm?.requestSubmit();
    });

    expect(page.host.querySelector("#auth-confirmation-code-note")?.textContent).toContain(
      "Revisa el código e inténtalo de nuevo.",
    );
    expect(page.host.textContent).not.toContain("Token has expired");
    expect(finished).toBe(0);
    expect(code.value).toBe("");
    expect(document.activeElement).toBe(code);
    expect(page.host.querySelector("[data-testid='auth-check-email']")).not.toBeNull();
    await act(async () => {
      page.root.unmount();
    });
  });
  test.each(["123", "123456", "1234567"])("incomplete code %s does not verify or erase the entered digits", async (partialCode) => {
    let requests = 0;
    const page = await renderSpanishSignup({ onConfirmEmailCode: async () => { requests += 1; } });
    const code = page.host.querySelector("[data-testid='auth-confirmation-code']") as HTMLInputElement;
    await setNativeValue(code, partialCode);
    await act(async () => { code.closest("form")?.requestSubmit(); });
    expect(requests).toBe(0);
    expect(code.value).toBe(partialCode);
    expect(code.getAttribute("aria-invalid")).toBe("true");
    await act(async () => { page.root.unmount(); });
  });

  test("verification locks the code and prevents duplicate requests", async () => {
    let requests = 0;
    let finish: () => void = () => {};
    const pending = new Promise<void>((resolve) => { finish = resolve; });
    const page = await renderSpanishSignup({ onConfirmEmailCode: async () => { requests += 1; await pending; } });
    const code = page.host.querySelector("[data-testid='auth-confirmation-code']") as HTMLInputElement;
    await setNativeValue(code, "12345678");
    await act(async () => {
      code.closest("form")?.requestSubmit();
      code.closest("form")?.requestSubmit();
    });
    expect(requests).toBe(1);
    expect(code.readOnly).toBe(true);
    await act(async () => { finish(); });
    expect(code.readOnly).toBe(true);
    await act(async () => { page.root.unmount(); });
  });

});
