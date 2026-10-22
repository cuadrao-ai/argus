import { afterAll, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import i18next from "i18next";
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import AuthForm, { type AuthFormMode, type AuthFormSubmissionResult } from "../components/auth/AuthForm";
import en from "../public/locales/en/common.json";
import es419 from "../public/locales/es-419/common.json";
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  HTMLElement.prototype.scrollIntoView = () => {};
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
async function fill(input: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
async function blur(input: HTMLInputElement) { await act(async () => { input.focus(); input.blur(); }); }
async function mount(onSubmit: () => Promise<AuthFormSubmissionResult | void> = async () => {}, mode: AuthFormMode = "signup") {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "en", fallbackLng: false, resources: { en: { translation: en }, "es-419": { translation: es419 } } });
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  const render = async (next: AuthFormMode) => act(async () => {
    root.render(createElement(I18nextProvider, { i18n }, createElement(AuthForm, { mode: next, onSubmit, onModeChange: () => {} })));
  });
  await render(mode);
  return { host, i18n, render,
    email: () => host.querySelector<HTMLInputElement>('input[type="email"]')!,
    password: () => host.querySelector<HTMLInputElement>('input[autocomplete$="password"]')!,
    submit: async () => act(async () => { host.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); }),
    close: async () => { await act(async () => root.unmount()); host.remove(); },
  };
}
test("labels persist; errors wait for blur then clear live; success describes email format", async () => {
  const p = await mount();
  try {
    expect(p.host.querySelector("form")!.noValidate).toBe(true);
    expect(document.activeElement).not.toBe(p.email());
    expect(p.email().labels?.[0]?.textContent).toBe("Email address");
    await blur(p.email()); expect(p.email().getAttribute("aria-invalid")).toBeNull();
    await fill(p.email(), "a"); expect(p.email().getAttribute("aria-invalid")).toBeNull();
    await blur(p.email()); expect(p.email().getAttribute("aria-invalid")).toBe("true");
    await fill(p.email(), "person@example.com"); expect(p.email().getAttribute("aria-invalid")).toBeNull();
    expect(document.getElementById(p.email().getAttribute("aria-describedby")!)?.textContent).toContain("Email format looks right");
  } finally { await p.close(); }
});
test.each(["signup", "login"] as const)("%s focuses the first invalid field without a duplicate banner", async (mode) => {
  let calls = 0; const p = await mount(async () => { calls++; }, mode);
  try {
    await p.submit();
    expect(p.host.querySelector('[data-testid="form-error-summary"]')).toBeNull();
    expect(p.host.querySelector('[data-auth-feedback]')).toBeNull();
    expect(document.activeElement).toBe(p.email());
    expect(p.email().getAttribute("aria-describedby")).not.toBeNull();
    await fill(p.password(), "long-enough"); expect(p.email().getAttribute("aria-invalid")).toBe("true");
    await act(async () => { await p.i18n.changeLanguage("es-419"); });
    expect(p.host.textContent).toContain("Escribe tu correo"); expect(calls).toBe(0);
  } finally { await p.close(); }
});
test("editing a valid first-blur value revokes its check until the next blur", async () => {
  const p = await mount();
  try {
    await fill(p.email(), "one@example.com"); await blur(p.email()); expect(p.email().getAttribute("aria-describedby")).not.toBeNull();
    await fill(p.email(), "two@example.com"); expect(p.email().getAttribute("aria-describedby")).toBeNull();
    await blur(p.email()); expect(p.email().getAttribute("aria-describedby")).not.toBeNull();
  } finally { await p.close(); }
});
test("sign-in accepts an existing short password without strength coaching", async () => {
  let calls = 0; const p = await mount(async () => { calls++; }, "login");
  try {
    expect(p.host.querySelector('[data-testid="password-coach"]')).toBeNull();
    await fill(p.email(), "person@example.com"); await fill(p.password(), "old"); await p.submit(); expect(calls).toBe(1);
  } finally { await p.close(); }
});
test("duplicate submits share one request; pending fields remain readable; errors translate and clear on credential edit", async () => {
  let reject!: (e: Error) => void; let calls = 0;
  const p = await mount(() => { calls++; return new Promise((_, fail) => { reject = fail; }); }, "login");
  try {
    await fill(p.email(), "person@example.com"); await fill(p.password(), "unchanged");
    await act(async () => { const form = p.host.querySelector("form")!;
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    expect(calls).toBe(1); expect(p.email().readOnly).toBe(true); expect(p.host.querySelector("form")?.getAttribute("aria-busy")).toBe("true");
    await act(async () => { reject(Object.assign(new Error("raw"), { code: "unauthorized" })); });
    expect(p.email().readOnly).toBe(false); expect(p.password().value).toBe("unchanged");
    const before = p.host.querySelector('[role="alert"]')?.textContent;
    await act(async () => { await p.i18n.changeLanguage("es-419"); });
    expect(p.host.querySelector('[role="alert"]')?.textContent).not.toBe(before);
    await fill(p.email(), "corrected@example.com"); expect(p.host.querySelector('[role="alert"]')).toBeNull();
  } finally { await p.close(); }
});
test("an old response cannot show confirmation after the mode changes", async () => {
  let resolve!: (r: AuthFormSubmissionResult) => void;
  const p = await mount(() => new Promise((done) => { resolve = done; }));
  try {
    await fill(p.email(), "person@example.com"); await fill(p.password(), "long-enough"); await p.submit();
    await p.render("login"); await act(async () => resolve({ status: "email_confirmation_required" }));
    expect(p.host.querySelector('[data-testid="auth-check-email"]')).toBeNull();
    expect(p.host.querySelector("h2")?.textContent).toBe("Sign in");
  } finally { await p.close(); }
});

test("switching modes starts a new request and the old completion cannot unlock it", async () => {
  const resolutions: ((result?: AuthFormSubmissionResult) => void)[] = [];
  const p = await mount(() => new Promise((resolve) => { resolutions.push(resolve); }));
  try {
    await fill(p.email(), "person@example.com"); await fill(p.password(), "long-enough"); await p.submit();
    await p.render("login");
    expect(p.email().readOnly).toBe(false);
    await p.submit(); expect(resolutions.length).toBe(2);
    await act(async () => resolutions[0]({ status: "email_confirmation_required" }));
    expect(p.email().readOnly).toBe(true);
    expect(p.host.querySelector('[data-testid="auth-check-email"]')).toBeNull();
    await p.submit(); expect(resolutions.length).toBe(2);
    await act(async () => resolutions[1]());
    expect(p.email().readOnly).toBe(false);
  } finally { await p.close(); }
});
test.each(["signup", "login"] as const)("%s changes password visibility only through the eye and keeps the input focused", async (mode) => {
  const p = await mount(async () => {}, mode);
  try {
    await fill(p.password(), "unchanged-password");
    await act(async () => { p.password().focus(); });
    expect(p.password().type).toBe("password");
    await act(async () => { p.email().focus(); p.password().focus(); });
    expect(p.password().type).toBe("password");
    p.password().setSelectionRange(2, 5);
    const eye = p.host.querySelector<HTMLButtonElement>('button[aria-label="Show password"]')!;
    await act(async () => { p.email().focus(); eye.click(); });
    expect(p.password().type).toBe("text");
    expect(document.activeElement === p.password()).toBe(true);
    expect(p.password().selectionStart).toBe(2);
    expect(p.password().selectionEnd).toBe(5);
    expect(eye.querySelector(".lucide-eye-closed")).not.toBeNull();
    expect(eye.getAttribute("aria-label")).toBe("Hide password");
    await act(async () => { p.password().blur(); p.password().focus(); });
    expect(p.password().type).toBe("text");
    await act(async () => { eye.focus(); eye.click(); });
    expect(document.activeElement === p.password()).toBe(true);
    expect(p.password().type).toBe("password");
    expect(p.password().value).toBe("unchanged-password");
    await act(async () => { p.password().blur(); p.password().focus(); });
    expect(p.password().type).toBe("password");
  } finally { await p.close(); }
});

test("clean labels keep required semantics and describe the optional name group once", async () => {
  const p = await mount();
  try {
    await act(async () => { await p.i18n.changeLanguage("es-419"); });
    expect(p.host.textContent).not.toContain("Campos requeridos");
    expect(p.host.querySelector('[role="group"]')?.textContent).toContain("Nombre y apellido son opcionales");
    expect(p.host.querySelector<HTMLInputElement>('input[autocomplete="given-name"]')?.labels?.[0]?.textContent).toBe("Nombre");
    expect(p.host.querySelector<HTMLInputElement>('input[autocomplete="family-name"]')?.labels?.[0]?.textContent).toBe("Apellido");
    expect(p.email().required).toBe(true); expect(p.password().required).toBe(true);
    expect(p.email().labels?.[0]?.textContent).toBe("Correo electrónico");
  } finally { await p.close(); }
});

test("signup reveals coaching on focus and keeps it open through edits and blur", async () => {
  const p = await mount();
  try {
    expect(p.host.querySelector('[data-testid="password-coach"]')).toBeNull();
    expect(p.host.querySelector('[data-auth-feedback]')).toBeNull();
    await act(async () => p.password().focus());
    expect(p.host.querySelector('[data-testid="password-coach"]')?.textContent).toContain("At least 8 characters");
    expect(p.password().getAttribute("aria-describedby")).toContain("-coach");
    expect(p.host.querySelector('[data-testid="password-strength-reading"]')?.getAttribute("aria-hidden")).toBe("true");
    await fill(p.password(), "a");
    expect(p.host.querySelector('[data-testid="password-strength-reading"]')?.getAttribute("aria-hidden")).toBeNull();
    await fill(p.password(), ""); await blur(p.password());
    expect(p.host.querySelector('[data-testid="password-coach"]')).not.toBeNull();
  } finally { await p.close(); }
});

test.each(["signup", "login"] as const)("%s focuses password when only that field is invalid", async (mode) => {
  let calls = 0;
  const p = await mount(async () => { calls++; }, mode);
  try {
    await fill(p.email(), "person@example.com");
    await p.submit();
    expect(document.activeElement).toBe(p.password());
    expect(p.password().getAttribute("aria-invalid")).toBe("true");
    const note = p.password().getAttribute("aria-describedby")!.split(" ").find((id) => id.endsWith("-note"))!;
    expect(document.getElementById(note)?.textContent).toBe("Enter your password.");
    expect(p.host.querySelector('[role="alert"]')).toBeNull();
    expect(calls).toBe(0);
    await act(async () => p.email().focus());
    await p.submit();
    expect(document.activeElement).toBe(p.password());
  } finally { await p.close(); }
});
