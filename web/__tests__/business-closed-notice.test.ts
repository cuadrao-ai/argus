import { test } from "bun:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import { BusinessClosedNotice } from "@/components/status/BusinessClosedNotice";

for (const [language, translation] of [["es-419", spanish], ["en", english]] as const) {
  test(`the closed notice in ${language} links hola@cuadrao.ai`, async () => {
    const i18n = i18next.createInstance();
    await i18n.init({ lng: language, resources: { [language]: { translation } } });
    const html = renderToStaticMarkup(createElement(I18nextProvider, { i18n }, createElement(BusinessClosedNotice)));
    assert.match(html, /<a [^>]*href="mailto:hola@cuadrao\.ai"[^>]*>hola@cuadrao\.ai<\/a>/);
    assert.equal(html.includes("admin@cuadrao.ai"), false);
  });
}
