import { describe, test } from "bun:test";
import i18next from "i18next";
import { doesNotMatch, equal, match } from "node:assert/strict";
import { createElement, type ComponentProps, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import { readFileSync } from "node:fs";

import ForgotPasswordPage from "../app/auth/forgot-password/page";
import AuthForm from "../components/auth/AuthForm";
import RequestAccess from "../components/auth/RequestAccess";
import en from "../public/locales/en/common.json";

async function renderLocalized(element: ReactElement): Promise<string> {
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: "en",
    fallbackLng: false,
    interpolation: { escapeValue: false },
    resources: { en: { translation: en } },
  });

  return renderToStaticMarkup(
    createElement(I18nextProvider, { i18n }, element),
  );
}

function authForm(embedded: boolean): ReactElement {
  const props = {
    mode: "login" as const,
    embedded,
    onModeChange: () => undefined,
    onSubmit: async () => undefined,
  } as ComponentProps<typeof AuthForm> & { embedded: boolean };
  return createElement(AuthForm, props);
}

function requestAccess(embedded: boolean): ReactElement {
  return createElement(RequestAccess, {
    embedded,
    onShowSignup: () => undefined,
    onShowLogin: () => undefined,
  });
}

function occurrences(value: string, fragment: string): number {
  return value.split(fragment).length - 1;
}

describe("auth card consistency", () => {
  test("standalone auth owns one canonical card while embedded auth adds none", async () => {
    const standalone = await renderLocalized(authForm(false));
    const embedded = await renderLocalized(authForm(true));
    const canonicalCard = "rounded-[20px] border border-black/10 bg-white p-7";

    equal(occurrences(standalone, canonicalCard), 1);
    doesNotMatch(standalone, /shadow/);
    equal(occurrences(embedded, canonicalCard), 0);
  });

  test("standalone request access owns one canonical card while embedded access adds none", async () => {
    const standalone = await renderLocalized(requestAccess(false));
    const embedded = await renderLocalized(requestAccess(true));
    const canonicalCard = "rounded-[20px] border border-black/10 bg-white p-7";

    equal(occurrences(standalone, canonicalCard), 1);
    doesNotMatch(standalone, /shadow/);
    equal(occurrences(embedded, canonicalCard), 0);
  });

  test("forgot password uses the canonical 20px card radius", async () => {
    const html = await renderLocalized(createElement(ForgotPasswordPage));
    const shell = readFileSync(new URL("../components/auth/RecoveryShell.tsx", import.meta.url), "utf8");
    const styles = readFileSync(new URL("../components/auth/recovery.module.css", import.meta.url), "utf8");

    equal(occurrences(html, "<section"), 1, "one recovery card");
    match(shell, /<section className=\{styles\.card\}/);
    match(styles, /\.card\s*\{[^}]*border:\s*1px solid var\(--auth-line\);[^}]*border-radius:\s*20px;/);
    doesNotMatch(styles, /\.card\s*\{[^}]*box-shadow:/);
  });
});
