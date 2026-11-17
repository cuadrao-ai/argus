import { describe, expect, test } from "bun:test";
import { createInstance } from "i18next";
import { dgiiChoiceLabel } from "@/lib/dgii-labels";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

/** Each DGII list by the code the server stores, as the screens name it. */
const approved = {
  "es-419": {
    income_withholding_type: {
      "01": "01 - Alquileres",
      "02": "02 - Honorarios por servicios",
      "03": "03 - Otras rentas",
      "04": "04 - Otras rentas (rentas presuntas)",
      "05": "05 - Intereses a personas jurídicas residentes",
      "06": "06 - Intereses a personas físicas residentes",
      "07": "07 - Retención por proveedores del Estado",
      "08": "08 - Juegos telefónicos",
      "09": "09 - Retenciones subsector ganadería de carne bovina",
    },
    income_type: {
      "1": "01 - Ingresos por operaciones (no financieros)",
      "2": "02 - Ingresos financieros",
      "3": "03 - Ingresos extraordinarios",
      "4": "04 - Ingresos por arrendamientos",
      "5": "05 - Ingresos por venta de activo depreciable",
      "6": "06 - Otros ingresos",
    },
    id_type: { "1": "1 - RNC", "2": "2 - Cédula", "3": "3 - Pasaporte o ID tributaria" },
  },
  en: {
    income_withholding_type: {
      "01": "01 - Rent",
      "02": "02 - Professional services fees",
      "03": "03 - Other income",
      "04": "04 - Other income (presumed income)",
      "05": "05 - Interest paid to resident legal entities",
      "06": "06 - Interest paid to resident individuals",
      "07": "07 - Withholding by government suppliers",
      "08": "08 - Telephone games",
      "09": "09 - Beef cattle subsector withholdings",
    },
    income_type: {
      "1": "01 - Operating income (non-financial)",
      "2": "02 - Financial income",
      "3": "03 - Extraordinary income",
      "4": "04 - Lease income",
      "5": "05 - Income from sale of depreciable assets",
      "6": "06 - Other income",
    },
    id_type: { "1": "1 - RNC", "2": "2 - Cédula", "3": "3 - Passport or tax ID" },
  },
} as const;

for (const [language, catalog] of [["es-419", es], ["en", en]] as const) {
  const instance = createInstance().use(dgiiChoiceLabel);
  await instance.init({ defaultNS: "common", postProcess: dgiiChoiceLabel.name, postProcessPassResolved: true, parseMissingKeyHandler: () => "", lng: language, supportedLngs: ["es-419", "en"], fallbackLng: false, resources: { [language]: { common: catalog } } });
  describe(`606 screen labels in ${language}`, () => {
    for (const field of ["category", "payment_method"] as const) {
      test.each(Object.entries(catalog.business.dgii.option[field]))(`${field} %s includes the code and locale name`, (code, name) => {
        expect(instance.t(`business.dgii.option.${field}.${code}`)).toBe(`${code} - ${name}`);
      });
    }
    for (const field of ["income_withholding_type", "income_type", "id_type"] as const) {
      test.each(Object.entries(approved[language][field]))(`${field} %s reads as its approved DGII name`, (code, label) => {
        expect(instance.t(`business.dgii.option.${field}.${code}`)).toBe(label);
      });
      test(`${field} has a label for exactly the codes the server stores`, () => {
        expect(Object.keys(catalog.business.dgii.option[field]).sort()).toEqual(Object.keys(approved[language][field]).sort());
      });
    }
    test("unknown codes and other DGII lists keep their existing rendering", () => {
      expect(instance.t("business.dgii.option.category.99", { defaultValue: "99" }) || "99").toBe("99");
      expect(instance.t("business.dgii.option.income_type.7", { defaultValue: "7" }) || "7").toBe("7");
      expect(instance.t("business.dgii.option.id_type.1")).toBe(catalog.business.dgii.option.id_type["1"]);
    });
  });
}
