import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createElement, type ReactElement } from "react";

import { AuthLinkErrorScreen } from "@/components/status/AuthLinkErrorScreen";
import { BrandedStatusScreen } from "@/components/status/BrandedStatusScreen";
import { NotFoundScreen } from "@/components/status/NotFoundScreen";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/missing" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function render(element: ReactElement, language: "en" | "es-419" = "en") {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const english = (await import("@/public/locales/en/common.json")).default;
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: language,
    fallbackLng: false,
    interpolation: { escapeValue: false },
    resources: {
      en: { translation: english },
      "es-419": { translation: spanish },
    },
  });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(createElement(I18nextProvider, { i18n }, element));
  });
  return host;
}

describe("branded status layout", () => {
  test("shows the lockup, one heading, one line, and one keyboard button", async () => {
    const host = await render(
      createElement(BrandedStatusScreen, {
        title: "No encontramos esta página.",
        detail: "Puede que el enlace esté viejo o mal copiado.",
        actionLabel: "Ir a Cuadrao",
        actionHref: "/?auth=login",
      }),
    );
    const heading = host.querySelector("h1");
    const line = host.querySelector("p");
    const link = host.querySelector("a");
    const image = host.querySelector("img");
    assert.equal(host.querySelectorAll("h1, h2, h3, h4").length, 1);
    assert.equal(heading?.textContent, "No encontramos esta página.");
    assert.equal(line?.textContent, "Puede que el enlace esté viejo o mal copiado.");
    assert.equal(link?.textContent, "Ir a Cuadrao");
    assert.equal(link?.getAttribute("href"), "/?auth=login");
    assert.equal(image?.getAttribute("src"), "/brand/cuadrao-lockup-light.svg");
    assert.equal(image?.getAttribute("alt"), "");
    assert.match(heading?.className ?? "", /font-display/);
    assert.match(heading?.className ?? "", /font-medium/);
    assert.match(line?.className ?? "", /font-sans/);
    assert.match(host.querySelector("main")?.className ?? "", /bg-\[#F7F5EE\]/);
    assert.match(link?.className ?? "", /min-h-11/);
    assert.match(link?.className ?? "", /bg-\[#2f5a49\]/);
    assert.match(link?.className ?? "", /focus-visible:ring-2/);
    assert.equal(host.textContent?.includes("\u2014"), false);
  });
});

describe("missing page", () => {
  test("the button goes home when signed in and to login when signed out", async () => {
    const signedIn = await render(
      createElement(NotFoundScreen, { homeHref: "/chat" }),
      "es-419",
    );
    const signedOut = await render(
      createElement(NotFoundScreen, { homeHref: "/?auth=login" }),
      "es-419",
    );
    assert.equal(signedIn.querySelector("a")?.getAttribute("href"), "/chat");
    assert.equal(signedOut.querySelector("a")?.getAttribute("href"), "/?auth=login");
    assert.equal(signedIn.querySelector("a")?.textContent, "Ir a Cuadrao");
  });
});

describe("spanish status copy", () => {
  test("renders the Iris lines and no em dash", async () => {
    const missing = await render(createElement(NotFoundScreen, { homeHref: "/?auth=login" }), "es-419");
    const expired = await render(
      createElement(AuthLinkErrorScreen, {
        homeHref: "/?auth=login",
        reference: "c0ffee0011",
        view: {
          problem: "expired",
          kind: "request",
          flow: "recovery",
          email: "ada@example.test",
          href: "/auth/forgot-password?email=ada%40example.test",
        },
      }),
      "es-419",
    );
    const invite = await render(
      createElement(AuthLinkErrorScreen, {
        homeHref: "/chat",
        reference: "c0ffee0022",
        view: { problem: "expired", kind: "invite" },
      }),
      "es-419",
    );
    const malformed = await render(
      createElement(AuthLinkErrorScreen, {
        reference: "c0ffee0033",
        view: { problem: "malformed", kind: "request", flow: "recovery", email: null, href: "/auth/forgot-password" },
      }),
      "es-419",
    );
    const rejected = await render(
      createElement(AuthLinkErrorScreen, {
        homeHref: "/chat",
        reference: "c0ffee0044",
        view: { problem: "rejected", kind: "invite" },
      }),
      "es-419",
    );

    assert.equal(missing.querySelector("h1")?.textContent, "No encontramos esta página.");
    assert.equal(missing.querySelector("p")?.textContent, "Puede que el enlace esté viejo o mal copiado.");
    assert.equal(expired.querySelector("h1")?.textContent, "Este enlace ya venció o ya se usó.");
    assert.equal(expired.querySelector("a")?.textContent, "Pedir un enlace nuevo");
    assert.equal(expired.querySelector("a")?.getAttribute("href"), "/auth/forgot-password?email=ada%40example.test");
    assert.equal(invite.querySelector("p")?.textContent, "Pide a quien te invitó que te envíe otra invitación.");
    assert.equal(invite.querySelector("a")?.textContent, "Ir a Cuadrao");
    assert.equal(invite.querySelector("a")?.getAttribute("href"), "/chat");
    assert.equal(expired.querySelector('[data-testid="error-reference"]')?.getAttribute("title"), "c0ffee0011");
    assert.equal(expired.querySelector("[data-reference-short]")?.textContent, "Ref. c0ffee00");
    assert.equal(malformed.querySelector("h1")?.textContent, "Este enlace no funcionó");
    assert.equal(malformed.querySelector("p")?.textContent, "Al enlace le falta una parte o se copió mal. Ábrelo desde el correo o pide uno nuevo.");
    assert.equal(malformed.querySelector("a")?.textContent, "Pedir un enlace nuevo");
    assert.equal(malformed.querySelector('[data-testid="error-reference"]')?.getAttribute("title"), "c0ffee0033");
    assert.equal(rejected.querySelector("h1")?.textContent, "Este enlace no funcionó");
    assert.equal(rejected.querySelector("p")?.textContent, "No pudimos verificar este enlace. Pide uno nuevo e inténtalo otra vez.");
    assert.equal(rejected.querySelector("a")?.textContent, "Ir a Cuadrao");
    for (const host of [missing, expired, invite, malformed, rejected]) {
      assert.equal(host.textContent?.includes("\u2014"), false);
      assert.equal(host.textContent?.includes("This page could not be found"), false);
    }
  });
});
