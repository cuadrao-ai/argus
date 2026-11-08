import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createElement } from "react";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";

import AuthForm from "@/components/auth/AuthForm";
import en from "@/public/locales/en/common.json";
import es419 from "@/public/locales/es-419/common.json";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/?auth=login" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function renderLoginForm(
  locale: "en" | "es-419",
  errorCode: "unauthorized" | "captcha_unavailable" = "unauthorized",
) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const resources =
    locale === "en"
      ? { en: { translation: en } }
      : { "es-419": { translation: es419 } };
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: locale,
    resources,
    interpolation: { escapeValue: false },
  });
  const submissions: string[] = [];
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      createElement(
        I18nextProvider,
        { i18n },
        createElement(AuthForm, {
          mode: "login",
          onSubmit: async () => {
            submissions.push("submit");
            throw Object.assign(new Error("raw"), { code: errorCode });
          },
        }),
      ),
    );
  });

  return { act, host, root, submissions };
}

async function submitCredentials(
  act: (callback: () => void | Promise<void>) => Promise<void>,
  host: HTMLElement,
) {
  const email = host.querySelector('input[type="email"]') as HTMLInputElement;
  const password = host.querySelector('input[type="password"]') as HTMLInputElement;
  const setControl = (input: HTMLInputElement, value: string) => {
    const setter = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )?.set;
    setter?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  };
  await act(async () => {
    setControl(email, "mama@example.com");
    setControl(password, "password123");
  });
  const form = host.querySelector("form")!;
  await act(async () => {
    form.requestSubmit();
    await Promise.resolve();
  });
  return form;
}

describe("password sign-in uniform server failure", () => {
  test("unauthorized server failure keeps approved English copy and the ordinary submit button", async () => {
    const { act, host, root, submissions } = await renderLoginForm("en");
    const form = await submitCredentials(act, host);

    assert.equal(
      host.querySelector("[role=alert]")?.textContent,
      "We couldn’t verify those account details. Check them and try again.",
    );
    const retry = host.querySelector("button[type=submit]") as HTMLButtonElement;
    assert.equal(retry.textContent, "Continue");
    assert.equal(retry.disabled, false);
    await act(async () => {
      form.requestSubmit(retry);
      await Promise.resolve();
    });
    assert.deepEqual(submissions, ["submit", "submit"]);
    await act(async () => root.unmount());
  });

  test("unauthorized server failure keeps approved Spanish copy and the ordinary submit button", async () => {
    const { act, host, root, submissions } = await renderLoginForm("es-419");
    const form = await submitCredentials(act, host);

    assert.equal(
      host.querySelector("[role=alert]")?.textContent,
      "No pudimos verificar los datos de la cuenta. Revísalos e inténtalo de nuevo.",
    );
    const retry = host.querySelector("button[type=submit]") as HTMLButtonElement;
    assert.equal(retry.textContent, "Continuar");
    assert.equal(retry.disabled, false);
    await act(async () => {
      form.requestSubmit(retry);
      await Promise.resolve();
    });
    assert.deepEqual(submissions, ["submit", "submit"]);
    await act(async () => root.unmount());
  });
});

describe("password sign-in local browser-check failure", () => {
  test("client acquisition failure keeps the retry label in English", async () => {
    const { act, host, root, submissions } = await renderLoginForm(
      "en",
      "captcha_unavailable",
    );
    const form = await submitCredentials(act, host);

    assert.equal(
      host.querySelector("[role=alert]")?.textContent,
      "We couldn’t verify your browser. Try again.",
    );
    const retry = host.querySelector("button[type=submit]") as HTMLButtonElement;
    assert.equal(retry.textContent, "Try again");
    await act(async () => {
      form.requestSubmit(retry);
      await Promise.resolve();
    });
    assert.deepEqual(submissions, ["submit", "submit"]);
    await act(async () => root.unmount());
  });

  test("client acquisition failure keeps the retry label in Spanish", async () => {
    const { act, host, root, submissions } = await renderLoginForm(
      "es-419",
      "captcha_unavailable",
    );
    const form = await submitCredentials(act, host);

    assert.equal(
      host.querySelector("[role=alert]")?.textContent,
      "No pudimos verificar tu navegador. Intenta de nuevo.",
    );
    const retry = host.querySelector("button[type=submit]") as HTMLButtonElement;
    assert.equal(retry.textContent, "Intentar de nuevo");
    await act(async () => {
      form.requestSubmit(retry);
      await Promise.resolve();
    });
    assert.deepEqual(submissions, ["submit", "submit"]);
    await act(async () => root.unmount());
  });
});
