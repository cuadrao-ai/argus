import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ClosedGrantedSpace, GrantedSpace } from "@/lib/business-api";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";

// A real DOM: the switcher is a button and a listbox driven by the keyboard,
// and the cue lines read the context the provider builds from the server's list.
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const OWN: GrantedSpace = { space_id: "s-own", name: "Ferretería Luna", grant_id: "g-own", role: "owner", business_role:"owner",permissions:["read","prepare","approve","manage","assign_owner","download","export"],capabilities: ["read", "prepare", "approve"], access_seen: true };
const CLIENT: GrantedSpace = { space_id: "s-client", name: "Colmado Peña", grant_id: "g-client", role: "accountant", business_role:"editor",permissions:["read","prepare","download","export"],capabilities: ["read", "prepare"], access_seen: false };
const OTHER: GrantedSpace = { space_id: "s-other", name: "Taller Brito", grant_id: "g-other", role: "accountant", business_role:"editor",permissions:["read","prepare","download","export"],capabilities: ["read", "prepare"], access_seen: true };

async function setup() {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const settle = () => act(async () => { await Promise.resolve(); await Promise.resolve(); });
  return { act, root, host, settle, I18nextProvider, i18n };
}

async function mountSwitcher(spaces: GrantedSpace[] | null, chosen: GrantedSpace | null, collapsed = false, closedSpaces: ClosedGrantedSpace[] = [], invite = false) {
  const env = await setup();
  const { default: BusinessSwitcher } = await import("@/components/business-app/BusinessSwitcher");
  const chosenIds: (string | null)[] = [];
  const opened: string[] = [];
  await env.act(async () => {
    env.root.render(
      <env.I18nextProvider i18n={env.i18n}>
        <BusinessSwitcher spaces={spaces} closedSpaces={closedSpaces} chosen={chosen} collapsed={collapsed} onChoose={(id) => chosenIds.push(id)} onOpenSettings={() => opened.push("settings")} onInvite={invite ? () => opened.push("access") : undefined} memberEmail="member@example.test" />
      </env.I18nextProvider>,
    );
  });
  await env.settle();
  return { ...env, chosenIds, opened };
}

const key = (target: Element, key: string) => target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));

describe("the Business mark menu", () => {
  test("owner invite reuses access navigation and member identity is separate from the Business", async () => {
    const page = await mountSwitcher([OWN, CLIENT], OWN, false, [], true);
    await page.act(async () => (page.host.querySelector("button[aria-haspopup=menu]") as HTMLButtonElement).click());
    assert.equal(document.querySelector('[data-testid="business-member-email"]')?.textContent, "member@example.test");
    assert.equal(document.querySelector('[data-testid="business-member-access"]')?.textContent, "Tu acceso · Dueño");
    assert.equal(document.querySelector('[data-testid="business-member-access"]')?.parentElement, document.querySelector('[data-testid="business-member-email"]')?.parentElement);
    const items = [...document.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')];
    assert.deepEqual(items.map(item => item.textContent?.trim()), ["Invitar colaborador", "Configurar", "Añadir negocio", "Cambiar de negocio"]);
    assert.equal(items[2].disabled, true, "creation is not connected by this design preview");
    await page.act(async () => items[0].click());
    assert.deepEqual(page.opened, ["access"]);
    assert.equal(document.querySelector('[role="menu"]'), null);
    await page.act(async () => page.root.unmount());
    const client = await mountSwitcher([CLIENT], CLIENT, false, [], true);
    await client.act(async () => (client.host.querySelector("button[aria-haspopup=menu]") as HTMLButtonElement).click());
    assert.ok(!document.querySelector('[role="menu"]')?.textContent?.includes("Invitar colaborador"));
    await client.act(async () => client.root.unmount());
  });

  test("the English default is Spanish in the collapsed label and open options", async () => {
    const unnamed = { ...CLIENT, name: "My business" };
    const page = await mountSwitcher([OWN, unnamed], unnamed, true);
    const button = page.host.querySelector("button[aria-haspopup=menu]") as HTMLButtonElement;
    assert.equal(page.host.querySelector('[data-testid="business-current-name"]')?.textContent, "Mi negocio");
    assert.ok(button.getAttribute("aria-label")?.includes("Mi negocio"));
    await page.act(async () => button.click());
    await page.settle();
    const change = [...document.querySelectorAll('[role="menuitem"]')].find((item) => item.textContent?.includes("Cambiar de negocio")) as HTMLButtonElement;
    await page.act(async () => change.click());
    await page.settle();
    assert.ok([...document.querySelectorAll('[role="option"]')][1].textContent?.includes("Mi negocio"));
    assert.ok(!document.body.textContent?.includes("My business"));
    assert.equal(unnamed.name, "My business");
    await page.act(async () => page.root.unmount());
  });

  test("with only the own Business the menu offers Configurar negocio and does not offer a switch", async () => {
    const page = await mountSwitcher([OWN], OWN);
    const control = page.host.querySelector('[data-testid="business-switcher"]')!;
    assert.equal(control.getAttribute("data-switchable"), "false");
    assert.equal(page.host.querySelector('[data-testid="business-current-name"]')?.textContent, "Ferretería Luna");
    const button = page.host.querySelector("button[aria-haspopup=menu]") as HTMLButtonElement;
    assert.ok(button);
    assert.ok(!control.textContent?.includes("Tu negocio"));
    await page.act(async () => button.click());
    await page.settle();
    const items = [...document.querySelectorAll('[role="menuitem"]')];
    assert.deepEqual(items.map((item) => item.textContent?.trim()), ["Configurar", "Añadir negocio"]);
    await page.act(async () => (items[0] as HTMLButtonElement).click());
    assert.deepEqual(page.opened, ["settings"]);
    assert.equal(document.querySelector('[role="menu"]'), null, "the menu closes as the Negocio page opens");
    await page.act(async () => page.root.unmount());
  });

  test("with only a client Business the menu offers Configurar negocio and does not offer a switch", async () => {
    const page = await mountSwitcher([CLIENT], null);
    const control = page.host.querySelector('[data-testid="business-switcher"]')!;
    assert.equal(control.getAttribute("data-switchable"), "false");
    assert.equal(page.host.querySelector('[data-testid="business-current-name"]')?.textContent, "Colmado Peña");
    const button = page.host.querySelector("button[aria-haspopup=menu]") as HTMLButtonElement;
    await page.act(async () => button.click());
    await page.settle();
    const items = [...document.querySelectorAll('[role="menuitem"]')];
    assert.deepEqual(items.map((item) => item.textContent?.trim()), ["Configurar", "Añadir negocio"]);
    await page.act(async () => page.root.unmount());
  });

  test("the header names the business without a role and keeps the briefcase when collapsed", async () => {
    const owner = await mountSwitcher([OWN, CLIENT], OWN);
    assert.equal(owner.host.querySelector("button[aria-haspopup=menu]")?.textContent, "Ferretería Luna");
    await owner.act(async () => owner.root.unmount());
    const client = await mountSwitcher([OWN, CLIENT], CLIENT);
    assert.equal(client.host.querySelector("button[aria-haspopup=menu]")?.textContent, "Colmado Peña");
    assert.ok(!client.host.textContent?.includes("Dueño"));
    await client.act(async () => client.root.unmount());
    const collapsed = await mountSwitcher([OWN], OWN, true);
    assert.ok(collapsed.host.querySelector("svg.lucide-briefcase-business"));
    assert.ok(!collapsed.host.textContent?.includes("Dueño"), "the collapsed rail shows no role line");
    await collapsed.act(async () => collapsed.root.unmount());
  });

  test("with a client Business the menu opens the list the keyboard drives", async () => {
    const page = await mountSwitcher([OWN, CLIENT, OTHER], CLIENT);
    const button = page.host.querySelector("button[aria-haspopup=menu]") as HTMLButtonElement;
    assert.ok(button, "a switch button");
    assert.equal(page.host.querySelector('[data-testid="business-current-name"]')?.textContent, "Colmado Peña");
    assert.equal(button.getAttribute("aria-expanded"), "false");
    assert.ok(button.getAttribute("aria-label")?.includes("Colmado Peña"));
    await page.act(async () => { button.click(); });
    await page.settle();
    const change = [...document.querySelectorAll('[role="menuitem"]')].find((item) => item.textContent?.includes("Cambiar de negocio")) as HTMLButtonElement;
    await page.act(async () => change.click());
    await page.settle();
    let list = document.querySelector('[role="listbox"]') as HTMLElement;
    assert.ok(list, "the listbox opened");
    assert.ok(document.querySelector('[data-testid="business-member-email"]'), "desktop parent identity remains visible");
    assert.ok(change.isConnected, "the parent switch action remains in place");
    assert.equal(document.activeElement, list, "focus moves into the list");
    await page.act(async () => key(list, "ArrowLeft"));
    assert.equal(document.activeElement, change, "Left returns focus to the parent action");
    await page.act(async () => key(change, "ArrowRight"));
    assert.ok(document.querySelector('[role="listbox"]'), "Right opens the submenu");
    list = document.querySelector('[role="listbox"]') as HTMLElement;

    const options = [...document.querySelectorAll('[role="option"]')];
    assert.deepEqual(options.map((o) => o.getAttribute("aria-selected")), ["false", "true", "false"]);
    assert.ok(options[0].textContent?.includes("Ferretería Luna"));
    assert.equal(options.some((option) => option.textContent?.includes("Tu negocio")), false);
    // Arrow down from the active (second) to the third, Home to the first, Enter chooses the own Business grant.
    await page.act(async () => { key(list, "ArrowDown"); });
    assert.equal(options[2].getAttribute("data-active"), "true");
    await page.act(async () => { key(list, "Home"); });
    assert.equal(options[0].getAttribute("data-active"), "true");
    await page.act(async () => { key(list, "Enter"); });
    await page.settle();
    assert.deepEqual(page.chosenIds, [OWN.grant_id]);
    assert.equal(document.querySelector('[role="listbox"]'), null, "closed after choosing");
    assert.equal(document.activeElement, button, "focus returns to the button");
    // Open again, type-ahead to Taller, Escape closes without choosing.
    await page.act(async () => { button.click(); });
    await page.settle();
    const changeAgain = [...document.querySelectorAll('[role="menuitem"]')].find((item) => item.textContent?.includes("Cambiar de negocio")) as HTMLButtonElement;
    await page.act(async () => changeAgain.click());
    await page.settle();
    const again = document.querySelector('[role="listbox"]') as HTMLElement;
    await page.act(async () => { key(again, "t"); });
    assert.equal([...document.querySelectorAll('[role="option"]')][2].getAttribute("data-active"), "true");
    await page.act(async () => { key(again, "Escape"); });
    assert.equal(document.querySelector('[role="listbox"]'), null);
    assert.deepEqual(page.chosenIds, [OWN.grant_id]);
    assert.ok(document.querySelector('[role="menu"]'), "Escape closes the submenu first");
    assert.equal(document.activeElement, changeAgain);
    await page.act(async () => { key(changeAgain, "Escape"); });
    assert.equal(document.querySelector('[role="menu"]'), null);
    await page.act(async () => page.root.unmount());
  });

  test("a click on a client row chooses its grant; collapsed, the name stays readable to assistive tech", async () => {
    const page = await mountSwitcher([OWN, CLIENT], OWN, true);
    assert.equal(page.host.querySelector('[data-testid="business-current-name"]')?.textContent, "Ferretería Luna");
    const button = page.host.querySelector("button[aria-haspopup=menu]") as HTMLButtonElement;
    await page.act(async () => { button.click(); });
    await page.settle();
    const change = [...document.querySelectorAll('[role="menuitem"]')].find((item) => item.textContent?.includes("Cambiar de negocio")) as HTMLButtonElement;
    await page.act(async () => change.click());
    await page.settle();
    const client = [...document.querySelectorAll('[role="option"]')][1] as HTMLElement;
    await page.act(async () => { client.click(); });
    assert.deepEqual(page.chosenIds, ["g-client"]);
    await page.act(async () => page.root.unmount());
  });
});

describe("inside a client's Business every screen says so", () => {
  async function mountCue(chosen: GrantedSpace | null, lostAccess = false) {
    const env = await setup();
    const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
    const { BusinessContextCue } = await import("@/components/business-app/BusinessPanel");
    const seen: string[] = [];
    let setChosenOutside: (next: GrantedSpace | null) => void = () => undefined;
    const { useState } = await import("react");
    function Harness() {
      const [current, setCurrent] = useState(chosen);
      setChosenOutside = setCurrent;
      const value = {
        chosen: current,
        lostAccess,
        clearLostAccess: () => undefined,
        markAccessSeen: async () => { seen.push(current?.grant_id ?? ""); setCurrent(current ? { ...current, access_seen: true } : current); },
      } as unknown as BusinessContextValue;
      return (
        <env.I18nextProvider i18n={env.i18n}>
          <BusinessContext.Provider value={value}>
            <BusinessContextCue />
          </BusinessContext.Provider>
        </env.I18nextProvider>
      );
    }
    await env.act(async () => { env.root.render(<Harness />); });
    await env.settle();
    return { ...env, seen, setChosen: (next: GrantedSpace | null) => env.act(async () => setChosenOutside(next)) };
  }

  test("the client cue and the one-time line show on first landing; Entendido records it once and it never returns; the owner sees neither", async () => {
    const page = await mountCue(CLIENT);
    assert.equal(page.host.querySelector('[data-testid="business-client-cue"]')?.textContent, "Cliente: Colmado Peña");
    const line = page.host.querySelector('[data-testid="business-access-line"]')!;
    assert.equal(line.getAttribute("role"), "status");
    assert.ok(line.textContent?.includes("Ahora tienes acceso a Colmado Peña · Ver y preparar"));
    const got = line.querySelector("button") as HTMLButtonElement;
    assert.equal(got.textContent, "Entendido");
    await page.act(async () => { got.click(); });
    await page.settle();
    assert.deepEqual(page.seen, ["g-client"]);
    assert.equal(page.host.querySelector('[data-testid="business-access-line"]'), null, "dismissed");
    assert.ok(page.host.querySelector('[data-testid="business-client-cue"]'), "the cue stays");
    // Another client whose line was already seen: cue only.
    await page.setChosen(OTHER);
    assert.equal(page.host.querySelector('[data-testid="business-client-cue"]')?.textContent, "Cliente: Taller Brito");
    assert.equal(page.host.querySelector('[data-testid="business-access-line"]'), null);
    // The own Business: nothing at all.
    await page.setChosen(OWN);
    assert.equal(page.host.querySelector('[data-testid="business-client-cue"]'), null);
    assert.equal(page.host.querySelector('[data-testid="business-access-line"]'), null);
    await page.act(async () => page.root.unmount());
  });

  test("the client cue and access banner localize the saved English default", async () => {
    const page = await mountCue({ ...CLIENT, name: "My business" });
    assert.equal(page.host.querySelector('[data-testid="business-client-cue"]')?.textContent, "Cliente: Mi negocio");
    assert.ok(page.host.querySelector('[data-testid="business-access-line"]')?.textContent?.includes("Ahora tienes acceso a Mi negocio"));
    assert.ok(!page.host.textContent?.includes("My business"));
    await page.act(async () => page.root.unmount());
  });

  test("a grant that died mid-session says so once, in the own Business", async () => {
    const page = await mountCue(OWN, true);
    assert.equal(page.host.querySelector("h1")?.textContent, "No tienes acceso a este negocio.");
    assert.equal(page.host.querySelector("button")?.textContent, "Ir a mis negocios");
    assert.equal(page.host.querySelector('[data-testid="business-client-cue"]'), null);
    await page.act(async () => page.root.unmount());
  });
});

describe("the chosen grant rides on every API call", () => {
  test("the header is present only while a grant is chosen, and the memory survives a re-read", async () => {
    const { getChosenGrant, setChosenGrant, GRANT_HEADER, chosenGrantHeader } = await import("@/lib/business-grant");
    const { argusApiRequestHeaders } = await import("@/lib/argus-api-transport");
    setChosenGrant(null);
    assert.equal(argusApiRequestHeaders(undefined, {}).get(GRANT_HEADER), null);
    setChosenGrant("4b2a1f0e-9c3d-4e5f-8a7b-6c5d4e3f2a1b");
    assert.equal(getChosenGrant(), "4b2a1f0e-9c3d-4e5f-8a7b-6c5d4e3f2a1b");
    assert.deepEqual(chosenGrantHeader(), { [GRANT_HEADER]: "4b2a1f0e-9c3d-4e5f-8a7b-6c5d4e3f2a1b" });
    assert.equal(argusApiRequestHeaders({ "Idempotency-Key": "k" }, {}).get(GRANT_HEADER), "4b2a1f0e-9c3d-4e5f-8a7b-6c5d4e3f2a1b");
    // Only Business calls carry it: Personal chat and the rest never see the chosen grant.
    assert.equal(argusApiRequestHeaders(undefined, {}, "/business/receipts?view=inbox").get(GRANT_HEADER), "4b2a1f0e-9c3d-4e5f-8a7b-6c5d4e3f2a1b");
    assert.equal(argusApiRequestHeaders(undefined, {}, "/conversations?surface=business").get(GRANT_HEADER), "4b2a1f0e-9c3d-4e5f-8a7b-6c5d4e3f2a1b");
    for (const path of ["/conversations/c1/messages", "/conversations?surface=personal", "/conversations", "/chat/stream", "/backtests/run", "/me"]) {
      assert.equal(argusApiRequestHeaders(undefined, {}, path).get(GRANT_HEADER), null, path);
    }
    setChosenGrant(null);
    assert.equal(argusApiRequestHeaders(undefined, {}).get(GRANT_HEADER), null);
  });
});


for (const [capabilities, label] of [[["read", "prepare"], "Editar"], [["read"], "Ver"]] as const) {
  test(`member header omits the ${label} role subtitle`, async () => {
    const member = { ...CLIENT, capabilities: [...capabilities] };
    const page = await mountSwitcher([member], member);
    try { assert.ok(!page.host.textContent?.includes(label)); assert.equal(page.host.textContent?.includes("Contador"), false); }
    finally { await page.act(async () => page.root.unmount()); }
  });
}

test("closed owner Businesses link to recovery and never join live switch options", async () => {
  const closed = { space_id: "closed-business", name: "Taller Cerrado", grant_id: "closed-grant", role: "owner" as const, closed_at: "2026-10-21T17:45:00Z", reopen_until: "2026-11-20T17:45:00Z" };
  const page = await mountSwitcher([OWN], OWN, false, [closed]);
  try {
    await page.act(async () => page.host.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]')!.click());
    assert.ok(document.body.textContent?.includes("Cerrados"));
    const link = document.querySelector<HTMLAnchorElement>('a[href="/biz?lifecycle=manage&business=closed-business"]'); assert.ok(link);
    assert.ok(link.textContent?.includes("Taller Cerrado"));
    assert.equal(document.querySelector('[role="option"]'), null);
    assert.deepEqual(page.chosenIds, []);
  } finally { await page.act(async () => page.root.unmount()); }
});
