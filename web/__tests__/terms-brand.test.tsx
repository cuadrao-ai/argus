import { describe, expect, test } from "bun:test";
import i18next from "i18next";
import { createElement, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";

import AlphaLegalPage from "../components/legal/AlphaLegalPage";
import en from "../public/locales/en/common.json";
import es419 from "../public/locales/es-419/common.json";

const CATALOGS = { en, "es-419": es419 } as const;
type Locale = keyof typeof CATALOGS;

async function renderTerms(locale: Locale): Promise<string> {
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: locale,
    fallbackLng: false,
    interpolation: { escapeValue: false },
    resources: { [locale]: { translation: CATALOGS[locale] } },
  });

  const element: ReactElement = createElement(AlphaLegalPage, {
    kind: "terms",
    supportEmail: "support@get-argus.com",
  });

  return renderToStaticMarkup(createElement(I18nextProvider, { i18n }, element));
}

describe("terms page product name", () => {
  test("shows Cuadrao in the English and Spanish terms a reader sees", async () => {
    const english = await renderTerms("en");
    const spanish = await renderTerms("es-419");

    expect(english).toContain(
      "Cuadrao is an early access product for educational investing research.",
    );
    expect(english).toContain("not as a Cuadrao market data source.");
    expect(english).toContain(
      "Cuadrao is not a broker, dealer, investment adviser, fiduciary, exchange, custodian, or trading venue.",
    );

    expect(spanish).toContain(
      "Cuadrao es un producto en acceso anticipado para investigación educativa de inversión.",
    );
    expect(spanish).toContain("Cuadrao no es broker");
    expect(spanish).toContain("no como fuente de datos de mercado de Cuadrao.");

    for (const markup of [english, spanish]) {
      const withoutSupport = markup.replaceAll("support@get-argus.com", "");
      expect(withoutSupport.toLowerCase()).not.toContain("argus");
    }
  });
});
