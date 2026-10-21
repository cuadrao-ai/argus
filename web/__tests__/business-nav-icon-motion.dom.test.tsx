import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { afterAll, afterEach, beforeAll, beforeEach, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { renderToStaticMarkup } from "react-dom/server";
import { createInstance } from "i18next";
import { History } from "lucide-react";
import { ArrowsLeftRight, SquaresFour, Tray, type Icon } from "@phosphor-icons/react";
import { I18nextProvider } from "react-i18next";
import type { ReactNode } from "react";
import type { BusinessContextValue, BusinessPanelState } from "@/components/business-app/BusinessWorkspace";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";

const cleanups: (() => Promise<void>)[] = [];

/** Each move the page starts, so a test can finish or cancel it the way a browser would. */
type Move = { icon: Element; finish: () => void; cancel: () => void };
let moves: Move[] = [];

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
beforeEach(() => {
  moves = [];
  // The browser lists one running animation per part while the icon is moving, and none at rest or with reduced motion.
  (Element.prototype as unknown as { getAnimations: (this: Element) => unknown[] }).getAnimations = function getAnimations(this: Element) {
    if (this.getAttribute("data-move") === null) return [];
    let finish = () => {};
    let cancel = () => {};
    const finished = new Promise<void>((resolve, reject) => { finish = resolve; cancel = () => reject(new Error("AbortError")); });
    moves.push({ icon: this, finish, cancel });
    return [{ finished, effect: { target: this.querySelector("[data-part]") } }];
  };
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

async function settle(run: () => void = () => {}) {
  const { act } = await import("react");
  await act(async () => { run(); });
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
    button,
    current: button.getAttribute("aria-current") === "page",
    icon: button.querySelector<HTMLElement>("[data-nav-icon]")!,
  }));
  return { show, icons };
}

async function mountRow(name: "overview" | "inbox" | "transactions", active = false) {
  const { default: SidebarNavButton } = await import("@/components/sidebar/SidebarNavButton");
  const { NAV_GLYPHS, navGlyph } = await import("@/components/business-app/nav-glyphs");
  const view = await mount();
  await view.render(<SidebarNavButton glyph={navGlyph(NAV_GLYPHS[name])} label={name} active={active} onClick={() => {}} variant="business" />);
  const button = view.host.querySelector("button")!;
  const icon = view.host.querySelector<HTMLElement>("[data-nav-icon]")!;
  const pointer = (type: "pointerenter" | "pointerleave", pointerType = "mouse") => settle(() => button.dispatchEvent(new PointerEvent(type, { pointerType })));
  return { button, icon, pointer, moving: () => icon.dataset.move !== undefined };
}

/** A path's subpaths, each starting from an absolute point, so two spellings of one drawing compare equal. */
function subpaths(d: string): string[] {
  const out: string[] = [];
  let start: [number, number] = [0, 0];
  for (const chunk of d.match(/[Mm][^Mm]*/g) ?? []) {
    const [x, y] = chunk.slice(1).match(/-?\d*\.?\d+/g)!.slice(0, 2).map(Number);
    start = chunk[0] === "m" ? [start[0] + x, start[1] + y] : [x, y];
    const rest = chunk.slice(1).replace(/^-?\d*\.?\d+,?-?\d*\.?\d+,?/, "");
    // Numbers straight after a move are line-tos of the same case, so spell that line-to out.
    out.push(`M${start.join(",")}${/^[-\d.]/.test(rest) ? (chunk[0] === "m" ? "l" : "L") : ""}${rest}`);
  }
  return out;
}

function phosphorPath(Glyph: Icon, weight: "regular" | "fill") {
  return renderToStaticMarkup(<Glyph weight={weight} />).match(/ d="([^"]+)"/)![1];
}

test("each icon is drawn in parts that, at rest, are exactly the Phosphor icon it replaces in both weights", async () => {
  const { NAV_GLYPHS, NavIcon } = await import("@/components/business-app/nav-glyphs");
  const cases = [
    { glyph: NAV_GLYPHS.overview, phosphor: SquaresFour, parts: ["tile", "tile", "tile", "tile"] },
    { glyph: NAV_GLYPHS.inbox, phosphor: Tray, parts: ["tray"] },
    { glyph: NAV_GLYPHS.transactions, phosphor: ArrowsLeftRight, parts: ["arrow-left", "arrow-right"] },
  ] as const;
  for (const { glyph, phosphor, parts } of cases) {
    const host = document.createElement("div");
    host.innerHTML = renderToStaticMarkup(<NavIcon glyph={glyph} active={false} size={20} />);
    for (const weight of ["regular", "fill"] as const) {
      const svg = host.querySelector(`svg[data-weight="${weight}"]`)!;
      assert.equal(svg.getAttribute("viewBox"), "0 0 256 256");
      assert.equal(svg.getAttribute("width"), "20");
      const drawn = [...svg.querySelectorAll("[data-part]")].filter((part) => part.getAttribute("data-part") !== "receipt");
      assert.deepEqual(drawn.map((part) => part.getAttribute("data-part")), [...parts], `${glyph.name} ${weight} parts`);
      const geometry = drawn.flatMap((part) => part.tagName.toLowerCase() === "path" ? [part.getAttribute("d")!] : [...part.querySelectorAll(":scope > path")].map((path) => path.getAttribute("d")!));
      // The parts never overlap, so the order they are painted in does not change a pixel.
      assert.deepEqual(geometry.flatMap(subpaths).sort(), subpaths(phosphorPath(phosphor, weight)).sort(), `${glyph.name} ${weight} matches Phosphor`);
      const rest = svg.querySelector("[data-rest]");
      if (rest) assert.deepEqual(subpaths(rest.getAttribute("d")!), subpaths(phosphorPath(phosphor, weight)), `${glyph.name} ${weight} rest path`);
    }
  }
  const tray = document.createElement("div");
  tray.innerHTML = renderToStaticMarkup(<NavIcon glyph={NAV_GLYPHS.inbox} active={false} />);
  assert.equal(tray.querySelectorAll('[data-part="receipt"]').length, 2, "each weight of the Bandeja carries the receipt that drops in");
});

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

test("a tab settles and plays its move only when it becomes the current screen, never on first paint or on a touch", async () => {
  const tabs = await mountTabs();
  await tabs.show("overview");
  const state = () => tabs.icons().map(({ icon }) => `${"settle" in icon.dataset ? "settle" : "-"}/${"move" in icon.dataset ? "move" : "-"}`);
  assert.deepEqual(state(), ["-/-", "-/-", "-/-"], "first paint is still");
  await settle(() => tabs.icons()[1].button.dispatchEvent(new PointerEvent("pointerenter", { pointerType: "touch" })));
  assert.deepEqual(state(), ["-/-", "-/-", "-/-"], "a finger landing is not a hover");
  await tabs.show("inbox");
  assert.deepEqual(state(), ["-/-", "settle/move", "-/-"], "only the newly current icon settles and moves");
  await settle(() => moves.forEach((move) => move.finish()));
  await tabs.show("transactions");
  assert.deepEqual(state(), ["-/-", "-/-", "settle/move"], "the one left goes back to outline without a move");
});

test("a pointer entering a rail row plays its move once, and a move already playing finishes instead of restarting", async () => {
  for (const name of ["overview", "inbox", "transactions"] as const) {
    const row = await mountRow(name);
    assert.equal(row.moving(), false, `${name}: still on first paint`);
    await row.pointer("pointerenter");
    assert.equal(row.moving(), true, `${name}: hover plays the move`);
    assert.equal(moves.length, 1);
    await row.pointer("pointerleave");
    await row.pointer("pointerenter");
    assert.equal(moves.length, 1, `${name}: a fast sweep does not restart a move midway`);
    await settle(() => moves[0].finish());
    assert.equal(row.moving(), false, `${name}: back at rest when the move ends`);
    moves = [];
  }
});

test("leaving replays the move for Inicio and Transacciones, whose moves read both ways, and not for the Bandeja", async () => {
  for (const [name, replays] of [["overview", true], ["inbox", false], ["transactions", true]] as const) {
    const row = await mountRow(name);
    await row.pointer("pointerenter");
    await settle(() => moves[0].finish());
    await row.pointer("pointerleave");
    assert.equal(row.moving(), replays, name);
    moves = [];
  }
});

test("a move cut short, as when its animations are cancelled, still returns the icon to rest", async () => {
  const row = await mountRow("transactions");
  await row.pointer("pointerenter");
  await settle(() => moves[0].cancel());
  assert.equal(row.moving(), false);
  await row.pointer("pointerenter");
  assert.equal(row.moving(), true, "and the next hover plays it again");
});

test("keyboard focus plays the move once", async () => {
  const row = await mountRow("inbox");
  await settle(() => row.button.focus());
  assert.equal(row.moving(), true);
});

test("opening and closing the rail never replays the settle or the move", async () => {
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
    assert.equal("settle" in icon.dataset, false, `settle, collapsed=${collapsed}`);
    assert.equal("move" in icon.dataset, false, `move, collapsed=${collapsed}`);
  }
});

test("with reduced motion the icon changes weight at once and no part moves", () => {
  const css = readFileSync(new URL("../components/business-app/nav-glyphs.module.css", import.meta.url), "utf8");
  const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
  assert.ok(reduced.length < css.length, "the stylesheet has a reduced motion block");
  for (const selector of [".icon,", ".layer,", ".icon[data-settle],", ".icon[data-move] [data-part],"]) assert.ok(reduced.includes(selector), selector);
  assert.match(reduced, /transition: none;\s*animation: none;/);
  assert.match(reduced, /:global\(button\):active \.icon\[data-active\] \{\s*transform: none;/, "no press shrink");
  for (const keyframes of css.matchAll(/@keyframes (nav-move-[\w-]+)/g)) {
    assert.ok(css.includes(`animation: ${keyframes[1]} `), `${keyframes[1]} is only started by a data-move selector`);
  }
  assert.doesNotMatch(css.slice(0, css.indexOf("@media")), /forwards|both|infinite/, "no move holds a pose after it ends or loops");
});

test("personal sidebar rows keep their own icon and hover", async () => {
  const { default: SidebarNavButton } = await import("@/components/sidebar/SidebarNavButton");
  const html = renderToStaticMarkup(<SidebarNavButton icon={History} label="Recents" active onClick={() => {}} />);
  assert.equal(html.includes("data-nav-icon"), false);
  assert.equal(html.includes("data-part"), false);
  assert.match(html, /lucide-history/);
  assert.match(html, /group-hover:scale-\[1\.06\]/);
  assert.match(html, /aria-current="page"/);
});
