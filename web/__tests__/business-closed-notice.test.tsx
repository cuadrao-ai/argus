import { describe, expect, test } from "bun:test";
import { createInstance } from "i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import { Window } from "happy-dom";

import { primaryButtonClass } from "@/components/business-app/business-ui";
import { BusinessClosedNotice } from "@/components/status/BusinessClosedNotice";
import BusinessPanel from "@/components/business-app/BusinessPanel";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { classifyFailure } from "@/lib/failure-screen";
import { supportEmail } from "@/lib/support-email";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

describe("Business access-unavailable notice", () => {
  test("an API 403 still renders the account refusal notice in the workspace", async () => {
    const i18n = createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
    const context = {
      panel: { kind: "overview" },
      records: { closed: classifyFailure({ status: 403 }) === "closed" },
    } as unknown as BusinessContextValue;
    const html = renderToStaticMarkup(
      <I18nextProvider i18n={i18n}>
        <BusinessContext.Provider value={context}><BusinessPanel /></BusinessContext.Provider>
      </I18nextProvider>,
    );
    expect(html).toContain('data-testid="business-home-closed"');
    expect(html).toContain(i18n.t("auth.business_unavailable.title"));
    expect(html).toContain(i18n.t("auth.business_unavailable.sign_out"));
  });

  test.each(["es-419", "en"])("%s keeps the selected locale and shared action", async (language) => {
    const i18n = createInstance();
    await i18n.init({
      lng: language,
      resources: { en: { translation: english }, "es-419": { translation: spanish } },
      interpolation: { escapeValue: false },
    });
    const window = new Window();
    try {
      window.document.body.innerHTML = renderToStaticMarkup(
        <I18nextProvider i18n={i18n}><BusinessClosedNotice /></I18nextProvider>,
      );
      const notice = window.document.querySelector('[data-testid="business-home-closed"]')!;
      expect(notice.querySelector("h2")?.textContent).toBe(i18n.t("auth.business_unavailable.title"));
      expect(notice.querySelector("p")?.textContent).toBe(i18n.t("auth.business_unavailable.body", { supportEmail }));
      expect(notice.querySelector("a")?.getAttribute("href")).toBe(`mailto:${supportEmail}`);
      const action = notice.querySelector("button")!;
      expect(action.textContent).toBe(i18n.t("auth.business_unavailable.sign_out"));
      // Only layout utilities may accompany the shared button owner.
      const classes = action.className.split(/\s+/);
      const shared = primaryButtonClass.split(/\s+/);
      expect(classes.filter((name) => shared.includes(name)).sort()).toEqual([...shared].sort());
      expect(classes.filter((name) => !shared.includes(name)).every((name) => /^(?:w-full|mt-\[\d+px\])$/.test(name))).toBe(true);
    } finally {
      await window.happyDOM.close();
    }
  });
});
