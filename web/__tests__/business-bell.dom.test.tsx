import { afterAll, afterEach, beforeAll, expect, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, useEffect } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import type { GrantedSpace } from "@/lib/business-api";
import type { BusinessNotice } from "@/lib/business-notifications";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";
import spanish from "@/public/locales/es-419/common.json";

mock.module("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(), usePathname: () => "/biz", useRouter: () => ({ push: () => {}, replace: () => {} }) }));

const ROLES = ["owner", "admin", "editor", "viewer"] as const;
const id = (group: number, index: number) => `${String(group).repeat(8)}-${String(group).repeat(4)}-4${String(group).repeat(3)}-8${String(group).repeat(3)}-${String(index).padStart(12, "0")}`;
const space = (index: number, name: string, role: (typeof ROLES)[number] = "owner"): GrantedSpace => ({ space_id: id(6, index), name, grant_id: id(7, index), role: role === "owner" ? "owner" : "accountant", business_role: role, permissions: ["read"], capabilities: ["read"], access_seen: true }) as GrantedSpace;
const invitation = (index: number, name: string, role: BusinessNotice["requested_role"], unread = true): BusinessNotice => ({ id: id(5, index), kind: "invitation_received", business_id: id(6, 50 + index), business_name: name, requested_role: role, unread });
const copy = spanish.business.notifications;

const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
const cleanups: (() => Promise<void>)[] = [];
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1280, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  globalThis.fetch = originalFetch;
  document.body.innerHTML = "";
});
afterAll(async () => {
  if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  await GlobalRegistrator.unregister();
});

type Setup = { spaces?: GrantedSpace[]; notices?: BusinessNotice[]; link?: string; reload?: boolean; listFails?: boolean; acceptStatus?: number; width?: number };

/** The live workspace over a server double: it lists Businesses and notices, marks them read and accepts. */
/** `link` arrives by the email link; `reload` loads the page again at the address and with the storage the last one left. */
async function open({ spaces = [], notices = [], link, reload = false, listFails = false, acceptStatus = 200, width = 1280 }: Setup) {
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessContextCue } = await import("@/components/business-app/BusinessPanel");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { useChatWorkspace } = await import("@/components/chat/ChatWorkspace");
  const { clearToasts } = await import("@/components/business-app/foundation/toasts");
  const { getChosenGrant, setChosenGrant, synchronizeBusinessAccount } = await import("@/lib/business-grant");
  const { capturePendingInvite, forgetPendingInvite, pendingInviteId } = await import("@/lib/business-pending-invite");
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 900 });
  synchronizeBusinessAccount("bell-person");
  setChosenGrant(null);
  clearToasts();
  if (!reload) {
    forgetPendingInvite();
    window.history.replaceState(null, "", link ? `/biz?invite=${link}` : "/biz");
  }
  capturePendingInvite();
  const server = { spaces: [...spaces], notices: [...notices], listFails, read: [] as string[][], accepted: [] as { invite: string; space_id: string }[] };
  const requests: string[] = [];
  const businessLoads: string[] = [];
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    requests.push(`${method} ${new URL(url, "http://localhost").pathname.replace(/^.*\/business\//, "/business/")}`);
    if (url.endsWith("/business/notifications")) return server.listFails ? Response.json({ code: "unavailable" }, { status: 503 }) : Response.json({ items: server.notices, unread_count: server.notices.filter((item) => item.unread).length });
    if (url.endsWith("/business/notifications/read")) {
      const { ids } = JSON.parse(String(init?.body)) as { ids: string[] };
      server.read.push(ids);
      server.notices = server.notices.map((item) => (ids.includes(item.id) ? { ...item, unread: false } : item));
      return Response.json({ updated: ids.length });
    }
    const accept = /\/business\/invitations\/([^/]+)\/accept$/.exec(url);
    if (accept) {
      if (acceptStatus !== 200) return Response.json({ code: "business_invite_not_live" }, { status: acceptStatus });
      const found = server.notices.find((item) => item.id === accept[1])!;
      const body = JSON.parse(String(init?.body)) as { space_id: string };
      server.accepted.push({ invite: accept[1], space_id: body.space_id });
      server.notices = server.notices.filter((item) => item !== found);
      const joined = { ...space(90 + server.spaces.length, found.business_name ?? "", found.requested_role), space_id: found.business_id, access_seen: false };
      server.spaces = [...server.spaces, joined];
      return Response.json({ space_id: found.business_id, grant_id: joined.grant_id });
    }
    return Response.json([]);
  };
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const counted = <T extends unknown[], R>(name: string, call: (...args: T) => R) => (...args: T) => { businessLoads.push(name); return call(...args); };
  const source = {
    ...fixture,
    mode: "live",
    workspace: counted("workspace", fixture.workspace),
    overview: counted("overview", fixture.overview),
    receipts: counted("receipts", fixture.receipts),
    receiptPage: undefined,
    captures: counted("captures", fixture.captures),
    spaces: async () => server.spaces,
    spaceDirectory: async () => ({ spaces: server.spaces, closed_spaces: [], invitations_available: true, can_start_business: false, notifications_available: true }),
  };
  const shell = { currentView: "workspace", conversationId: null, isBelowTablet: width < 768, sidebarCollapsed: false, greetingName: null, memberEmail: "bell@example.test", showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined } as unknown as ChatShellBridge;
  let business: ReturnType<typeof useBusiness> | undefined;
  function Probe() {
    business = useBusiness();
    const workspace = useChatWorkspace();
    useEffect(() => { workspace?.onShellChange?.(shell); }, [workspace]);
    return <><header>{workspace?.headerActions(shell)}</header><nav>{workspace?.sidebarNav?.(shell)}</nav><main>{business.spaces?.length ? null : workspace?.panel(shell)}</main><aside><BusinessContextCue /></aside></>;
  }
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  let left = false;
  const leave = async () => { if (!left) await act(async () => root.unmount()); left = true; };
  cleanups.push(async () => { await leave(); forgetPendingInvite(); clearToasts(); synchronizeBusinessAccount(null); });
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source as never} userId="bell-person"><Probe /></BusinessWorkspaceProvider></BusinessConsentTestProvider></I18nextProvider>));
  const until = async (ready: () => boolean, what: string) => {
    for (let turn = 0; turn < 200 && !ready(); turn += 1) await act(async () => new Promise((resolve) => setTimeout(resolve, 5)));
    if (!ready()) throw new Error(`never happened: ${what}`);
  };
  const bell = () => host.querySelector<HTMLButtonElement>('[data-testid="business-notifications-trigger"]');
  const panel = () => document.querySelector<HTMLElement>('[role="dialog"], [data-testid="business-notifications-sheet"]');
  const rows = () => [...(panel()?.querySelectorAll<HTMLLIElement>("li[data-notice]") ?? [])];
  const button = (label: string, within: ParentNode = document) => [...within.querySelectorAll<HTMLButtonElement>("button")].find((found) => found.textContent?.trim() === label);
  await until(() => bell() !== null && requests.includes("GET /business/notifications"), "the bell and its first list");
  await act(async () => new Promise((resolve) => setTimeout(resolve, 30)));
  return {
    host, server, requests, businessLoads, until, bell, panel, rows, button, leave,
    addressNamesAnInvite: () => new URLSearchParams(window.location.search).has("invite"),
    business: () => business!,
    chosen: getChosenGrant,
    pending: pendingInviteId,
    dot: () => host.querySelector<HTMLElement>('[data-testid="business-notifications-dot"]'),
    toast: () => document.querySelector<HTMLElement>('[data-testid="toast"]'),
    accessLine: () => host.querySelector<HTMLElement>('[data-testid="business-access-line"]'),
    lists: () => requests.filter((request) => request === "GET /business/notifications").length,
    press: async (target: HTMLElement | null | undefined) => { expect(target).toBeTruthy(); await act(async () => target!.click()); },
  };
}

test("a new invitee from the link lands on the bell, open on that invitation, with no Business screen behind it", { timeout: 15000 }, async () => {
  const mine = invitation(1, "Panadería La Espiga", "admin");
  const page = await open({ notices: [invitation(2, "Ferretería Don Pepe", "editor"), mine], link: mine.id });
  await page.until(() => page.rows().length === 2, "the invitations");
  const linked = page.rows().find((row) => row.dataset.linked !== undefined)!;
  expect(linked.dataset.notice).toBe(mine.id);
  expect(linked.textContent).toContain("Panadería La Espiga");
  expect(linked.textContent).toContain("Administrador · Pendiente de aceptación");
  expect(document.activeElement).toBe(page.button("Aceptar invitación", linked)!);
  expect(page.businessLoads).toEqual([]);
  expect(page.host.querySelector("main")!.textContent).toBe("");
  expect(page.host.querySelector("nav")!.textContent).toBe("");
  expect(document.querySelector('[role="alert"]')).toBeNull();

  await page.press(page.button("Aceptar invitación", linked));
  await page.until(() => page.chosen() !== null, "entering the Business");
  expect(page.server.accepted).toEqual([{ invite: mine.id, space_id: mine.business_id }]);
  expect(page.chosen()).toBe(page.server.spaces[0].grant_id);
  expect(page.pending()).toBeNull();
  expect(page.panel()).toBeNull();
  await page.until(() => page.accessLine() !== null, "the access line");
  expect(page.accessLine()!.textContent).toContain("Ahora tienes acceso a Panadería La Espiga · Administrador");
  expect(page.button("Entendido", page.accessLine()!)).toBeTruthy();
  expect(page.toast()).toBeNull();
});

test("an existing person from the link gets the bell open on that invitation, and accepting enters that Business", { timeout: 15000 }, async () => {
  const own = space(1, "Colmado Doña Rosa");
  const mine = invitation(1, "Panadería La Espiga", "viewer");
  const page = await open({ spaces: [own], notices: [mine], link: mine.id });
  await page.until(() => page.rows().length === 1, "the invitation");
  expect(page.rows()[0].dataset.linked).toBe("");
  expect(page.rows()[0].textContent).toContain("Lector · Pendiente de aceptación");
  await page.press(page.button("Aceptar invitación", page.rows()[0]));
  await page.until(() => page.chosen() === page.server.spaces[1].grant_id, "entering the invited Business");
  expect(page.pending()).toBeNull();
  await page.until(() => page.accessLine() !== null, "the access line");
  expect(page.accessLine()!.textContent).toContain("Ahora tienes acceso a Panadería La Espiga · Lector");
  expect(page.toast()).toBeNull();
});

test("with no link the dot waits, opening marks it read on the server, and accepting stays put and offers the way in", { timeout: 15000 }, async () => {
  const own = space(1, "Colmado Doña Rosa");
  const waiting = invitation(1, "Panadería La Espiga", "editor");
  const page = await open({ spaces: [own], notices: [waiting] });
  await page.until(() => page.chosen() === own.grant_id, "working in the own Business");
  expect(page.panel()).toBeNull();
  expect(page.dot()).toBeTruthy();
  expect(page.dot()!.dataset.arrived).toBeUndefined();
  expect(page.server.read).toEqual([]);

  await page.press(page.bell());
  await page.until(() => page.server.read.length === 1, "the server marking it read");
  await act(async () => new Promise((resolve) => setTimeout(resolve, 50)));
  expect(page.server.read).toEqual([[waiting.id]]);
  expect(page.dot()).toBeNull();
  expect(page.rows()[0].querySelector('[role="img"]')!.getAttribute("aria-label")).toBe(copy.unread_label);

  await page.press(page.button("Aceptar invitación", page.rows()[0]));
  await page.until(() => page.toast() !== null, "the confirmation");
  expect(page.chosen()).toBe(own.grant_id);
  expect(page.toast()!.textContent).toContain("Invitación aceptada.");
  expect(page.button(copy.go_to_business, page.toast()!)).toBeTruthy();
  expect(page.accessLine()).toBeNull();
  expect(page.panel()!.textContent).toContain(copy.empty_all_title);
  await page.press(page.button(copy.go_to_business, page.toast()!));
  await page.until(() => page.chosen() === page.server.spaces[1].grant_id, "going to the Business");
});

test("a link to an invitation that is withdrawn or dead says so, once", { timeout: 15000 }, async () => {
  const page = await open({ spaces: [space(1, "Colmado Doña Rosa")], notices: [], link: id(5, 9) });
  await page.until(() => page.panel() !== null, "the bell opening");
  expect(page.panel()!.querySelector('[role="status"]')!.textContent).toBe(`${copy.invitation_gone_title}${copy.invitation_gone_body}`);
  expect(page.panel()!.textContent).toContain(copy.empty_all_title);
  expect(page.pending()).toBeNull();
  expect(page.addressNamesAnInvite()).toBe(false);
  await page.press(page.button("Cerrar", page.panel()!) ?? page.panel()!.querySelector<HTMLButtonElement>('[aria-label="Cerrar"]'));
  await page.press(page.bell());
  expect(page.panel()!.querySelector('[role="status"]')).toBeNull();

  await page.leave();
  const again = await open({ spaces: page.server.spaces, notices: [], reload: true });
  await again.until(() => again.chosen() !== null, "the Business after the reload");
  expect(again.panel()).toBeNull();
  expect(again.pending()).toBeNull();
});

test("after accepting from the link, a reload leaves the bell closed and the address names no invitation", { timeout: 15000 }, async () => {
  const mine = invitation(1, "Panadería La Espiga", "viewer");
  const page = await open({ spaces: [space(1, "Colmado Doña Rosa")], notices: [mine], link: mine.id });
  await page.until(() => page.rows().length === 1, "the invitation");
  expect(page.addressNamesAnInvite()).toBe(false);
  await page.press(page.button("Aceptar invitación", page.rows()[0]));
  await page.until(() => page.chosen() === page.server.spaces[1].grant_id, "entering the invited Business");
  expect(page.addressNamesAnInvite()).toBe(false);

  await page.leave();
  const again = await open({ spaces: page.server.spaces, notices: page.server.notices, reload: true });
  await again.until(() => again.chosen() !== null, "the Business after the reload");
  expect(again.panel()).toBeNull();
  expect(again.pending()).toBeNull();
  expect(document.querySelector('[role="status"]')).toBeNull();
});

test("a list that does not load says so with Reintentar, and the retry shows it", { timeout: 15000 }, async () => {
  const page = await open({ spaces: [space(1, "Colmado Doña Rosa")], notices: [invitation(1, "Panadería La Espiga", "admin")], listFails: true });
  expect(page.dot()).toBeNull();
  await page.press(page.bell());
  await page.until(() => page.panel()?.querySelector('[role="alert"]') != null, "the failure line");
  expect(page.panel()!.querySelector('[role="alert"]')!.textContent).toBe("No pudimos cargar tus avisos. Inténtalo de nuevo.");
  page.server.listFails = false;
  await page.press(page.button("Reintentar", page.panel()!));
  await page.until(() => page.rows().length === 1, "the list after the retry");
  expect(page.panel()!.querySelector('[role="alert"]')).toBeNull();
});

test("an invitation the server refuses to accept keeps its row, says so and turns its button off", { timeout: 15000 }, async () => {
  const page = await open({ spaces: [space(1, "Colmado Doña Rosa")], notices: [invitation(1, "Panadería La Espiga", "admin")], acceptStatus: 409 });
  await page.press(page.bell());
  await page.press(page.button("Aceptar invitación", page.rows()[0]));
  await page.until(() => page.rows()[0]?.querySelector('[role="alert"]') != null, "the refusal");
  expect(page.rows()[0].querySelector('[role="alert"]')!.textContent).toBe(spanish.business_access.invitation_accept_failed);
  expect(page.button("Aceptar invitación", page.rows()[0])!.disabled).toBe(true);
  expect(page.toast()).toBeNull();
});

for (const role of ROLES) {
  test(`a page load as ${role} asks for the notices once and for no sender list`, { timeout: 15000 }, async () => {
    const page = await open({ spaces: [space(1, "Colmado Doña Rosa", role)], notices: [invitation(1, "Panadería La Espiga", "admin")] });
    await page.until(() => page.chosen() !== null, "the Business");
    expect(page.requests.filter((request) => /senders/.test(request))).toEqual([]);
    expect(page.requests.filter((request) => /\/business\/invitations/.test(request))).toEqual([]);
    expect(page.lists()).toBe(1);
  });
}

test("switching Businesses keeps the same bell and the same list", { timeout: 15000 }, async () => {
  const first = space(1, "Colmado Doña Rosa");
  const second = space(2, "Taller Hermanos Peña", "admin");
  const page = await open({ spaces: [first, second], notices: [invitation(1, "Panadería La Espiga", "admin"), invitation(2, "Ferretería Don Pepe", "editor")] });
  await page.until(() => page.chosen() === first.grant_id, "the first Business");
  await page.press(page.bell());
  await page.until(() => page.rows().length === 2, "the list");
  const shown = page.rows().map((row) => row.textContent);
  const lists = page.lists();
  await act(async () => page.business().chooseBusiness(second.grant_id));
  await page.until(() => page.chosen() === second.grant_id, "the second Business");
  await act(async () => new Promise((resolve) => setTimeout(resolve, 50)));
  expect(page.rows().map((row) => row.textContent)).toEqual(shown);
  expect(page.lists()).toBe(lists);
  expect(page.requests.filter((request) => request.includes("business_id"))).toEqual([]);
});

test("the dot pops only for a notice that arrives after the first answer", { timeout: 15000 }, async () => {
  const page = await open({ spaces: [space(1, "Colmado Doña Rosa")], notices: [] });
  expect(page.dot()).toBeNull();
  page.server.notices = [invitation(3, "Panadería La Espiga", "admin")];
  await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
  await page.until(() => page.dot() !== null, "the dot");
  expect(page.dot()!.dataset.arrived).toBe("");
});

test("on a phone the bell opens in the sheet with the same rows", { timeout: 15000 }, async () => {
  const mine = invitation(1, "Panadería La Espiga", "owner");
  const page = await open({ notices: [mine], width: 390 });
  await page.until(() => page.rows().length === 1, "the invitation in the sheet");
  expect(page.rows()[0].textContent).toContain("Dueño · Pendiente de aceptación");
});
