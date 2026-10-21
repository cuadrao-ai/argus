import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { renderToStaticMarkup } from "react-dom/server";
import { createInstance } from "i18next";
import { History } from "lucide-react";
import { I18nextProvider } from "react-i18next";
import type { ReactNode } from "react";
import type { BusinessContextValue, BusinessPanelState } from "@/components/business-app/BusinessWorkspace";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";

const cleanups: (() => Promise<void>)[] = [];

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  document.body.innerHTML = "";
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function mount() {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  cleanups.push(() => act(async () => root.unmount()));
  return { host, render: (node: ReactNode) => act(async () => root.render(node)) };
}

async function mountTabs() {
  const { default: BusinessBottomTabs } = await import("@/components/business-app/BusinessBottomTabs");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const shell = { currentView: "workspace" } as unknown as ChatShellBridge;
  const i18n = createInstance();
  await i18n.init({ lng: "es-419", resources: {}, interpolation: { escapeValue: false } });
  const view = await mount();
  const show = (kind: BusinessPanelState["kind"]) => {
    const business = { panel: { kind }, openPanel: () => {}, records: { inbox: [] } } as unknown as BusinessContextValue;
    return view.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={business}><BusinessBottomTabs shell={shell} /></BusinessContext.Provider></I18nextProvider>);
  };
  const icons = () => [...view.host.querySelectorAll("button")].map((button) => ({
    current: button.getAttribute("aria-current") === "page",
    icon: button.querySelector<HTMLElement>("[data-nav-icon]")!,
  }));
  return { show, icons };
}

test("each tab draws both weights and shows the filled one only on the screen you are on", async () => {
  const tabs = await mountTabs();
  for (const [kind, index] of [["overview", 0], ["inbox", 1], ["transactions", 2]] as const) {
    await tabs.show(kind);
    tabs.icons().forEach(({ current, icon }, position) => {
      assert.equal(current, position === index, `${kind}: aria-current on tab ${position}`);
      assert.equal(icon.dataset.active, String(position === index), `${kind}: weight state of tab ${position}`);
      assert.deepEqual([...icon.querySelectorAll("svg")].map((svg) => svg.dataset.weight), ["regular", "fill"]);
    });
  }
});

test("an icon settles only when it becomes the current screen, never on first paint", async () => {
  const tabs = await mountTabs();
  await tabs.show("overview");
  assert.deepEqual(tabs.icons().map(({ icon }) => "settle" in icon.dataset), [false, false, false], "first paint is still");
  await tabs.show("inbox");
  assert.deepEqual(tabs.icons().map(({ icon }) => "settle" in icon.dataset), [false, true, false], "only the newly current icon settles");
  await tabs.show("transactions");
  assert.deepEqual(tabs.icons().map(({ icon }) => "settle" in icon.dataset), [false, false, true], "the one left goes back to outline without a settle");
});

test("opening and closing the rail never replays the settle", async () => {
  const { default: SidebarNavButton } = await import("@/components/sidebar/SidebarNavButton");
  const { NAV_GLYPHS, navGlyph } = await import("@/components/business-app/nav-glyphs");
  const view = await mount();
  const row = (collapsed: boolean) => (
    <SidebarNavButton glyph={navGlyph(NAV_GLYPHS.inbox)} label="Bandeja" active collapsed={collapsed} onClick={() => {}} variant="business" />
  );
  for (const collapsed of [false, true, false]) {
    await view.render(row(collapsed));
    const icon = view.host.querySelector<HTMLElement>("[data-nav-icon]")!;
    assert.equal(icon.dataset.active, "true");
    assert.equal("settle" in icon.dataset, false, `collapsed=${collapsed}`);
  }
});

test("with reduced motion the icon changes weight at once and does not move", () => {
  const css = readFileSync(new URL("../components/business-app/nav-glyphs.module.css", import.meta.url), "utf8");
  const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
  assert.ok(reduced.length < css.length, "the stylesheet has a reduced motion block");
  for (const selector of [".icon,", ".layer,", ".icon[data-settle]"]) assert.ok(reduced.includes(selector), selector);
  assert.match(reduced, /transition: none;\s*animation: none;/);
  assert.match(reduced, /\.icon\[data-active\] \{\s*translate: none;/, "no hover lift");
  assert.match(reduced, /:global\(button\):active \.icon\[data-active\] \{\s*transform: none;/, "no press shrink");
});

test("personal sidebar rows keep their own icon and hover", async () => {
  const { default: SidebarNavButton } = await import("@/components/sidebar/SidebarNavButton");
  const html = renderToStaticMarkup(<SidebarNavButton icon={History} label="Recents" active onClick={() => {}} />);
  assert.equal(html.includes("data-nav-icon"), false);
  assert.match(html, /lucide-history/);
  assert.match(html, /group-hover:scale-\[1\.06\]/);
  assert.match(html, /aria-current="page"/);
});
