import { describe, expect, test } from "bun:test";
import i18next from "i18next";
import { businessDateMessage } from "@/lib/business-date-errors";
import en from "@/public/locales/en/common.json";
import es from "@/public/locales/es-419/common.json";

for (const language of ["en", "es-419"] as const) {
  describe(language, () => {
    const translate = async () => {
      const i18n = i18next.createInstance();
      await i18n.init({ lng: language, resources: { en: { translation: en }, "es-419": { translation: es } }, interpolation: { escapeValue: false } });
      return i18n.t.bind(i18n);
    };
    for (const [code,english,spanish] of [
      ["business_date_before_minimum", "Date must be on or after 2016-11-15.", "Date debe ser del 2016-11-15 en adelante."],
      ["business_date_after_today", "Date can't be later than today.", "Date no puede ser posterior a hoy."],
    ]) {
      test(`${code}: API refusal, bank context and reader reason share the sentence`, async () => {
        const t = await translate();
        const expected = language === "en" ? english : spanish;
        const context = { min_date: "2016-11-15" };
        expect(businessDateMessage({ code: "validation_error", context: { errors: [{ type: code, loc: ["body", "facts", "occurred_on", "known", "value"], ctx: context }] } }, t, "Date")).toBe(expected);
        expect(businessDateMessage({ code, context }, t, "Date")).toBe(expected);
        expect(businessDateMessage({ code, ...context }, t, "Date")).toBe(expected);
        expect(businessDateMessage({ cause: { code, context } }, t, "Date")).toBe(expected);
      });
    }
    test("a missing server minimum never invents a local floor", async () => {
      expect(businessDateMessage({ code: "business_date_before_minimum" }, await translate(), "Date")).toBeNull();
    });
  });
}
