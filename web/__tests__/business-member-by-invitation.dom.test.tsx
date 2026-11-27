import { afterAll, afterEach, beforeAll, expect, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, useEffect } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import type { GrantedSpace } from "@/lib/business-api";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";
import english from "@/public/locales/en/common.json";

mock.module("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(), usePathname: () => "/biz", useRouter: () => ({ push: () => {}, replace: () => {} }) }));

const shell = { currentView: "workspace", conversationId: null, isBelowTablet: false, sidebarCollapsed: false, memberEmail: "admin@example.test", showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined } as unknown as ChatShellBridge;
/** The Business of someone else, joined by invitation as Administrador. */
const joined: GrantedSpace = { space_id: "66666666-6666-4666-8666-000000000001", name: "Colmado La Esquina", grant_id: "77777777-7777-4777-8777-000000000001", role: "accountant", business_role: "admin", permissions: ["read", "prepare", "approve", "manage", "download", "export"], capabilities: ["read", "prepare", "approve"], access_seen: true } as GrantedSpace;

beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost/biz", width: 1280, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(() => { document.body.innerHTML = ""; });
afterAll(() => GlobalRegistrator.unregister());

async function openSwitcher(canStartBusiness: boolean) {
  const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { useChatWorkspace } = await import("@/components/chat/ChatWorkspace");
  const { getChosenGrant, setChosenGrant, synchronizeBusinessAccount } = await import("@/lib/business-grant");
  synchronizeBusinessAccount("member");
  setChosenGrant(null);
  let starts = 0;
  const source = {
    ...createFixtureBusinessDataSource({ chatAvailable: false }),
    mode: "live",
    ensureSpace: async () => { starts += 1; throw Object.assign(new Error("API error 403"), { status: 403, code: "private_alpha_access_required" }); },
    spaces: async () => [joined],
    spaceDirectory: async () => ({ spaces: [joined], closed_spaces: [], invitations_available: true, can_start_business: canStartBusiness }),
  };
  function Probe() {
    const workspace = useChatWorkspace();
    useEffect(() => { workspace?.onShellChange?.(shell); }, [workspace]);
    return <header>{workspace?.sidebarHeader?.(shell)}</header>;
  }
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "en", resources: { en: { translation: english } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source as never} userId="member"><Probe /></BusinessWorkspaceProvider></BusinessConsentTestProvider></I18nextProvider>));
  const item = (label: string) => [...document.querySelectorAll<HTMLButtonElement>("[role=menuitem]")].find((found) => found.textContent?.includes(label));
  for (let turn = 0; turn < 200 && getChosenGrant() !== joined.grant_id; turn += 1) await act(async () => new Promise((resolve) => setTimeout(resolve, 5)));
  await act(async () => new Promise((resolve) => setTimeout(resolve, 50)));
  await act(async () => document.querySelector<HTMLButtonElement>("button[aria-haspopup=menu]")!.click());
  return { item, starts: () => starts, chosen: getChosenGrant, unmount: async () => { await act(async () => root.unmount()); synchronizeBusinessAccount(null); } };
}

test("a member who joined by invitation works in that Business and no page load starts one of their own", { timeout: 10000 }, async () => {
  const page = await openSwitcher(false);
  try {
    expect(page.chosen()).toBe(joined.grant_id);
    expect(page.starts()).toBe(0);
    expect(page.item(english.workspace_setup_preview.batch_title)?.disabled).toBe(false);
    expect(page.item(english.business.switcher.add)?.disabled).toBe(true);
  } finally { await page.unmount(); }
});

test("a new Business is offered when the server says the person may start one", { timeout: 10000 }, async () => {
  const page = await openSwitcher(true);
  try {
    expect(page.item(english.business.switcher.add)?.disabled).toBe(false);
    expect(page.starts()).toBe(0);
  } finally { await page.unmount(); }
});
