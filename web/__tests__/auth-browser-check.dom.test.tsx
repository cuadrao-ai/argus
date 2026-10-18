import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createElement } from "react";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";

import AuthForm from "@/components/auth/AuthForm";
import es419 from "@/public/locales/es-419/common.json";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/?auth=login" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

describe("password sign-in browser check", () => {
  test("a failed browser check shows the Spanish error and a retry that submits again", async () => {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18n = i18next.createInstance();
    await i18n.init({
      lng: "es-419",
      resources: { "es-419": { translation: es419 } },
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
              throw Object.assign(new Error("raw"), { code: "captcha_unavailable" });
            },
          }),
        ),
      );
    });

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

    assert.equal(
      host.querySelector("[role=alert]")?.textContent,
      "No pudimos verificar tu navegador. Intenta de nuevo.",
    );
    const retry = host.querySelector("button[type=submit]") as HTMLButtonElement;
    assert.equal(retry.textContent, "Intentar de nuevo");
    assert.equal(retry.disabled, false);
    await act(async () => {
      form.requestSubmit(retry);
      await Promise.resolve();
    });
    assert.deepEqual(submissions, ["submit", "submit"]);
    await act(async () => root.unmount());
  });
});
