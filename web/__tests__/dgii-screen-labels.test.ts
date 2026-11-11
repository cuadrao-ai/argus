import { describe, expect, test } from "bun:test";
import { createInstance } from "i18next";
import { dgiiChoiceLabel } from "@/lib/dgii-labels";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

for (const [language, catalog] of [["es-419", es], ["en", en]] as const) {
  const instance = createInstance().use(dgiiChoiceLabel);
  await instance.init({ defaultNS: "common", postProcess: dgiiChoiceLabel.name, postProcessPassResolved: true, parseMissingKeyHandler: () => "", lng: language, supportedLngs: ["es-419", "en"], fallbackLng: false, resources: { [language]: { common: catalog } } });
  describe(`606 screen labels in ${language}`, () => {
    for (const field of ["category", "payment_method"] as const) {
      test.each(Object.entries(catalog.business.dgii.option[field]))(`${field} %s includes the code and locale name`, (code, name) => {
        expect(instance.t(`business.dgii.option.${field}.${code}`)).toBe(`${code} - ${name}`);
      });
    }
    test("unknown codes and other DGII lists keep their existing rendering", () => {
      expect(instance.t("business.dgii.option.category.99", { defaultValue: "99" }) || "99").toBe("99");
      expect(instance.t("business.dgii.option.id_type.1")).toBe(catalog.business.dgii.option.id_type["1"]);
    });
  });
}
