import assert from "node:assert/strict";
import { test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import DgiiRegistryTag from "@/components/business-app/DgiiRegistryTag";
import DgiiRegistryStatus, { type RegistryStatusState } from "@/components/business-app/DgiiRegistryStatus";
import { translate } from "./support/i18n-instance";

for (const language of ["es-419", "en"] as const) {
  test(`registry display keeps the canonical tag for every settled state in ${language}`, async () => {
    const i18n = await translate(language);
    const states: RegistryStatusState[] = [
      { status: "verified", name: "Suplidor registrado" },
      { status: "inactive", name: "Suplidor registrado", registryStatus: "SUSPENDIDO" },
      { status: "pending", name: "Suplidor registrado" },
      { status: "unverified", name: null },
    ];
    for (const state of states) {
      if (state.status === "checking" || state.status === "failed") continue;
      const tag = renderToStaticMarkup(<I18nextProvider i18n={i18n}><DgiiRegistryTag status={state.status} /></I18nextProvider>);
      const display = renderToStaticMarkup(<I18nextProvider i18n={i18n}><DgiiRegistryStatus state={state} testId="registry" onRetry={() => {}} /></I18nextProvider>);
      assert.ok(display.includes(tag), `the registry uses the same ${state.status} tag`);
      assert.ok(tag.includes(i18n.t(`business.dgii.legal_name.tag_${state.status}`)));
      assert.match(tag, /inline-flex items-center.*rounded-full px-2 py-0.5 text-\[12px\] font-medium/);
      assert.equal(tag.includes("lucide-check"), state.status === "verified");
      assert.equal(tag.includes("rounded-full bg-current"), state.status === "inactive");
      assert.equal(tag.includes("bg-[#E3EFE8]"), state.status === "verified");
      assert.equal(tag.includes("bg-[#F6EBD4]"), state.status === "inactive");
      assert.equal(tag.includes("bg-[#EDECE6]"), state.status === "pending" || state.status === "unverified");
      assert.ok(tag.includes("dark:"));
      if (state.status === "inactive") assert.ok(display.includes("SUSPENDIDO"), "the registry keeps its source detail");
    }
  });
}
