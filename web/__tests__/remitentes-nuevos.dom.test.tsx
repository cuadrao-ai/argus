import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { BusinessEmailDelivery } from "@/lib/business-email";
import type { BusinessEmailSenderChange } from "@/lib/business-api";

let cleanup = async () => {};
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1280, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => { await cleanup(); cleanup = async () => {}; document.body.innerHTML = ""; });
afterAll(async () => { await GlobalRegistrator.unregister(); });

const sender = (over: Partial<BusinessEmailDelivery> = {}): BusinessEmailDelivery => ({
  id: "mail-new",
  state: "received",
  received_at: "2026-10-30T12:00:00Z",
  updated_at: "2026-10-30T12:00:00Z",
  original_document_id: null,
  retryable: false,
  subject: "Factura nueva",
  sender: "nuevo@proveedor.example",
  sent_at: null,
  error_code: null,
  parts: [],
  standing: null,
  notice: "Aviso 7",
  ...over,
});

const notedReceipt = (reviewNote: string | null) => ({
  kind: "receipt" as const,
  id: "rcpt-1",
  receivedAt: "2026-10-13T17:14:00Z",
  source: "email" as const,
  sender: "ventas@example.test",
  reviewNote,
  receipt: {
    id: "rcpt-1",
    channel: "email" as const,
    filename: "factura-41.pdf",
    media_type: "application/pdf",
    size_bytes: 1200,
    received_at: "2026-10-13T17:14:00Z",
    status: "review_ready" as const,
    error_code: null,
    attention: null,
    preparable: false,
    enterable: true,
    expense_id: null,
    merchant: "Ferretería La Esquina",
    bandeja: { por_revisar: true, con_problema: false, leyendo: false },
    email_delivery_ids: ["mail-1"],
  },
});

async function spanish() {
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const es = (await import("@/public/locales/es-419/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: es } }, interpolation: { escapeValue: false } });
  return { i18n, I18nextProvider };
}

test("the remitentes group renders above the Bandeja rows, with actions only for the owner", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const RemitentesNuevos = (await import("@/components/business-app/remitentes-nuevos")).default;
  const { remitentesNuevosItems } = await import("@/components/business-app/remitentes-nuevos");
  const { i18n, I18nextProvider } = await spanish();
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  const paint = (role: "owner" | "accountant", items: BusinessEmailDelivery[]) => act(async () => {
    const value = { chosen: { role, capabilities: ["read"] }, source: {}, panel: { kind: "inbox" }, openPanel: () => undefined, records: {} } as unknown as BusinessContextValue;
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessContext.Provider value={value}>
          <div>
            <RemitentesNuevos items={items} />
            <ul data-testid="bandeja-rows"><li data-testid="reception-row">Recibo en la Bandeja</li></ul>
          </div>
        </BusinessContext.Provider>
      </I18nextProvider>,
    );
  });
  await paint("owner", [sender()]);
  const group = host.querySelector<HTMLElement>('[data-testid="remitentes-nuevos"]')!;
  const row = host.querySelector<HTMLElement>('[data-testid="bandeja-rows"]')!;
  assert.ok(group);
  assert.equal(group.compareDocumentPosition(row) & Node.DOCUMENT_POSITION_FOLLOWING, Node.DOCUMENT_POSITION_FOLLOWING);
  assert.equal(group.querySelector("h3")?.textContent, "Remitentes nuevos");
  assert.match(group.textContent ?? "", /Remitente nuevo/);
  assert.match(group.textContent ?? "", /Aviso 7/);
  assert.equal(group.textContent?.includes("Prueba recibida"), false);
  const authorize = [...group.querySelectorAll("button")].find((button) => button.textContent === "Autorizar remitente");
  const block = [...group.querySelectorAll("button")].find((button) => button.textContent === "Bloquear");
  assert.ok(authorize && block);
  assert.match(authorize.className, /min-h-11/);
  assert.match(block.className, /min-h-11/);
  assert.equal(authorize.disabled, false);
  assert.equal(block.disabled, false);
  assert.equal(group.querySelector('[data-testid="remitente-admin-only"]'), null);
  await paint("accountant", [sender()]);
  const grantee = host.querySelector('[data-testid="remitentes-nuevos"]');
  assert.ok(grantee);
  assert.equal([...host.querySelectorAll("button")].some((button) => button.textContent === "Autorizar remitente" || button.textContent === "Bloquear"), false);
  assert.equal(grantee?.querySelector('[data-testid="remitente-admin-only"]')?.textContent, "Solo el administrador puede autorizar este remitente");
  for (const items of [remitentesNuevosItems(null), remitentesNuevosItems(undefined), remitentesNuevosItems([{ id: "remitentes_nuevos", items: [] }]), remitentesNuevosItems([{ id: "bandeja", items: [sender()] }])]) {
    await paint("owner", items);
    assert.equal(host.querySelector('[data-testid="remitentes-nuevos"]'), null);
    assert.equal(host.textContent?.includes("Remitentes nuevos"), false);
  }
});

test("a sender action calls the API once per click and refreshes the group", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { useState } = await import("react");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const RemitentesNuevos = (await import("@/components/business-app/remitentes-nuevos")).default;
  const { i18n, I18nextProvider } = await spanish();
  const calls: BusinessEmailSenderChange[] = [];
  let refreshes = 0;
  let release: () => void = () => undefined;
  let gate = new Promise<void>((resolve) => { release = resolve; });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  function Harness() {
    const [items, setItems] = useState([sender()]);
    const value = {
      chosen: { role: "owner", capabilities: ["read", "prepare", "approve"] },
      source: { setEmailSender: async (body: BusinessEmailSenderChange) => { calls.push(body); await gate; return { ...body, id: "rule-1" }; } },
      emailInboxRefresh: { refresh: async () => { refreshes += 1; setItems([]); } },
      panel: { kind: "inbox" },
      openPanel: () => undefined,
      records: {},
    } as unknown as BusinessContextValue;
    return <I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><RemitentesNuevos items={items} /></BusinessContext.Provider></I18nextProvider>;
  }
  await act(async () => { root.render(<Harness />); });
  const button = (label: string) => [...host.querySelectorAll("button")].find((item) => item.textContent === label)!;
  await act(async () => { button("Autorizar remitente").click(); button("Autorizar remitente").click(); button("Bloquear").click(); });
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0], { kind: "address", value: "nuevo@proveedor.example", status: "authorized" });
  assert.equal(button("Autorizar remitente").disabled, true);
  assert.equal(button("Bloquear").disabled, true);
  await act(async () => { release(); });
  assert.equal(refreshes, 1);
  assert.equal(host.querySelector('[data-testid="remitentes-nuevos"]'), null);
  gate = new Promise<void>((resolve) => { release = resolve; });
  await act(async () => { root.render(<Harness />); });
  const failing = {
    chosen: { role: "owner", capabilities: ["read"] },
    source: { setEmailSender: async () => { calls.push({ kind: "address", value: "nuevo@proveedor.example", status: "blocked" }); throw new Error("no"); } },
    emailInboxRefresh: { refresh: async () => { refreshes += 1; } },
    panel: { kind: "inbox" },
    openPanel: () => undefined,
    records: {},
  } as unknown as BusinessContextValue;
  await act(async () => {
    root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={failing}><RemitentesNuevos items={[sender()]} /></BusinessContext.Provider></I18nextProvider>);
  });
  const before = calls.length;
  await act(async () => { button("Bloquear").click(); });
  assert.equal(calls.length, before + 1);
  assert.equal(refreshes, 1);
  const alert = host.querySelector('[role="alert"]');
  assert.equal(alert?.textContent, "No pudimos actualizar este remitente.");
  assert.equal(button("Bloquear").disabled, false);
  assert.equal(button("Autorizar remitente").disabled, false);
});

test("a bandeja row renders review_note from the API and leaves the action enabled", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const ReceptionArrivalRow = (await import("@/components/business-app/recepcion/ReceptionArrivalRow")).default;
  const { defaultReceptionPreferences } = await import("@/components/business-app/recepcion/ReceptionControls");
  const { i18n, I18nextProvider } = await spanish();
  const value = { chosen: { role: "owner", capabilities: ["read", "prepare", "approve"] }, source: { mode: "live" }, panel: { kind: "inbox" }, openPanel: () => undefined, records: { emails: [] } } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  const paint = (reviewNote: string | null) => act(async () => {
    const row = notedReceipt(reviewNote);
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessContext.Provider value={value}>
          <ul><ReceptionArrivalRow row={row} panel={{ kind: "inbox" }} openPanel={() => undefined} preferences={defaultReceptionPreferences()} selectable={false} checked={false} unseen={false} onCheck={() => undefined} onSeen={() => undefined} onInspect={() => undefined} inspecting={false} /></ul>
        </BusinessContext.Provider>
      </I18nextProvider>,
    );
  });
  await paint("Texto distinto 41");
  const note = host.querySelector('[data-testid="bandeja-review-note"]');
  const source = host.querySelector('[data-testid="reception-source"]');
  const pill = host.querySelector('[data-testid="status-pill"]');
  assert.equal(host.querySelector('[data-testid="reception-row"]')?.getAttribute("data-kind"), "receipt");
  assert.ok(note && source?.contains(note));
  assert.equal(note.textContent, "Texto distinto 41");
  assert.equal(pill?.textContent, "Listo para revisar");
  assert.equal(pill?.getAttribute("data-reception-status"), "neutral");
  assert.equal(host.textContent?.includes("Necesita atención"), false);
  assert.equal(host.textContent?.includes("No pudimos verificar este remitente."), false);
  assert.equal(note.className.includes("9e2f39"), false);
  assert.equal([...host.querySelectorAll("button")].every((button) => button.disabled === false), true);
  await paint(null);
  assert.equal(host.querySelector('[data-testid="bandeja-review-note"]'), null);
});

test("the Bandeja screen puts the group above its rows", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const Inbox = (await import("@/components/business-app/BusinessInboxPanel")).default;
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { i18n, I18nextProvider } = await spanish();
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const receipts = await source.receipts("inbox");
  const notes = await source.captures("", 50, "inbox");
  const emails = await source.emailDeliveries();
  const activity = { reading_count: 0, unread_count: 0, presentation: "none" as const, pending_review_count: 1, needs_attention_count: 0, ready_to_review_count: 1 };
  const value = {
    source: { ...source, receiptPage: async () => ({ items: receipts, activity }) },
    records: { workspace: await source.workspace(), overview: null, inbox: receipts, notes: notes.items, notesTruncated: false, emails, error: false, receiptActivity: activity, emailInbox: [{ id: "remitentes_nuevos", items: [sender()] }, { id: "bandeja", items: [] }] },
    chosen: { role: "owner", space_id: "own", grant_id: "own", name: "Mi negocio", capabilities: ["read", "prepare", "approve"], permissions: ["read", "prepare", "approve", "manage"], access_seen: true },
    spaces: [], chooseBusiness: () => undefined, markAccessSeen: async () => undefined, lostAccess: false, clearLostAccess: () => undefined,
    revision: 0, reload: () => undefined, refresh: async () => "updated" as const, period: { key: "all", from: "", to: null }, setPeriod: () => undefined,
    panel: { kind: "inbox" }, openPanel: () => undefined, actions: { create: [], composer: [], starterEntries: [] }, bridge: null,
    attachedReceipt: null, clearAttachedReceipt: () => undefined, openExport: () => undefined, emailRefresh: { refresh: () => undefined, refreshing: false, stalled: false },
    emailInboxRefresh: { refresh: async () => undefined }, retrySources: () => undefined,
  } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><Inbox /></BusinessContext.Provider></I18nextProvider>); });
  for (let i = 0; i < 40; i += 1) {
    if (host.querySelector('[data-testid="reception-row"]')) break;
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); });
  }
  const group = host.querySelector<HTMLElement>('[data-testid="remitentes-nuevos"]');
  const row = host.querySelector<HTMLElement>('[data-testid="reception-row"]');
  assert.ok(group, host.textContent ?? "");
  assert.ok(row);
  assert.equal(group.compareDocumentPosition(row) & Node.DOCUMENT_POSITION_FOLLOWING, Node.DOCUMENT_POSITION_FOLLOWING);
  assert.equal([...group.querySelectorAll("button")].some((button) => button.textContent === "Autorizar remitente"), true);
});

test("an inbox failure does not replace the Bandeja rows", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { useEmailInbox } = await import("@/components/business-app/useEmailInbox");
  const { remitentesNuevosItems } = await import("@/components/business-app/remitentes-nuevos");
  const source = { emailInbox: async () => { throw new Error("down"); } };
  function Probe() {
    const inbox = useEmailInbox({ source: source as never, enabled: true, revision: 0, businessKey: "own" });
    const items = remitentesNuevosItems(inbox.groups);
    return <div><p data-testid="inbox-state">{inbox.failure ? "failed" : inbox.groups ? "ready" : "loading"}</p><p data-testid="group-size">{items.length}</p><ul data-testid="bandeja-rows"><li>Recibo</li></ul></div>;
  }
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  await act(async () => { root.render(<Probe />); });
  for (let i = 0; i < 20 && host.querySelector('[data-testid="inbox-state"]')?.textContent !== "failed"; i += 1) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); });
  }
  assert.equal(host.querySelector('[data-testid="inbox-state"]')?.textContent, "failed");
  assert.equal(host.querySelector('[data-testid="group-size"]')?.textContent, "0");
  assert.equal(host.querySelector('[data-testid="bandeja-rows"]')?.textContent, "Recibo");
});

test("sender standing chooses the note and the buttons", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const RemitentesNuevos = (await import("@/components/business-app/remitentes-nuevos")).default;
  const { i18n, I18nextProvider } = await spanish();
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  const paint = (role: "owner" | "accountant", item: BusinessEmailDelivery) => act(async () => {
    const value = { chosen: { role, capabilities: ["read"] }, source: {}, panel: { kind: "inbox" }, openPanel: () => undefined, records: {} } as unknown as BusinessContextValue;
    root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><RemitentesNuevos items={[item]} /></BusinessContext.Provider></I18nextProvider>);
  });
  const labels = () => [...host.querySelectorAll("button")].map((button) => button.textContent);
  const note = () => host.querySelector('[data-testid="bandeja-review-note"]');
  await paint("owner", sender({ sender_standing: "authorized", review_note: "Nota de la API 41", notice: null }));
  assert.equal(/ellipsis|truncate/.test(host.querySelector('[data-testid="remitente-sender"]')?.className ?? ""), false);
  assert.deepEqual(labels(), ["Bloquear"]);
  assert.equal(note()?.textContent, "Nota de la API 41");
  assert.equal(note()?.className.includes("9e2f39"), false);
  assert.equal(host.textContent?.includes("No pudimos verificar este remitente."), false);
  await paint("owner", sender({ sender_standing: "new", review_note: "Nota de la API 41", notice: null }));
  assert.deepEqual(labels(), ["Autorizar remitente", "Bloquear"]);
  assert.equal(note(), null);
  await paint("owner", sender({ notice: null }));
  assert.deepEqual(labels(), ["Autorizar remitente", "Bloquear"]);
  assert.equal(note(), null);
  await paint("owner", sender({ sender_standing: "blocked", review_note: "Nota de la API 41", notice: null }));
  assert.deepEqual(labels(), ["Autorizar remitente", "Bloquear"]);
  assert.equal(note(), null);
  await paint("accountant", sender({ sender_standing: "authorized", review_note: "Nota de la API 41", notice: null }));
  assert.deepEqual(labels(), []);
  assert.equal(note()?.textContent, "Nota de la API 41");
  assert.equal(host.querySelector('[data-testid="remitente-admin-only"]')?.textContent, "Solo el administrador puede autorizar este remitente");
  await paint("owner", sender({ sender_standing: "authorized", review_note: "Nota de la API 41", notice: null }));
  assert.equal(host.querySelector('[data-testid="remitente-admin-only"]'), null);
});

test("the sender address wraps at every width and the label stays one line", () => {
  const css = readFileSync(new URL("../components/business-app/recepcion/reception.module.css", import.meta.url), "utf8");
  const blocks = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter((block) => block[1].includes(".remitenteSender") || block[1].includes(".remitenteLabel") || block[1].includes(".remitenteActions > button"));
  const sender = blocks.filter((block) => block[1].includes(".remitenteSender")).map((block) => block[2]).join(" ");
  const label = blocks.filter((block) => block[1].includes(".remitenteLabel")).map((block) => block[2]).join(" ");
  assert.match(sender, /overflow-wrap:\s*anywhere/);
  assert.equal(sender.includes("ellipsis"), false);
  assert.equal(sender.includes("nowrap"), false);
  assert.match(label, /white-space:\s*nowrap/);
  assert.match(blocks.filter((block) => block[1].includes(".remitenteActions > button")).map((block) => block[2]).join(" "), /min-height:\s*44px/);
  const phone = css.slice(css.indexOf("@media (max-width:640px)"));
  const actions = phone.match(/\.remitente \.remitenteActions\s*\{([^}]*)\}/)?.[1] ?? "";
  const phoneButtons = phone.match(/\.remitenteActions > button\s*\{([^}]*)\}/)?.[1] ?? "";
  assert.match(actions, /flex-direction:\s*column/);
  assert.match(actions, /gap:\s*8px/);
  assert.match(actions, /width:\s*100%/);
  assert.match(phoneButtons, /width:\s*100%/);
  assert.match(phoneButtons, /white-space:\s*nowrap/);
  const readOnly = css.match(/\.remitenteReadOnly\s*\{([^}]*)\}/)?.[1] ?? "";
  assert.match(readOnly, /font-size:\s*13px/);
  assert.match(readOnly, /var\(--muted\)/);
  assert.equal(/9e2f39|red/.test(readOnly), false);
  assert.equal(css.includes(".remitentesList") && /border-radius/.test(css.slice(css.indexOf(".remitentesList"), css.indexOf(".remitente {"))), false);
  assert.equal(/\.remitenteDot\s*\{[^}]*border-radius/.test(css), false);
});

test("the Por revisar tab and the badge share one count", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const Inbox = (await import("@/components/business-app/BusinessInboxPanel")).default;
  const BusinessSidebarNav = (await import("@/components/business-app/BusinessSidebarNav")).default;
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { i18n, I18nextProvider } = await spanish();
  const previousNode = process.env.NODE_ENV;
  const previousMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
  process.env.NODE_ENV = "production";
  process.env.NEXT_PUBLIC_MOCK_AUTH = "false";
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const receipts = await source.receipts("inbox");
  const notes = await source.captures("", 50, "inbox");
  const emails = await source.emailDeliveries();
  const activity = { reading_count: 0, unread_count: 0, presentation: "none" as const, pending_review_count: 1, needs_attention_count: 0, ready_to_review_count: 1 };
  const emailInbox = [{ id: "remitentes_nuevos", items: [sender({ id: "one" }), sender({ id: "two", sender: "otro@proveedor.example" })] }, { id: "bandeja", items: [] }];
  const shell = { currentView: "workspace" as const, conversationId: null, isBelowTablet: false, sidebarCollapsed: false, greetingName: null, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined };
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  cleanup = async () => {
    await act(async () => root.unmount());
    host.remove();
    if (previousNode === undefined) delete process.env.NODE_ENV;
    else process.env.NODE_ENV = previousNode;
    if (previousMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = previousMock;
  };
  const paint = (role: "owner" | "accountant") => act(async () => {
    const value = {
      source: { ...source, receiptPage: async () => ({ items: receipts, activity }) },
      records: { workspace: await source.workspace(), overview: null, inbox: receipts, notes: notes.items, notesTruncated: false, emails, error: false, receiptActivity: activity, emailInbox },
      chosen: { role, space_id: "own", grant_id: "own", name: "Mi negocio", capabilities: role === "owner" ? ["read", "prepare", "approve"] : ["read"], access_seen: true },
      spaces: [], chooseBusiness: () => undefined, markAccessSeen: async () => undefined, lostAccess: false, clearLostAccess: () => undefined,
      revision: 0, reload: () => undefined, refresh: async () => "updated" as const, period: { key: "all", from: "", to: null }, setPeriod: () => undefined,
      panel: { kind: "inbox" }, openPanel: () => undefined, actions: { create: [], composer: [], starterEntries: [] }, bridge: null,
      attachedReceipt: null, clearAttachedReceipt: () => undefined, openExport: () => undefined, emailRefresh: { refresh: () => undefined, refreshing: false, stalled: false },
      emailInboxRefresh: { refresh: async () => undefined }, retrySources: () => undefined,
    } as unknown as BusinessContextValue;
    root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><BusinessSidebarNav shell={shell} /><Inbox /></BusinessContext.Provider></I18nextProvider>);
  });
  const reviewCount = () => host.querySelector("#reception-tab-review span")?.textContent ?? "";
  await paint("owner");
  for (let i = 0; i < 40 && reviewCount() !== "3"; i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); });
  await act(async () => { host.querySelector<HTMLButtonElement>("#reception-tab-review")?.click(); });
  assert.ok(host.querySelector('[data-testid="remitentes-nuevos"]'));
  assert.equal(reviewCount(), "3");
  assert.equal(host.querySelector('[data-testid="business-inbox-count"]')?.textContent, "3");
  await paint("accountant");
  for (let i = 0; i < 40 && reviewCount() !== "1"; i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); });
  assert.equal(reviewCount(), "1");
  assert.equal(host.querySelector('[data-testid="business-inbox-count"]')?.textContent, "1");
  assert.equal([...host.querySelectorAll("button")].some((button) => button.textContent === "Autorizar remitente" || button.textContent === "Bloquear"), false);
});

test("the sidebar badge counts remitentes nuevos for the owner only", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const BusinessSidebarNav = (await import("@/components/business-app/BusinessSidebarNav")).default;
  const { i18n, I18nextProvider } = await spanish();
  const activity = { reading_count: 0, unread_count: 0, presentation: "none" as const, pending_review_count: 2, needs_attention_count: 0, ready_to_review_count: 2 };
  const emailInbox = [{ id: "remitentes_nuevos", items: [{ id: "a" }, { id: "b" }] }, { id: "bandeja", items: [{ id: "c" }] }];
  const shell = { currentView: "workspace" as const, conversationId: null, isBelowTablet: false, sidebarCollapsed: false, greetingName: null, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined };
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  const paint = (role: "owner" | "accountant") => act(async () => {
    const value = { chosen: { role, capabilities: ["read"] }, records: { receiptActivity: activity, emailInbox }, panel: { kind: "overview" }, openPanel: () => undefined } as unknown as BusinessContextValue;
    root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><BusinessSidebarNav shell={shell} /></BusinessContext.Provider></I18nextProvider>);
  });
  await paint("owner");
  assert.equal(host.querySelector('[data-testid="business-inbox-count"]')?.textContent, "4");
  await paint("accountant");
  assert.equal(host.querySelector('[data-testid="business-inbox-count"]')?.textContent, "2");
});
