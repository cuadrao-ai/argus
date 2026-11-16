import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { act, useState } from "react";
import { createRoot } from "react-dom/client";
import BusinessSidebarNav from "@/components/business-app/BusinessSidebarNav";
import { BusinessContext, type BusinessContextValue, type BusinessPanelState } from "@/components/business-app/BusinessWorkspace";
import { useBusinessKeyboardShortcuts } from "@/components/business-app/business-keyboard-shortcuts";
import { ChatWorkspaceProvider, type ChatWorkspace, type ChatShellBridge } from "@/components/chat/ChatWorkspace";
import { useChatKeyboardShortcuts } from "@/components/keyboard/useChatKeyboardShortcuts";
import { workspaceShortcutKeys, type WorkspaceKeyboardShortcut } from "@/lib/keyboard-shortcuts";
import spanish from "@/public/locales/es-419/common.json";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
let cleanup = async () => {};
afterEach(async () => { await cleanup(); document.body.innerHTML = ""; });
afterAll(() => GlobalRegistrator.unregister());

async function mount(command: boolean) {
  Object.defineProperty(navigator, "userAgent", { configurable: true, value: command ? "Macintosh" : "Linux" });
  const i18n = createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  let registry: readonly WorkspaceKeyboardShortcut[] = [];
  function KeyboardHandler() {
    useChatKeyboardShortcuts({ enabled: true } as Parameters<typeof useChatKeyboardShortcuts>[0]);
    return null;
  }
  function Harness() {
    const [panel, openPanel] = useState<BusinessPanelState>({ kind: "overview" });
    registry = useBusinessKeyboardShortcuts({ openPanel, actions: { create: [], composer: [], starterEntries: [] }, chosen: null });
    const business = { panel, openPanel, records: { inbox: [] } } as unknown as BusinessContextValue;
    const shell = { currentView: "workspace", sidebarCollapsed: false, isBelowTablet: false } as ChatShellBridge;
    return <ChatWorkspaceProvider value={{ keyboardShortcuts: registry, chatAvailable: false } as ChatWorkspace}>
      <BusinessContext.Provider value={business}>
        <KeyboardHandler /><BusinessSidebarNav shell={shell} />
        <output data-testid="panel">{panel.kind}</output>
        <input aria-label="Search" /><textarea /><div contentEditable role="textbox" />
      </BusinessContext.Provider>
    </ChatWorkspaceProvider>;
  }
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  cleanup = async () => { await act(async () => root.unmount()); };
  await act(async () => root.render(<I18nextProvider i18n={i18n}><Harness /></I18nextProvider>));
  const dispatch = async (type: string, init: KeyboardEventInit = {}, target: EventTarget = document.body) => {
    const event = new KeyboardEvent(type, { bubbles: true, cancelable: true, ...init });
    await act(async () => { target.dispatchEvent(event); });
    return event;
  };
  const primary = command ? { metaKey: true, key: "Meta" } : { ctrlKey: true, key: "Control" };
  const chord = { ...primary, code: "Digit4", key: "4", ...(command ? { altKey: true } : { shiftKey: true }) };
  const hints = () => [...host.querySelectorAll('[aria-hidden="true"][class*="min-w-9"]')].filter((kbd) => !kbd.classList.contains("hidden"));
  return { host, registry, dispatch, primary, chord, hints };
}

for (const command of [true, false]) {
  const platform = command ? "command" : "control";
  test(`${platform}: the Actividad shortcut opens Actividad`, async () => {
    const view = await mount(command);
    const event = await view.dispatch("keydown", view.chord);
    assert.equal(view.host.querySelector("output")?.textContent, "activity");
    assert.equal(event.defaultPrevented, true);
    assert.equal(view.registry.find((item) => item.id === "activity")?.label, "Ir a Actividad");
  });
  test(`${platform}: holding the primary modifier shows registry hints and releasing hides them`, async () => {
    const view = await mount(command);
    assert.equal(view.hints().length, 0);
    await view.dispatch("keydown", view.primary);
    const jumps = view.registry.filter((item) => item.jumpIndex !== undefined);
    assert.equal(view.hints().length, 4);
    assert.deepEqual(view.hints().map((hint) => hint.textContent), jumps.map((item) => workspaceShortcutKeys(item, command).join(command ? "" : "+")));
    await view.dispatch("keyup", { key: view.primary.key });
    assert.equal(view.hints().length, 0);
  });
  test(`${platform}: typing fields suppress hints and navigation`, async () => {
    const view = await mount(command);
    for (const field of view.host.querySelectorAll<HTMLElement>("input, textarea, [contenteditable]")) {
      await act(async () => field.focus());
      await view.dispatch("keydown", view.primary, field);
      assert.equal(view.hints().length, 0);
      assert.equal((await view.dispatch("keydown", view.chord, field)).defaultPrevented, false);
      assert.equal(view.host.querySelector("output")?.textContent, "overview");
      assert.equal(view.host.querySelector('[aria-hidden="true"][class*="min-w-9"]'), null, "typing also disables hover hints");
    }
  });
  test(`${platform}: moving focus into a field or leaving the window clears held hints`, async () => {
    const view = await mount(command);
    await view.dispatch("keydown", view.primary);
    assert.equal(view.hints().length, 4);
    await act(async () => view.host.querySelector("input")!.focus());
    assert.equal(view.hints().length, 0);
    await act(async () => view.host.querySelector("input")!.blur());
    await view.dispatch("keydown", view.primary);
    assert.equal(view.hints().length, 4);
    await act(async () => window.dispatchEvent(new Event("blur")));
    assert.equal(view.hints().length, 0);
  });
}
