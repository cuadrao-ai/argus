import { readFileSync } from "node:fs";
import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import postcss from "postcss";

const sheets = [
  "../components/auth/account-security.module.css",
  "../app/globals.css",
];

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/account/security" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(() => GlobalRegistrator.unregister());

async function mount() {
  const { createRoot } = await import("react-dom/client");
  const { AccountSecurity } = await import("@/components/auth/AccountSecurity");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(
    <I18nextProvider i18n={i18n}>
      <AccountSecurity loadSession={async () => ({})} />
    </I18nextProvider>,
  ));
  return {
    button: (scope: string) => host.querySelector<HTMLButtonElement>(`[data-scope="${scope}"] button`)!,
    close: async () => { await act(async () => root.unmount()); host.remove(); },
  };
}

function sageRulesFor(button: HTMLButtonElement, source: string, states: string[]) {
  // The DOM runner does not model pointer state. Substitute only the dynamic
  // pseudo-classes; match the real ancestry, attributes and :disabled normally.
  for (const state of ["hover", "focus-visible", "active"]) {
    button.toggleAttribute(`data-test-${state}`, states.includes(state));
  }
  const matches: string[] = [];
  postcss.parse(readFileSync(new URL(source, import.meta.url), "utf8")).walkRules((rule) => {
    const paintsSage = rule.nodes.some((node) => node.type === "decl"
      && ["background", "background-color"].includes(node.prop)
      && node.value === "var(--auth-sage)");
    if (!paintsSage) return;
    const selector = rule.selector.replace(/:(hover|focus-visible|active)\b/g, "[data-test-$1]");
    if (button.matches(selector)) matches.push(rule.selector);
  });
  return matches;
}

describe("account security session action CSS", () => {
  for (const source of sheets) {
    test.each([
      ["rest", []],
      ["hover", ["hover"]],
      ["keyboard focus", ["focus-visible"]],
      ["hover with keyboard focus", ["hover", "focus-visible"]],
      ["pressed", ["hover", "active"]],
      ["disabled hover", ["hover", "disabled"]],
    ] as const)(`${source}: destructive action excludes sage at %s`, async (_name, states) => {
      const page = await mount();
      try {
        const button = page.button("global");
        button.disabled = states.some((state) => state === "disabled");
        expect(sageRulesFor(button, source, [...states])).toEqual([]);
      } finally { await page.close(); }
    });

    test.each(["local", "others"])(`${source}: %s action keeps sage hover`, async (scope) => {
      const page = await mount();
      try {
        expect(sageRulesFor(page.button(scope), source, ["hover"]).length).toBeGreaterThan(0);
      } finally { await page.close(); }
    });
  }
});
