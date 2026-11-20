import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import type { ReactNode } from "react";
import { ChatWorkspaceProvider, type ChatWorkspace } from "@/components/chat/ChatWorkspace";
import spanish from "@/public/locales/es-419/common.json";

const copy = spanish.settings.profile.request_deletion;
const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
const cleanups: (() => Promise<void>)[] = [];
const NAMES = ["Cafetería Malecón", "Colmado La Esquina", "Farmacia San Rafael", "Ferretería Los Pinos", "Panadería El Trigal", "Repuestos del Cibao", "Salón Brisa", "Taller Hermanos Peña"];
const owned = (count: number) => NAMES.slice(0, count).map((name, index) => ({ kind: "business_owner", business_id: `00000000-0000-4000-8000-00000000000${index}`, business_name: name }));
const ALLOWED = { allowed: true, blockers: [], notices: [] };
const IN_PROGRESS = () => Response.json({ status: "in_progress", pending: ["apple"] }, { status: 202 });
let answer: unknown = ALLOWED;
let deletionReply: () => Response = IN_PROGRESS;
let feedbackReply: () => Response = () => Response.json({ success: true });
let calls: { path: string; method: string }[] = [];

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = (async (input: unknown, init?: RequestInit) => {
    const path = new URL(String(input), "http://localhost").pathname;
    const method = init?.method ?? "GET";
    calls.push({ path, method });
    if (path.endsWith("/account/deletion")) return Response.json(answer);
    if (path.endsWith("/account/deletion/request")) return Response.json({ status: "requested" });
    if (path.endsWith("/account/delete")) return deletionReply();
    if (path.endsWith("/feedback")) return feedbackReply();
    if (path.endsWith("/business/owned-spaces")) {
      return Response.json({ spaces: owned(3).map((business, index) => ({ space_id: business.business_id, name: business.business_name, grant_id: `10000000-0000-4000-8000-00000000000${index}`, member_count: 0, reopen_until: "2026-12-20T17:45:00Z", export_windows: [], members: [] })) });
    }
    return Response.json({ user: { id: "cuenta-owner", display_name: "Ana Morel", email: "ana@example.test", language: "es-419" }, account_kind: "registered", available: false });
  }) as typeof fetch;
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
  answer = ALLOWED;
  deletionReply = IN_PROGRESS;
  feedbackReply = () => Response.json({ success: true });
  calls = [];
  window.happyDOM.setWindowSize({ width: 1024, height: 768 });
});
afterAll(async () => {
  globalThis.fetch = originalFetch;
  (await import("@/lib/business-grant")).setChosenGrant(null);
  if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  await GlobalRegistrator.unregister();
});

async function mount(content: ReactNode) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18n = createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><ChatWorkspaceProvider value={{ conversationSurface: "business" } as ChatWorkspace}>{content}</ChatWorkspaceProvider></I18nextProvider>));
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  cleanups.push(() => act(async () => root.unmount()));
  return act;
}

const buttons = (text: string) => [...document.body.querySelectorAll("button")].filter((item) => item.textContent?.trim() === text);
const button = (text: string) => buttons(text)[0];
const text = () => document.body.textContent ?? "";
const settle = (act: (callback: () => Promise<void>) => Promise<void>) => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

/** Ajustes with only Cuenta, as a Business owner opens it, over the server answer set above. */
async function openCuenta({ lifecycleControls = false, onLeave = (href: string) => void href, onLogout = () => undefined, onAccountDeleted = () => undefined } = {}) {
  const { default: SettingsWindow } = await import("@/components/settings/SettingsWindow");
  const { default: AccountSettings } = await import("@/components/settings/AccountSettings");
  return mount(
    <SettingsWindow
      sections={["account"]}
      renderSection={() => (
        <AccountSettings
          profile={null}
          avatar={{ className: "", style: undefined }}
          profileLanguage="es-419"
          lifecycleControls={lifecycleControls}
          onLogout={onLogout}
          onLeave={onLeave}
          onAccountDeleted={onAccountDeleted}
          onClose={() => undefined}
        />
      )}
      legalLinks={[]}
      returnFocusRef={{ current: null }}
      onClose={() => undefined}
    />,
  );
}

const ownedRows = () => [...document.querySelectorAll<HTMLAnchorElement>('[data-testid="account-owned-business"]')];

test("clear: the server's yes shows the one-line note beside an enabled Eliminar cuenta", async () => {
  await openCuenta();
  assert.equal(calls.filter((call) => call.path.endsWith("/account/deletion")).length, 1, "Cuenta asks the server as it opens");
  assert.ok(text().includes(spanish.settings.profile.delete_account_note));
  const remove = button(copy.confirm);
  assert.ok(remove && !remove.disabled);
  assert.equal(document.querySelector('[data-testid="account-deletion-pending"]'), null);
  assert.equal(text().includes("Zona de peligro"), false);
  const security = document.querySelector<HTMLAnchorElement>('a[href="/account/security"]');
  assert.ok(security?.textContent?.includes(spanish.settings.data.security), "the whole Seguridad row is the link");
});

for (const count of [1, 3, 8]) {
  test(`blocked by ${count}: the counter, one line and the owned rows, with no Eliminar cuenta button`, async () => {
    answer = { allowed: false, blockers: owned(count), notices: [] };
    await openCuenta({ lifecycleControls: true });
    const pending = document.querySelector('[data-testid="account-deletion-pending"]')?.textContent ?? "";
    assert.ok(pending.includes(count === 1 ? "1 negocio por resolver" : `${count} negocios por resolver`), pending);
    assert.ok(text().includes(copy.business_owner));
    assert.equal(buttons(copy.confirm).length, 0, "never a disabled delete button while blocked");
    assert.equal(text().includes(spanish.settings.profile.delete_account_note), false);
    assert.equal(ownedRows().length, Math.min(count, 3));
    assert.equal(Boolean(button(`Ver los ${count} negocios`)), count > 3);
    assert.equal(button(copy.request_support), undefined, "transfer and close exist, so no support request");
  });
}

test("the disclosure opens every owned Business in place and closes again", async () => {
  answer = { allowed: false, blockers: owned(8), notices: [] };
  const act = await openCuenta({ lifecycleControls: true });
  const more = button("Ver los 8 negocios")!;
  assert.equal(more.getAttribute("aria-expanded"), "false");
  assert.equal(document.getElementById(more.getAttribute("aria-controls")!)?.tagName, "UL");
  await act(async () => more.click());
  assert.equal(ownedRows().length, 8);
  assert.deepEqual(ownedRows().map((row) => row.textContent), NAMES, "in the server's order");
  const less = button("Ver menos")!;
  assert.equal(less.getAttribute("aria-expanded"), "true");
  await act(async () => less.click());
  assert.equal(ownedRows().length, 3);
  assert.equal(calls.filter((call) => call.path.endsWith("/account/deletion")).length, 1, "opening the list asks nothing");
});

test("an owned row selects that Business, then leaves for its Negocio settings", async () => {
  answer = { allowed: false, blockers: owned(3), notices: [] };
  const left: string[] = [];
  const act = await openCuenta({ lifecycleControls: true, onLeave: (href) => left.push(href) });
  const row = ownedRows()[1];
  assert.equal(row.getAttribute("href"), "/biz?view=business&tab=datos");
  await act(async () => row.click());
  await settle(act);
  const { getChosenGrant } = await import("@/lib/business-grant");
  assert.equal(getChosenGrant(), "10000000-0000-4000-8000-000000000001");
  assert.deepEqual(left, ["/biz?view=business&tab=datos"]);
});

test("lifecycle off: Solicitar eliminación files the support request and says so in its place", async () => {
  answer = { allowed: false, blockers: owned(3), notices: [] };
  const act = await openCuenta({ lifecycleControls: false });
  assert.equal(buttons(copy.confirm).length, 0);
  await act(async () => button(copy.request_support)!.click());
  await settle(act);
  assert.deepEqual(calls.filter((call) => call.path.endsWith("/account/deletion/request")).map((call) => call.method), ["POST"]);
  assert.equal(calls.some((call) => call.path.endsWith("/account/delete")), false, "nothing is deleted");
  assert.equal(button(copy.request_support), undefined);
  assert.ok(text().includes(copy.requested));
});

test("confirmation: in the pane, Cancelar has focus, and both buttons share one size", async () => {
  const act = await openCuenta();
  await act(async () => button(copy.confirm)!.click());
  assert.equal(document.querySelector('[role="dialog"][aria-modal="true"] [role="dialog"]'), null, "no alert over the window");
  assert.ok(text().includes(copy.body));
  assert.ok(text().includes(copy.signs_out_now));
  assert.ok(text().includes(copy.finishes_later));
  assert.equal(text().includes("correo"), false, "no email promise");
  assert.equal(document.querySelector("input"), null, "no typed confirmation");
  const cancel = button(spanish.common.cancel)!;
  assert.equal(document.activeElement, cancel);
  const pair = cancel.parentElement!;
  assert.match(pair.className, /grid-cols-2/);
  assert.equal(pair.children.length, 2);
  assert.ok(document.querySelector('[data-testid="settings-window-back"]'), "the header has the arrow back");
  await act(async () => cancel.click());
  assert.ok(text().includes(spanish.settings.profile.delete_account_note), "Cancelar returns to Cuenta");
  assert.equal(document.activeElement, button(copy.confirm));
});

test("confirming runs the existing deletion and keeps its in-progress answer", async () => {
  let deleted = 0;
  const act = await openCuenta({ onAccountDeleted: () => { deleted += 1; } });
  await act(async () => button(copy.confirm)!.click());
  await act(async () => buttons(copy.confirm).at(-1)!.click());
  await settle(act);
  assert.deepEqual(calls.filter((call) => call.path.endsWith("/account/delete")).map((call) => call.method), ["POST"]);
  assert.equal(deleted, 1, "the session ends on the result");
  assert.ok(text().includes(copy.in_progress));
  assert.equal(document.querySelector('[data-testid="settings-window-back"]'), null, "nothing to go back to");
  assert.equal(button(spanish.common.cancel), undefined);
});

test("Ajustes lists one Cuenta section; Cerrar sesión signs out and closing after a deletion only cleans up", async () => {
  const { default: ProfileMenu } = await import("@/components/sidebar/ProfileMenu");
  const anchor = document.createElement("button");
  document.body.appendChild(anchor);
  const logouts: unknown[] = [];
  const act = await mount(<ProfileMenu isOpen onClose={() => {}} onLogout={(options) => logouts.push(options)} anchorRef={{ current: anchor }} />);
  await act(async () => button("Ajustes")!.click());
  await settle(act);
  assert.equal(document.querySelector('[data-testid="settings-nav-security"]'), null);
  assert.equal(document.querySelector('[data-testid="settings-nav-delete-account"]'), null);
  assert.equal(calls.filter((call) => call.path.endsWith("/account/deletion")).length, 0, "nothing is read before Cuenta opens");
  await act(async () => document.querySelector<HTMLButtonElement>('[data-testid="settings-nav-account"]')!.click());
  await settle(act);
  assert.equal(calls.filter((call) => call.path.endsWith("/account/deletion")).length, 1);

  await act(async () => button(copy.confirm)!.click());
  await act(async () => buttons(copy.confirm).at(-1)!.click());
  await settle(act);
  assert.deepEqual(logouts, [{ afterAccountDeletion: true }]);
  await act(async () => document.querySelector<HTMLButtonElement>('[data-testid="settings-window-close"]')!.click());
  assert.deepEqual(logouts, [{ afterAccountDeletion: true }, { sessionEnded: true }]);
});

test("Cerrar sesión in Cuenta is the existing sign-out", async () => {
  const { default: ProfileMenu } = await import("@/components/sidebar/ProfileMenu");
  const anchor = document.createElement("button");
  document.body.appendChild(anchor);
  const logouts: unknown[] = [];
  const act = await mount(<ProfileMenu isOpen onClose={() => {}} onLogout={(options) => logouts.push(options)} anchorRef={{ current: anchor }} />);
  await act(async () => button("Ajustes")!.click());
  await act(async () => document.querySelector<HTMLButtonElement>('[data-testid="settings-nav-account"]')!.click());
  await settle(act);
  assert.ok(text().includes("Ana Morel") && text().includes("ana@example.test"));
  await act(async () => button(spanish.settings.logout)!.click());
  assert.deepEqual(logouts, [undefined]);
  assert.equal(document.querySelector('[data-testid="settings-window"]'), null, "Ajustes closes as it signs out");
});

test("a check that could not run shows its reference and Reintentar, never Eliminar cuenta", async () => {
  const { default: AccountSettings } = await import("@/components/settings/AccountSettings");
  answer = { allowed: false, blockers: owned(1), notices: [] };
  const serverFetch = globalThis.fetch;
  cleanups.push(async () => { globalThis.fetch = serverFetch; });
  globalThis.fetch = ((original) => (async (input: unknown, init?: RequestInit) => {
    if (String(input).endsWith("/account/deletion") && calls.length === 0) {
      calls.push({ path: "/account/deletion", method: "GET" });
      return Response.json({ code: "account_deletion_unavailable", detail: "unavailable" }, { status: 503, headers: { "X-Request-Id": "ref-503-cuenta" } });
    }
    return original(input as RequestInfo, init);
  }) as typeof fetch)(globalThis.fetch);
  const act = await mount(<AccountSettings profile={null} avatar={{ className: "", style: undefined }} profileLanguage="es-419" lifecycleControls onLogout={() => undefined} onLeave={() => undefined} onAccountDeleted={() => undefined} onClose={() => undefined} />);
  assert.ok(text().includes(spanish.business.lifecycle.deletion.failed));
  assert.ok(text().includes("ref-503-cuenta"));
  assert.equal(buttons(copy.confirm).length, 0);
  await act(async () => button(spanish.common.retry)!.click());
  await settle(act);
  assert.ok(text().includes("1 negocio por resolver"));
});

test("a closed Business inside its reopen window is a warning in the confirmation, never a block", async () => {
  answer = { allowed: true, blockers: [], notices: [{ kind: "closed_business", business_id: "00000000-0000-4000-8000-0000000000aa", business_name: "Colmado Rosa", purge_at: "2026-11-20T17:45:00Z" }] };
  const act = await openCuenta();
  await act(async () => button(copy.confirm)!.click());
  assert.ok(text().includes("Colmado Rosa está cerrado. Si borras tu cuenta, nadie podrá reabrirlo"));
  assert.ok(text().includes("hora de RD"));
  assert.equal(buttons(copy.confirm).at(-1)!.disabled, false);
});

const REPLIES = {
  success: { reply: () => Response.json({ status: "deleted" }), copy: copy.success, logouts: [{ afterAccountDeletion: true }], closed: [{ afterAccountDeletion: true }, { sessionEnded: true }] },
  in_progress: { reply: IN_PROGRESS, copy: copy.in_progress, logouts: [{ afterAccountDeletion: true }], closed: [{ afterAccountDeletion: true }, { sessionEnded: true }] },
  requested: { reply: () => Response.json({ code: "not_found", detail: "off" }, { status: 404 }), copy: copy.requested, logouts: [], closed: [] },
} as const;

for (const width of [390, 800, 1280]) {
  for (const [outcome, expected] of Object.entries(REPLIES)) {
    for (const exit of ["close", "Escape"] as const) {
      test(`${width}px, ${outcome}: the answer holds Ajustes and ${exit} runs the window's cleanup once`, async () => {
        window.happyDOM.setWindowSize({ width, height: 844 });
        deletionReply = expected.reply;
        const { default: ProfileMenu } = await import("@/components/sidebar/ProfileMenu");
        const anchor = document.createElement("button");
        document.body.appendChild(anchor);
        const logouts: unknown[] = [];
        const act = await mount(<ProfileMenu isOpen onClose={() => {}} onLogout={(options) => logouts.push(options)} anchorRef={{ current: anchor }} />);
        await act(async () => button("Ajustes")!.click());
        await act(async () => document.querySelector<HTMLButtonElement>('[data-testid="settings-nav-account"]')!.click());
        await settle(act);
        await act(async () => button(copy.confirm)!.click());
        await act(async () => buttons(copy.confirm).at(-1)!.click());
        await settle(act);
        assert.ok(text().includes(expected.copy));
        assert.deepEqual(logouts, expected.logouts);

        const pane = () => document.querySelector<HTMLElement>('[data-testid="settings-pane-account"]');
        const surface = pane()!.closest<HTMLElement>('[role="dialog"]')!;
        assert.equal(surface.querySelector('[data-testid="settings-window-back"]'), null, "no arrow back into Ajustes");
        for (const row of document.querySelectorAll<HTMLButtonElement>("[data-settings-row]")) await act(async () => row.click());
        assert.ok(pane() && text().includes(expected.copy), "no section row replaces the answer");

        await act(async () => {
          if (exit === "close") surface.querySelector<HTMLButtonElement>('[data-testid="settings-window-close"]')!.click();
          else document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
        });
        assert.deepEqual(logouts, expected.closed, "the window's cleanup, once, with no second sign-out");
        if (outcome === "requested") assert.equal(document.querySelector('[data-testid="settings-window"]'), null, "Ajustes closes");
        else assert.ok(pane() && text().includes(expected.copy), "never back to the Ajustes list");
      });
    }
  }
}

const OFF_HERE = () => Response.json({ code: "not_found", detail: "off" }, { status: 404 });
const supportLinks = () => [...document.querySelectorAll<HTMLAnchorElement>('a[href^="mailto:"]')];

async function assertSupportLink() {
  const { supportEmail } = await import("@/lib/support-email");
  const { pillButtonClass } = await import("@/components/business-app/business-ui");
  const links = supportLinks();
  assert.equal(links.length, 1, "one way to write to support");
  assert.equal(links[0].textContent, copy.write_support);
  assert.equal(links[0].getAttribute("href"), `mailto:${supportEmail}?subject=${encodeURIComponent(copy.email_subject)}`);
  assert.equal(links[0].className.includes(pillButtonClass), false, "a link, never a pill");
}

test("unavailable: off here and the ticket failed, so the confirmation offers Escribir a soporte below its line", async () => {
  deletionReply = OFF_HERE;
  feedbackReply = () => Response.json({ detail: "down" }, { status: 500 });
  const act = await openCuenta();
  await act(async () => button(copy.confirm)!.click());
  await act(async () => buttons(copy.confirm).at(-1)!.click());
  await settle(act);
  const line = [...document.querySelectorAll('[role="alert"]')].find((node) => node.textContent === copy.unavailable);
  assert.ok(line, "the unavailable line stays");
  await assertSupportLink();
  assert.ok(line.compareDocumentPosition(supportLinks()[0]) & Node.DOCUMENT_POSITION_FOLLOWING, "the link sits below the line");
});

test("not allowed for another reason: Cuenta says support can delete it and links to support", async () => {
  answer = { allowed: false, blockers: [{ kind: "not_allowed" }], notices: [] };
  await openCuenta();
  assert.ok(text().includes(copy.unavailable));
  await assertSupportLink();
});

const NO_LINK: Record<string, { answer?: unknown; lifecycleControls?: boolean; reply?: () => Response; confirm?: boolean }> = {
  allowed: {},
  "owner-blocked, lifecycle on": { answer: { allowed: false, blockers: owned(2), notices: [] }, lifecycleControls: true },
  "owner-blocked, lifecycle off": { answer: { allowed: false, blockers: owned(2), notices: [] } },
  "allowed, confirming": { confirm: true },
  success: { confirm: true, reply: () => Response.json({ status: "deleted" }) },
  in_progress: { confirm: true, reply: IN_PROGRESS },
  requested: { confirm: true, reply: OFF_HERE },
  error: { confirm: true, reply: () => Response.json({ code: "account_deletion_unavailable", detail: "busy" }, { status: 503 }) },
};

for (const [name, path] of Object.entries(NO_LINK)) {
  test(`${name}: no support email link on a normal path`, async () => {
    if (path.answer) answer = path.answer;
    if (path.reply) deletionReply = path.reply;
    const act = await openCuenta({ lifecycleControls: path.lifecycleControls ?? false });
    if (path.confirm) {
      await act(async () => button(copy.confirm)!.click());
      assert.equal(supportLinks().length, 0, "not in the confirmation before it runs");
      await act(async () => buttons(copy.confirm).at(-1)!.click());
      await settle(act);
    }
    assert.equal(supportLinks().length, 0);
  });
}
