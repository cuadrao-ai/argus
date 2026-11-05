import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/auth/confirm/error" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(() => {
  document.body.innerHTML = "";
  window.history.replaceState(null, "", "/auth/confirm/error");
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function renderAt(search: string) {
  window.history.replaceState(null, "", `/auth/confirm/error${search}`);
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { default: ConfirmErrorPage } = await import("@/app/auth/confirm/error/page");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", fallbackLng: false, resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.append(host);
  await act(async () => createRoot(host).render(<I18nextProvider i18n={i18n}><ConfirmErrorPage /></I18nextProvider>));
  return host;
}

describe("/auth/confirm/error", () => {
  test("shows the reference the confirm route logged", async () => {
    for (const ref of ["c0ffee11", "badcafe22"]) {
      const host = await renderAt(`?error_code=otp_expired&type=recovery&ref=${ref}`);
      assert.equal(host.querySelector('[data-testid="error-reference"]')?.getAttribute("title"), ref);
      assert.equal(host.querySelector("h1")?.textContent, "Este enlace ya venció o ya se usó.");
      document.body.innerHTML = "";
    }
  });

  test("makes up a reference only when the URL carries none that is usable", async () => {
    for (const search of ["?error_code=otp_expired&type=recovery", "?error_code=otp_expired&type=recovery&ref=%3Cscript%3E"]) {
      const host = await renderAt(search);
      const title = host.querySelector('[data-testid="error-reference"]')?.getAttribute("title");
      assert.ok(title && title.length >= 4 && !title.includes("<"));
      document.body.innerHTML = "";
    }
  });
});
