import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import i18next from "i18next";
import { act, createElement, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { I18nextProvider } from "react-i18next";

import AuthForm from "../components/auth/AuthForm";
import { takeRecoveryEmail } from "../components/auth/recovery-email";
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
  onEmailConfirmed?: (input: { signal: AbortSignal }) => void | Promise<void>;
  onResendEmailCode?: (input: { email: string }) => Promise<void>;
  onModeChange?: (mode: "signup" | "login") => void;
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
  const renderMode = async (mode: "signup" | "login") => act(async () => {
    root.render(
      createElement(
        I18nextProvider,
        { i18n },
        createElement(AuthForm, {
          mode,
          onSubmit: async () => ({ status: "email_confirmation_required" as const }),
          ...props,
        }) as ReactNode,
      ),
    );
  });
  await renderMode("signup");

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
  return { host, root, renderMode };
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
    expect(state?.textContent).toContain(es419.auth.signup.confirmation_help);
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


describe("confirmation integration safety", () => {
  test.each(["123456789", "1234x5678", "1234-5678"])("malformed %s never becomes a valid token", async (value) => {
    let requests = 0;
    const page = await renderSpanishSignup({ onConfirmEmailCode: async () => { requests++; } });
    const code = page.host.querySelector("[data-testid='auth-confirmation-code']") as HTMLInputElement;
    await setNativeValue(code, value);
    await act(async () => { code.closest("form")?.requestSubmit(); });
    expect(requests).toBe(0);
    expect(code.getAttribute("aria-invalid")).toBe("true");
    await act(async () => { page.root.unmount(); });
  });

  test.each(["otp_transient", "too_many_requests"])("%s keeps the code for retry", async (kind) => {
    let requests = 0;
    const page = await renderSpanishSignup({ onConfirmEmailCode: async () => {
      requests++;
      if (requests === 1) throw Object.assign(new Error("private"), { code: kind });
    } });
    const code = page.host.querySelector("[data-testid='auth-confirmation-code']") as HTMLInputElement;
    await setNativeValue(code, "01234567");
    await act(async () => { code.closest("form")?.requestSubmit(); });
    expect(code.value).toBe("01234567");
    expect(page.host.textContent).not.toContain("private");
    await act(async () => { code.closest("form")?.requestSubmit(); });
    expect(requests).toBe(2);
    await act(async () => { page.root.unmount(); });
  });

  test("continuation retry never resubmits a consumed code", async () => {
    let verified = 0;
    let continued = 0;
    let release: () => void = () => {};
    const pending = new Promise<void>((resolve) => { release = resolve; });
    const page = await renderSpanishSignup({
      onConfirmEmailCode: async () => { verified++; },
      onEmailConfirmed: async () => {
        continued++;
        if (continued === 1) throw new Error("offline");
        await pending;
      },
    });
    const code = page.host.querySelector("[data-testid='auth-confirmation-code']") as HTMLInputElement;
    await setNativeValue(code, "01234567");
    await act(async () => { code.closest("form")?.requestSubmit(); });
    expect(code.readOnly).toBe(true);
    await act(async () => {
      code.closest("form")?.requestSubmit();
      code.closest("form")?.requestSubmit();
    });
    expect(verified).toBe(1);
    expect(continued).toBe(2);
    await act(async () => { release(); });
    await act(async () => { page.root.unmount(); });
  });
});


test("a stale verification cannot continue after an auth mode switch", async () => {
  let finish: () => void = () => {};
  let continued = 0;
  const pending = new Promise<void>((resolve) => { finish = resolve; });
  const page = await renderSpanishSignup({ onConfirmEmailCode: () => pending, onEmailConfirmed: () => { continued++; } });
  const code = page.host.querySelector("[data-testid='auth-confirmation-code']") as HTMLInputElement;
  await setNativeValue(code, "01234567");
  await act(async () => { code.closest("form")?.requestSubmit(); });
  await page.renderMode("login");
  await act(async () => { finish(); });
  expect(continued).toBe(0);
  expect(page.host.querySelector("[data-testid='auth-check-email']")).toBeNull();
  await act(async () => { page.root.unmount(); });
});

test("resend waits for acceptance, preserves the code and blocks concurrent verification", async () => {
  const originalInterval = window.setInterval;
  const originalNow = Date.now;
  let tick: () => void = () => {};
  window.setInterval = ((handler: () => void) => { tick = handler; return 0; }) as typeof window.setInterval;
  let release: () => void = () => {};
  let sent = 0;
  let verified = 0;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  const page = await renderSpanishSignup({ onResendEmailCode: async () => { sent++; await pending; }, onConfirmEmailCode: async () => { verified++; } });
  try {
    const code = page.host.querySelector("[data-testid='auth-confirmation-code']") as HTMLInputElement;
    await setNativeValue(code, "01234567");
    Date.now = () => originalNow() + 31_000;
    await act(async () => { tick(); });
    const resend = [...page.host.querySelectorAll("button")].find(button => button.textContent === "Reenviar código") as HTMLButtonElement;
    await act(async () => { resend.click(); resend.click(); code.closest("form")?.requestSubmit(); });
    expect(sent).toBe(1);
    expect(verified).toBe(0);
    expect(resend.disabled).toBe(true);
    expect(page.host.textContent).not.toContain("Solicitud recibida.");
    await act(async () => { release(); });
    expect(page.host.textContent).toContain("Solicitud recibida.");
    expect(code.value).toBe("01234567");
  } finally {
    Date.now = originalNow;
    window.setInterval = originalInterval;
    await act(async () => { page.root.unmount(); });
  }
});

test("browser-check refusal uses short resend feedback without clearing the code", async () => {
  const originalInterval = window.setInterval;
  const originalNow = Date.now;
  let tick: () => void = () => {};
  window.setInterval = ((handler: () => void) => { tick = handler; return 0; }) as typeof window.setInterval;
  const page = await renderSpanishSignup({
    onResendEmailCode: async () => { throw Object.assign(new Error("private"), { code: "captcha_unavailable" }); },
  });
  try {
    const code = page.host.querySelector("[data-testid='auth-confirmation-code']") as HTMLInputElement;
    await setNativeValue(code, "01234567");
    Date.now = () => originalNow() + 31_000;
    await act(async () => { tick(); });
    const resend = [...page.host.querySelectorAll("button")].find(button => button.textContent === "Reenviar código") as HTMLButtonElement;
    await act(async () => { resend.click(); });
    expect(page.host.querySelector("#auth-confirmation-code-note")?.textContent).toBe("No se pudo reenviar. Intenta de nuevo.");
    expect(code.value).toBe("01234567");
    expect(page.host.textContent).not.toContain("private");
  } finally {
    Date.now = originalNow;
    window.setInterval = originalInterval;
    await act(async () => { page.root.unmount(); });
  }
});

test("the check-email step offers sign-in and password recovery", async () => {
  const modes: Array<"signup" | "login"> = [];
  const page = await renderSpanishSignup({ onModeChange: (mode) => modes.push(mode) });
  const exits = page.host.querySelector("[data-testid='auth-check-email-exits']");
  expect(exits?.textContent).toContain("¿Ya tienes una cuenta? Iniciar sesión");
  const recovery = exits?.querySelector("a");
  expect(recovery?.getAttribute("href")).toBe("/auth/forgot-password");
  expect(recovery?.textContent).toBe("¿Olvidaste tu contraseña?");

  await act(async () => {
    (exits?.querySelector("button") as HTMLButtonElement).click();
  });
  expect(modes).toEqual(["login"]);
  await page.renderMode("login");
  expect(page.host.querySelector("[data-testid='auth-check-email']")).toBeNull();
  expect((page.host.querySelector('input[type="email"]') as HTMLInputElement).value).toBe("ada@example.com");
  await act(async () => {
    page.root.unmount();
  });
});

describe("an exit chosen while a code operation is pending wins over its late result", () => {
  type Settle = { resolve: () => void; reject: () => void };
  const operations: Record<string, (settle: Settle) => Parameters<typeof renderSpanishSignup>[0]> = {
    "a code check that succeeds late": (settle) => ({ onConfirmEmailCode: () => new Promise<void>((resolve) => { settle.resolve = resolve; }) }),
    "a code check that fails late": (settle) => ({ onConfirmEmailCode: () => new Promise<void>((_, reject) => {
      settle.resolve = () => reject(Object.assign(new Error("private"), { code: "otp_rejected" }));
    }) }),
    "a resend that is accepted late": (settle) => ({ onResendEmailCode: () => new Promise<void>((resolve) => { settle.resolve = resolve; }) }),
    "a resend that is refused late": (settle) => ({ onResendEmailCode: () => new Promise<void>((_, reject) => {
      settle.resolve = () => reject(Object.assign(new Error("private"), { code: "captcha_unavailable" }));
    }) }),
  };
  const lateResults = [
    es419.auth.signup.confirmation_resend_sent,
    es419.auth.signup.confirmation_resend_failed,
    es419.auth.signup.confirmation_code_rejected,
  ];
  function expectNoLateResult(host: HTMLElement) {
    const note = host.querySelector("#auth-confirmation-code-note")?.textContent ?? "";
    for (const text of lateResults) expect(note).not.toContain(text);
    expect(host.querySelector("[data-otp-status]")?.getAttribute("data-otp-status")).not.toBe("verified");
  }

  async function startPending(page: Awaited<ReturnType<typeof renderSpanishSignup>>, operation: string, armed: { tick: () => void; restore: () => void }) {
    const code = page.host.querySelector("[data-testid='auth-confirmation-code']") as HTMLInputElement;
    await setNativeValue(code, "01234567");
    if (operation.startsWith("a resend")) {
      await act(async () => { armed.tick(); });
      const resend = [...page.host.querySelectorAll("button")].find((button) => button.textContent === es419.auth.signup.confirmation_resend) as HTMLButtonElement;
      await act(async () => { resend.click(); });
    } else {
      await act(async () => { code.closest("form")?.requestSubmit(); });
    }
    return code;
  }

  function armResend() {
    const originalInterval = window.setInterval;
    const originalNow = Date.now;
    let tick: () => void = () => {};
    window.setInterval = ((handler: () => void) => { tick = handler; return 0; }) as typeof window.setInterval;
    return {
      tick: () => { Date.now = () => originalNow() + 31_000; tick(); },
      restore: () => { Date.now = originalNow; window.setInterval = originalInterval; },
    };
  }

  // A code check disables the exits (the design's "disable competing
  // actions"), so there the sign-in choice can only arrive from the parent as
  // a mode change. A resend leaves them live.
  const exitsLiveDuring = (operation: string) => operation.startsWith("a resend");

  for (const [operation, props] of Object.entries(operations)) {
    test(`${operation}: sign-in ${exitsLiveDuring(operation) ? "stays usable" : "waits and the parent's mode change wins"}, and the login view shows no trace of it`, async () => {
      const armed = armResend();
      const settle: Settle = { resolve: () => {}, reject: () => {} };
      const modes: Array<"signup" | "login"> = [];
      let finished = 0;
      const page = await renderSpanishSignup({ ...props(settle), onEmailConfirmed: () => { finished += 1; }, onModeChange: (mode) => modes.push(mode) });
      try {
        const code = await startPending(page, operation, armed);
        const signIn = page.host.querySelector("[data-testid='auth-check-email-exits'] button") as HTMLButtonElement;
        if (exitsLiveDuring(operation)) {
          expect(signIn.disabled).toBe(false);
          await act(async () => { signIn.click(); });
          expect(modes).toEqual(["login"]);
        } else {
          expect(signIn.disabled).toBe(true);
          await act(async () => { signIn.click(); });
          expect(modes).toEqual([]);
          await page.renderMode("login");
        }

        await act(async () => { settle.resolve(); });
        expect(finished).toBe(0);
        expectNoLateResult(page.host);
        expect(document.activeElement).not.toBe(code);

        await page.renderMode("login");
        expect(page.host.querySelector("[data-testid='auth-check-email']")).toBeNull();
        expect(page.host.querySelector("[role='alert']")).toBeNull();
        expect(page.host.querySelector("h2")?.textContent).toBe(es419.auth.login.title);
        expect((page.host.querySelector('input[type="email"]') as HTMLInputElement).value).toBe("ada@example.com");
        expect(finished).toBe(0);
      } finally {
        armed.restore();
        await act(async () => { page.root.unmount(); });
      }
    });

    if (!exitsLiveDuring(operation)) continue;
    test(`${operation}: password recovery stays usable and the late result is dropped`, async () => {
      const armed = armResend();
      const settle: Settle = { resolve: () => {}, reject: () => {} };
      let finished = 0;
      const page = await renderSpanishSignup({ ...props(settle), onEmailConfirmed: () => { finished += 1; } });
      const keepPage = (event: Event) => event.preventDefault();
      page.host.addEventListener("click", keepPage);
      try {
        const code = await startPending(page, operation, armed);
        const recovery = page.host.querySelector("[data-testid='auth-check-email-exits'] a") as HTMLAnchorElement;
        expect(recovery.getAttribute("aria-disabled")).toBeNull();
        // Other files replace HTMLAnchorElement.prototype.click for downloads, so dispatch the click itself.
        await act(async () => { recovery.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true })); });
        expect(takeRecoveryEmail()).toBe("ada@example.com");

        await act(async () => { settle.resolve(); });
        expect(finished).toBe(0);
        expectNoLateResult(page.host);
        expect(document.activeElement).not.toBe(code);
      } finally {
        page.host.removeEventListener("click", keepPage);
        armed.restore();
        await act(async () => { page.root.unmount(); });
      }
    });
  }

  test("sign-in chosen while the confirmed signup is still finishing aborts that continuation", async () => {
    let release: () => void = () => {};
    let seen: AbortSignal | undefined;
    const modes: Array<"signup" | "login"> = [];
    const page = await renderSpanishSignup({
      onConfirmEmailCode: async () => {},
      onEmailConfirmed: ({ signal }) => { seen = signal; return new Promise<void>((resolve) => { release = resolve; }); },
      onModeChange: (mode) => modes.push(mode),
    });
    try {
      const code = page.host.querySelector("[data-testid='auth-confirmation-code']") as HTMLInputElement;
      await setNativeValue(code, "01234567");
      await act(async () => { code.closest("form")?.requestSubmit(); });
      expect(seen?.aborted).toBe(false);
      const signIn = page.host.querySelector("[data-testid='auth-check-email-exits'] button") as HTMLButtonElement;
      expect(signIn.disabled).toBe(false);
      await act(async () => { signIn.click(); });
      expect(modes).toEqual(["login"]);
      expect(seen?.aborted).toBe(true);
      await act(async () => { release(); });
    } finally {
      await act(async () => { page.root.unmount(); });
    }
  });

  const confirming = es419.auth.signup.confirmation_loading;
  const exitsOf = (host: HTMLElement) => ({
    loading: host.querySelector("[data-testid='auth-check-email'] form button[type='submit']") as HTMLButtonElement,
    signIn: host.querySelector("[data-testid='auth-check-email-exits'] button") as HTMLButtonElement,
    recovery: host.querySelector("[data-testid='auth-check-email-exits'] a") as HTMLAnchorElement,
    resend: [...host.querySelectorAll("button")].find((button) => button.textContent === es419.auth.signup.confirmation_resend) as HTMLButtonElement,
  });
  // The anchor's own click() is replaced by other files, so the click is dispatched; the listener
  // records whether the component left it to the browser before it stops happy-dom from navigating.
  function watchClicks(host: HTMLElement) {
    const leftToBrowser: boolean[] = [];
    const listener = (event: Event) => { leftToBrowser.push(!event.defaultPrevented); event.preventDefault(); };
    host.addEventListener("click", listener);
    host.addEventListener("auxclick", listener);
    return { leftToBrowser, stop: () => { host.removeEventListener("click", listener); host.removeEventListener("auxclick", listener); } };
  }
  const dispatch = (target: Element, type: "click" | "auxclick", init: MouseEventInit = {}) =>
    act(async () => { target.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, button: 0, ...init })); });

  describe("while the code is checked, the competing actions wait and the loading button says why", () => {
    test("sign-in, recovery and resend are disabled and described by the loading button, a click runs nothing, and the late success finishes", async () => {
      const armed = armResend();
      const settle: Settle = { resolve: () => {}, reject: () => {} };
      const modes: Array<"signup" | "login"> = [];
      let finished = 0;
      let resent = 0;
      const page = await renderSpanishSignup({
        ...operations["a code check that succeeds late"](settle),
        onResendEmailCode: async () => { resent += 1; },
        onEmailConfirmed: () => { finished += 1; },
        onModeChange: (mode) => modes.push(mode),
      });
      let clicks = { leftToBrowser: [] as boolean[], stop: () => {} };
      try {
        await act(async () => { armed.tick(); });
        const code = await startPending(page, "a code check that succeeds late", armed);
        clicks = watchClicks(page.host);
        const { loading, signIn, recovery, resend } = exitsOf(page.host);
        expect(loading.textContent).toBe(confirming);
        expect(loading.id).not.toBe("");
        for (const action of [signIn, recovery, resend]) expect(action.getAttribute("aria-describedby")).toBe(loading.id);
        expect(signIn.disabled).toBe(true);
        expect(resend.disabled).toBe(true);
        expect(recovery.getAttribute("aria-disabled")).toBe("true");

        await act(async () => { signIn.click(); resend.click(); });
        await dispatch(recovery, "click");
        await dispatch(recovery, "click", { metaKey: true });
        await dispatch(recovery, "auxclick", { button: 1 });
        expect(modes).toEqual([]);
        expect(resent).toBe(0);
        expect(takeRecoveryEmail()).toBe("");
        expect(clicks.leftToBrowser).toEqual([false, false, false]);
        expect(page.host.querySelector("[data-otp-status]")?.getAttribute("data-otp-status")).toBe("verifying");
        expect(code.readOnly).toBe(true);

        await act(async () => { settle.resolve(); });
        expect(finished).toBe(1);
        expect(page.host.querySelector("[data-otp-status]")?.getAttribute("data-otp-status")).toBe("verified");
      } finally {
        clicks.stop();
        armed.restore();
        await act(async () => { page.root.unmount(); });
      }
    });

    test("after a rejected code the competing actions are usable again and the explanation is gone", async () => {
      const armed = armResend();
      const settle: Settle = { resolve: () => {}, reject: () => {} };
      const modes: Array<"signup" | "login"> = [];
      const page = await renderSpanishSignup({ ...operations["a code check that fails late"](settle), onModeChange: (mode) => modes.push(mode) });
      try {
        await startPending(page, "a code check that fails late", armed);
        const locked = exitsOf(page.host);
        expect(locked.signIn.disabled).toBe(true);
        expect(locked.recovery.getAttribute("aria-disabled")).toBe("true");

        await act(async () => { settle.resolve(); });
        const { loading, signIn, recovery } = exitsOf(page.host);
        expect(page.host.querySelector("#auth-confirmation-code-note")?.textContent).toContain(es419.auth.signup.confirmation_code_rejected);
        expect(loading.textContent).not.toBe(confirming);
        expect(signIn.disabled).toBe(false);
        expect(recovery.getAttribute("aria-disabled")).toBeNull();
        expect(signIn.getAttribute("aria-describedby")).toBeNull();
        expect(recovery.getAttribute("aria-describedby")).toBeNull();
        await act(async () => { signIn.click(); });
        expect(modes).toEqual(["login"]);
      } finally {
        armed.restore();
        await act(async () => { page.root.unmount(); });
      }
    });
  });

  describe("a modified or middle click on password recovery leaves this tab as it is", () => {
    const openElsewhere: Array<[string, "click" | "auxclick", MouseEventInit]> = [
      ["Cmd-click", "click", { metaKey: true }],
      ["Ctrl-click", "click", { ctrlKey: true }],
      ["Shift-click", "click", { shiftKey: true }],
      ["Alt-click", "click", { altKey: true }],
      ["middle click", "auxclick", { button: 1 }],
      ["middle click reported as a click", "click", { button: 1 }],
    ];

    test.each(openElsewhere)("%s during a pending code check: this tab keeps verifying and the late success finishes", async (_name, type, init) => {
      const settle: Settle = { resolve: () => {}, reject: () => {} };
      let finished = 0;
      const page = await renderSpanishSignup({ ...operations["a code check that succeeds late"](settle), onEmailConfirmed: () => { finished += 1; } });
      let clicks = { leftToBrowser: [] as boolean[], stop: () => {} };
      try {
        const code = await startPending(page, "a code check that succeeds late", armResend());
        clicks = watchClicks(page.host);
        await dispatch(exitsOf(page.host).recovery, type, init);
        expect(takeRecoveryEmail()).toBe("");
        expect(page.host.querySelector("[data-otp-status]")?.getAttribute("data-otp-status")).toBe("verifying");
        expect(exitsOf(page.host).loading.textContent).toBe(confirming);

        await act(async () => { settle.resolve(); });
        expect(finished).toBe(1);
        expect(page.host.querySelector("[data-otp-status]")?.getAttribute("data-otp-status")).toBe("verified");
        expect(code.readOnly).toBe(true);
      } finally {
        clicks.stop();
        await act(async () => { page.root.unmount(); });
      }
    });

    test.each(openElsewhere)("%s during a resend in flight: the browser gets the click, this tab remembers nothing, and the late result lands", async (_name, type, init) => {
      const armed = armResend();
      const settle: Settle = { resolve: () => {}, reject: () => {} };
      const page = await renderSpanishSignup(operations["a resend that is accepted late"](settle));
      let clicks = { leftToBrowser: [] as boolean[], stop: () => {} };
      try {
        const code = await startPending(page, "a resend that is accepted late", armed);
        clicks = watchClicks(page.host);
        await dispatch(exitsOf(page.host).recovery, type, init);
        expect(clicks.leftToBrowser).toEqual([true]);
        expect(takeRecoveryEmail()).toBe("");
        expect(page.host.querySelector("#auth-confirmation-code-note")?.textContent).toBe(es419.auth.signup.confirmation_resend_pending);

        await act(async () => { settle.resolve(); });
        expect(page.host.querySelector("#auth-confirmation-code-note")?.textContent).toBe(es419.auth.signup.confirmation_resend_sent);
        expect(code.value).toBe("01234567");
      } finally {
        clicks.stop();
        armed.restore();
        await act(async () => { page.root.unmount(); });
      }
    });

    test("a plain click on recovery during a resend in flight is the choice: the late result is dropped", async () => {
      const armed = armResend();
      const settle: Settle = { resolve: () => {}, reject: () => {} };
      const page = await renderSpanishSignup(operations["a resend that is accepted late"](settle));
      let clicks = { leftToBrowser: [] as boolean[], stop: () => {} };
      try {
        await startPending(page, "a resend that is accepted late", armed);
        clicks = watchClicks(page.host);
        await dispatch(exitsOf(page.host).recovery, "click");
        expect(takeRecoveryEmail()).toBe("ada@example.com");
        await act(async () => { settle.resolve(); });
        expectNoLateResult(page.host);
      } finally {
        clicks.stop();
        armed.restore();
        await act(async () => { page.root.unmount(); });
      }
    });

    test("a modified click on the sign-in button is still a choice made in this tab", async () => {
      const armed = armResend();
      const settle: Settle = { resolve: () => {}, reject: () => {} };
      const modes: Array<"signup" | "login"> = [];
      const page = await renderSpanishSignup({ ...operations["a resend that is accepted late"](settle), onModeChange: (mode) => modes.push(mode) });
      try {
        await startPending(page, "a resend that is accepted late", armed);
        await dispatch(exitsOf(page.host).signIn, "click", { metaKey: true });
        expect(modes).toEqual(["login"]);
        await act(async () => { settle.resolve(); });
        expectNoLateResult(page.host);
      } finally {
        armed.restore();
        await act(async () => { page.root.unmount(); });
      }
    });
  });
});
