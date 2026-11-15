import { readFileSync } from "node:fs";
import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import postcss from "postcss";
import { compile } from "tailwindcss";
import { Features, transform } from "lightningcss";

const globals = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
const sessions = readFileSync(new URL("../components/auth/account-security.module.css", import.meta.url), "utf8");
const variants: string[] = [];
postcss.parse(globals).walkAtRules("custom-variant", (rule) => { variants.push(`${rule.toString()};`); });
const lookProperties = new Set([
  "color", "background", "background-color", "border-color", "border-width", "border-style",
  "opacity", "outline", "outline-style", "outline-width", "outline-color", "outline-offset", "text-decoration-line",
]);

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
  // Compile the rendered utilities so a red label or outline is observable as
  // an applicable CSS declaration, rather than a class-name string assertion.
  const classes = [...host.querySelectorAll("[class]")].flatMap((element) => [...element.classList]);
  const utilities = (await compile(`${variants.join("\n")}\n@tailwind utilities;`)).build(classes);
  const flattened = transform({ filename: "session-utilities.css", code: Buffer.from(utilities), include: Features.Nesting }).code.toString();
  return {
    css: `${globals}\n${sessions}\n${flattened}`,
    button: (scope: string) => host.querySelector<HTMLButtonElement>(`[data-scope="${scope}"] button`)!,
    close: async () => { await act(async () => root.unmount()); host.remove(); },
  };
}

function appliedLook(button: HTMLButtonElement, css: string, states: readonly string[]) {
  // Pointer states are simulated; real ancestry, theme, attributes and disabled
  // state are matched by the DOM. These checks model a hover-capable viewport.
  for (const state of ["hover", "focus-visible", "active"]) {
    button.toggleAttribute(`data-test-${state}`, states.includes(state));
  }
  button.disabled = states.includes("disabled");
  const declarations: string[] = [];
  postcss.parse(css).walkRules((rule) => {
    if (rule.parent?.type === "atrule" && rule.parent.name.endsWith("keyframes")) return;
    const selector = rule.selector.replace(/:(hover|focus-visible|active)\b/g, "[data-test-$1]");
    if (!rule.nodes.some((node) => node.type === "decl" && lookProperties.has(node.prop)) || !button.matches(selector)) return;
    rule.walkDecls((declaration) => {
      if (lookProperties.has(declaration.prop)) declarations.push(`${declaration.prop}: ${declaration.value}${declaration.important ? " !important" : ""}`);
    });
  });
  return declarations.sort();
}

describe("account security quiet session actions", () => {
  for (const theme of ["light", "dark"]) {
    test.each([
      ["rest", []], ["hover", ["hover"]], ["keyboard focus", ["focus-visible"]],
      ["hover with keyboard focus", ["hover", "focus-visible"]],
      ["pressed", ["hover", "active"]], ["disabled", ["disabled"]],
    ] as const)(`${theme}: all sessions uses the same quiet look at %s`, async (_name, states) => {
      document.documentElement.classList.toggle("dark", theme === "dark");
      const page = await mount();
      try {
        const expected = appliedLook(page.button("local"), page.css, states);
        expect(expected.length).toBeGreaterThan(0);
        expect(appliedLook(page.button("others"), page.css, states)).toEqual(expected);
        expect(appliedLook(page.button("global"), page.css, states)).toEqual(expected);
      } finally {
        await page.close();
        document.documentElement.classList.remove("dark");
      }
    });
  }
});
