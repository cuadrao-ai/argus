import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { GrantedSpace } from "@/lib/business-api";
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

const OWN: GrantedSpace = { space_id: "s-own", name: "Ferretería Luna", grant_id: "g-own", role: "owner", capabilities: ["read", "prepare", "approve"], access_seen: true };
const CLIENT: GrantedSpace = { space_id: "s-client", name: "Colmado Peña", grant_id: "g-client", role: "accountant", capabilities: ["read", "prepare"], access_seen: false };
const OTHER: GrantedSpace = { space_id: "s-other", name: "Taller Brito", grant_id: "g-other", role: "accountant", capabilities: ["read", "prepare"], access_seen: true };

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

async function mountSwitcher(spaces: GrantedSpace[] | null, chosen: GrantedSpace | null, collapsed = false) {
  const env = await setup();
  const { default: BusinessSwitcher } = await import("@/components/business-app/BusinessSwitcher");
  const chosenIds: (string | null)[] = [];
  await env.act(async () => {
    env.root.render(
      <env.I18nextProvider i18n={env.i18n}>
        <BusinessSwitcher spaces={spaces} chosen={chosen} collapsed={collapsed} onChoose={(id) => chosenIds.push(id)} />
      </env.I18nextProvider>,
    );
  });
  await env.settle();
  return { ...env, chosenIds };
}

const key = (target: Element, key: string) => target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));

describe("the Business switcher at the top left", () => {
  test("the English default is Spanish in the collapsed label and open options", async () => {
    const unnamed = { ...CLIENT, name: "My business" };
    const page = await mountSwitcher([OWN, unnamed], unnamed, true);
    const button = page.host.querySelector("button[aria-haspopup=listbox]") as HTMLButtonElement;
    assert.equal(page.host.querySelector('[data-testid="business-current-name"]')?.textContent, "Mi negocio");
    assert.ok(button.getAttribute("aria-label")?.includes("Mi negocio"));
    assert.ok(button.getAttribute("title")?.includes("Mi negocio"));
    await page.act(async () => button.click());
    assert.ok([...document.querySelectorAll('[role="option"]')][1].textContent?.includes("Mi negocio"));
    assert.ok(!page.host.textContent?.includes("My business"));
    assert.equal(unnamed.name, "My business");
    await page.act(async () => page.root.unmount());
  });

  test("with only the own Business it is a plain label naming it; nothing opens", async () => {
    const page = await mountSwitcher([OWN], OWN);
    const control = page.host.querySelector('[data-testid="business-switcher"]')!;
    assert.equal(control.getAttribute("data-switchable"), "false");
    assert.equal(page.host.querySelector('[data-testid="business-current-name"]')?.textContent, "Ferretería Luna");
    assert.equal(page.host.querySelector("button"), null);
    assert.ok(control.textContent?.includes("Tu negocio"));
    await page.act(async () => page.root.unmount());
  });

  test("with a client Business it is a button that names the active one and opens a listbox the keyboard drives", async () => {
    const page = await mountSwitcher([OWN, CLIENT, OTHER], CLIENT);
    const button = page.host.querySelector("button[aria-haspopup=listbox]") as HTMLButtonElement;
    assert.ok(button, "a switch button");
    assert.equal(page.host.querySelector('[data-testid="business-current-name"]')?.textContent, "Colmado Peña");
    assert.equal(button.getAttribute("aria-expanded"), "false");
    assert.ok(button.getAttribute("aria-label")?.includes("Cambiar de negocio"));
    await page.act(async () => { button.click(); });
    await page.settle();
    const list = document.querySelector('[role="listbox"]') as HTMLElement;
    assert.ok(list, "the listbox opened");
    assert.equal(document.activeElement, list, "focus moves into the list");
    const options = [...document.querySelectorAll('[role="option"]')];
    assert.deepEqual(options.map((o) => o.getAttribute("aria-selected")), ["false", "true", "false"]);
    assert.ok(options[0].textContent?.includes("Ferretería Luna") && options[0].textContent?.includes("Tu negocio"));
    assert.ok(options[2].textContent?.includes("Cliente · Ver y preparar"));
    // Arrow down from the active (second) to the third, Home to the first, Enter chooses the own Business (null).
    await page.act(async () => { key(list, "ArrowDown"); });
    assert.equal(options[2].getAttribute("data-active"), "true");
    await page.act(async () => { key(list, "Home"); });
    assert.equal(options[0].getAttribute("data-active"), "true");
    await page.act(async () => { key(list, "Enter"); });
    await page.settle();
    assert.deepEqual(page.chosenIds, [null]);
    assert.equal(document.querySelector('[role="listbox"]'), null, "closed after choosing");
    assert.equal(document.activeElement, button, "focus returns to the button");
    // Open again, type-ahead to Taller, Escape closes without choosing.
    await page.act(async () => { button.click(); });
    await page.settle();
    const again = document.querySelector('[role="listbox"]') as HTMLElement;
    await page.act(async () => { key(again, "t"); });
    assert.equal([...document.querySelectorAll('[role="option"]')][2].getAttribute("data-active"), "true");
    await page.act(async () => { key(again, "Escape"); });
    assert.equal(document.querySelector('[role="listbox"]'), null);
    assert.deepEqual(page.chosenIds, [null]);
    await page.act(async () => page.root.unmount());
  });

  test("a click on a client row chooses its grant; collapsed, the name stays readable to assistive tech", async () => {
    const page = await mountSwitcher([OWN, CLIENT], OWN, true);
    assert.equal(page.host.querySelector('[data-testid="business-current-name"]')?.textContent, "Ferretería Luna");
    const button = page.host.querySelector("button[aria-haspopup=listbox]") as HTMLButtonElement;
    await page.act(async () => { button.click(); });
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
    assert.equal(page.host.querySelector('[data-testid="business-access-lost"]')?.textContent, "Ya no tienes acceso a este negocio.");
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
