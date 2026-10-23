import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, useState } from "react";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import AuthForm, { type AuthFormMode, type AuthFormSubmission } from "../components/auth/AuthForm";
import es from "../public/locales/es-419/common.json";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function fill(input: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

test.each(["signup", "login"] as const)("%s reveals password locally, supports edit, and submits once", async (initialMode) => {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: es } } });
  const host = document.createElement("div"); document.body.appendChild(host);
  const root = createRoot(host);
  const submissions: AuthFormSubmission[] = [];
  function Flow() {
    const [mode, setMode] = useState<AuthFormMode>(initialMode);
    return <AuthForm emailFirst mode={mode} onModeChange={setMode} onSubmit={async value => { submissions.push(value); }} />;
  }
  await act(async () => root.render(<I18nextProvider i18n={i18n}><Flow /></I18nextProvider>));
  const submit = () => act(async () => { host.querySelector("form")?.requestSubmit(); });
  const emailInput = () => host.querySelector('input[type="email"]') as HTMLInputElement;
  const passwordInput = () => host.querySelector('[data-open="true"] input[autocomplete$="password"]') as HTMLInputElement | null;
  expect(passwordInput()).toBeNull();
  await submit();
  expect(submissions.length).toBe(0);
  expect(emailInput().getAttribute("aria-invalid")).toBe("true");
  await fill(emailInput(), "ada@example.com");
  await submit();
  expect(submissions.length).toBe(0);
  expect(passwordInput()).not.toBeNull();
  await act(async () => { await new Promise<void>(resolve => requestAnimationFrame(() => resolve())); });
  expect(document.activeElement).toBe(passwordInput());
  expect(passwordInput()?.type).toBe("password");
  await fill(passwordInput()!, "synthetic-password47");
  const edit = [...host.querySelectorAll("button")].find(b => b.textContent === "Editar")!;
  await act(async () => edit.click());
  expect(emailInput().value).toBe("ada@example.com");
  expect(passwordInput()).toBeNull();
  await submit();
  expect(passwordInput()?.value).toBe("");
  await fill(passwordInput()!, "synthetic-password47");
  await submit();
  expect(submissions).toEqual([{ mode: initialMode, email: "ada@example.com", displayName: "", password: "synthetic-password47" }]);
  const sharedEmail = emailInput();
  const sharedForm = host.querySelector("form");
  const sharedButton = host.querySelector("button[type=submit]");
  const switchMode = [...host.querySelectorAll("button")].find(b => b.textContent === (initialMode === "signup" ? "Iniciar sesión" : "Registrarse"))!;
  await act(async () => switchMode.click());
  expect(emailInput()).toBe(sharedEmail);
  expect(host.querySelector("form")).toBe(sharedForm);
  expect(host.querySelector("button[type=submit]")).toBe(sharedButton);
  expect(passwordInput()).toBeNull();
  expect(emailInput().value).toBe("ada@example.com");
  await submit();
  expect(passwordInput()?.value).toBe("");
  const switchBack = [...host.querySelectorAll("button")].find(b => b.textContent === (initialMode === "signup" ? "Registrarse" : "Iniciar sesión"))!;
  await act(async () => switchBack.click());
  expect(passwordInput()).toBeNull();
  expect(emailInput().value).toBe("ada@example.com");
  await act(async () => root.unmount()); host.remove();
});
