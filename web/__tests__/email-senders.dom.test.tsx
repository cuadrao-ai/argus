import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import EmailSenders from "@/components/business-app/EmailSenders";
import { TOOLTIP_DELAY_MS } from "@/components/ui/Tooltip";
import { EmailSenderRequestError, type EmailSender, type EmailSenderClient, type EmailSenderUpdate } from "@/lib/business-email";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1280, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

const sender = (overrides: Partial<EmailSender> & Pick<EmailSender, "id" | "value" | "status">): EmailSender => ({
  kind: "address",
  ...overrides,
});

const mixed: EmailSender[] = [
  sender({ id: "p-yes", value: "facturas@ferreteria.example", status: "pending", tag: "verified", last_auth_result: "aligned" }),
  sender({ id: "p-no", value: "avisos@correo.example", status: "pending", tag: "unverified", last_auth_result: "aligned" }),
  sender({ id: "p-hand", value: "manual@dueno.example", status: "pending", tag: null, last_auth_result: null }),
  sender({ id: "p-old", value: "viejo@negocio.example", status: "pending", last_auth_result: "aligned" }),
  sender({ id: "domain", value: "proveedor.example", status: "authorized", kind: "domain", tag: null }),
  sender({ id: "blocked", value: "spam@lista.example", status: "blocked", tag: "unverified" }),
];

async function mount(client: EmailSenderClient) {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { en: { translation: english }, "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => { root.render(<I18nextProvider i18n={i18n}><EmailSenders client={client} /></I18nextProvider>); });
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 20 && !done(); i += 1) await act(async () => { await Promise.resolve(); });
  };
  return {
    host,
    settle,
    close: async () => { await act(async () => root.unmount()); host.remove(); },
  };
}

const rows = (host: HTMLElement) => [...host.querySelectorAll<HTMLElement>("[data-testid='email-sender-row']")];
const text = (row: HTMLElement) => row.textContent ?? "";
const button = (row: HTMLElement, label: string) => [...row.querySelectorAll("button")].find((item) => item.textContent === label);

test("pending senders stay first, the count shows, and tags follow tag only", async () => {
  const scrambled = [mixed[5]!, mixed[1]!, mixed[4]!, mixed[0]!, mixed[2]!, mixed[3]!];
  const page = await mount({ list: async () => scrambled, update: async (body) => ({ ...scrambled[0]!, ...body }) });
  try {
    await page.settle(() => rows(page.host).length === 6);
    const pending = page.host.querySelector("details")!;
    assert.equal(pending.open, true);
    assert.equal(page.host.querySelector("[data-testid='email-senders-pending-count']")?.textContent, "[PENDIENTE COPY] 4");
    assert.deepEqual(rows(page.host).map((row) => row.getAttribute("data-status")), ["pending", "pending", "pending", "pending", "authorized", "blocked"]);
    assert.deepEqual(rows(page.host).map((row) => row.querySelector("span")?.textContent), [
      "avisos@correo.example", "facturas@ferreteria.example", "manual@dueno.example", "viejo@negocio.example", "proveedor.example", "spam@lista.example",
    ]);
    const tags = [...page.host.querySelectorAll("[data-testid='email-sender-tag']")].map((tag) => tag.getAttribute("data-verification"));
    assert.deepEqual(tags, ["unverified", "verified", "unverified", "unverified"]);
    assert.equal(page.host.textContent?.includes("aligned"), false);
    assert.equal(rows(page.host)[2]?.querySelector("[data-testid='email-sender-tag']"), null);
    assert.equal(rows(page.host)[4]?.querySelector("[data-testid='email-sender-tag']"), null);
    for (const control of page.host.querySelectorAll("button, summary")) assert.match(control.className, /min-h-11/);
  } finally { await page.close(); }
});

test("an empty pending group stays open without a count, and no senders is its own empty state", async () => {
  const settled = mixed.filter((item) => item.status !== "pending");
  const page = await mount({ list: async () => settled, update: async (body) => ({ ...settled[0]!, ...body }) });
  try {
    await page.settle(() => rows(page.host).length === 2);
    const pending = page.host.querySelector("details")!;
    assert.equal(pending.open, true);
    assert.equal(page.host.querySelector("[data-testid='email-senders-pending-count']"), null);
    assert.match(pending.textContent ?? "", /\[PENDIENTE COPY\] Nadie en espera/);
    assert.match(page.host.textContent ?? "", /proveedor\.example/);
    assert.match(page.host.textContent ?? "", /spam@lista\.example/);
  } finally { await page.close(); }
  const empty = await mount({ list: async () => [], update: async (body) => ({ id: "new", kind: body.kind, value: body.value, status: body.status }) });
  try {
    await empty.settle(() => empty.host.querySelector("[data-testid='email-senders-empty']") !== null);
    assert.match(empty.host.textContent ?? "", /\[PENDIENTE COPY\] No hay remitentes/);
    assert.equal(empty.host.querySelector("details"), null);
  } finally { await empty.close(); }
});

test("loading and a failed load with retry", async () => {
  let release: (value: EmailSender[]) => void = () => undefined;
  const loading = await mount({ list: () => new Promise((resolve) => { release = resolve; }), update: async (body) => ({ id: "new", ...body }) });
  try {
    assert.equal(loading.host.querySelector("[data-testid='email-senders-loading']")?.getAttribute("aria-busy"), "true");
    assert.match(loading.host.textContent ?? "", /\[PENDIENTE COPY\] Cargando remitentes/);
    await act(async () => release([]));
    await loading.settle(() => loading.host.querySelector("[data-testid='email-senders-empty']") !== null);
  } finally { await loading.close(); }
  let lists = 0;
  const failed = await mount({
    list: async () => { lists += 1; throw new EmailSenderRequestError(503, "unavailable"); },
    update: async (body) => ({ id: "new", ...body }),
  });
  try {
    await failed.settle(() => failed.host.querySelector("[data-testid='email-senders-error']") !== null);
    const retry = [...failed.host.querySelectorAll("button")].find((item) => item.textContent === "[PENDIENTE COPY] Reintentar");
    assert.ok(retry);
    assert.match(retry.className, /min-h-11/);
    await act(async () => retry.click());
    await failed.settle(() => lists === 2);
    assert.equal(lists, 2);
  } finally { await failed.close(); }
});

test("authorize and block replace the row from the returned item, including a new id", async () => {
  const calls: EmailSenderUpdate[] = [];
  let created = false;
  const page = await mount({
    list: async () => [mixed[0]!],
    update: async (body) => {
      calls.push(body);
      if (!created) return { ...mixed[0]!, status: body.status, tag: "verified" };
      return { id: "created", kind: body.kind, value: "nueva@negocio.example", status: body.status, tag: null };
    },
  });
  try {
    await page.settle(() => rows(page.host).length === 1);
    const authorize = button(rows(page.host)[0]!, "Autorizar")!;
    await act(async () => authorize.click());
    await page.settle(() => rows(page.host)[0]?.getAttribute("data-status") === "authorized");
    assert.deepEqual(calls[0], { kind: "address", value: "facturas@ferreteria.example", status: "authorized" });
    assert.equal(page.host.querySelector("[data-testid='email-senders-pending-count']"), null);
    created = true;
    const block = button(rows(page.host)[0]!, "Bloquear")!;
    await act(async () => block.click());
    await page.settle(() => text(rows(page.host)[0]!).includes("nueva@negocio.example"));
    assert.equal(rows(page.host)[0]?.getAttribute("data-status"), "blocked");
    assert.deepEqual(calls[1], { kind: "address", value: "facturas@ferreteria.example", status: "blocked" });
  } finally { await page.close(); }
});

test("a 422 keeps the buttons enabled and a 403 disables them", async () => {
  let calls = 0;
  const rejected = await mount({
    list: async () => [mixed[1]!],
    update: async () => { calls += 1; throw new EmailSenderRequestError(422, "email_sender_invalid"); },
  });
  try {
    await rejected.settle(() => rows(rejected.host).length === 1);
    const block = () => button(rows(rejected.host)[0]!, "Bloquear")!;
    await act(async () => block().click());
    await rejected.settle(() => rejected.host.querySelector("[data-testid='email-sender-error']") !== null);
    assert.equal(block().disabled, false);
    assert.match(block().className, /min-h-11/);
    await act(async () => block().click());
    await rejected.settle(() => calls === 2);
    assert.equal(calls, 2);
  } finally { await rejected.close(); }
  let forbiddenCalls = 0;
  const forbidden = await mount({
    list: async () => [mixed[1]!],
    update: async () => { forbiddenCalls += 1; throw new EmailSenderRequestError(403, "forbidden"); },
  });
  try {
    await forbidden.settle(() => rows(forbidden.host).length === 1);
    await act(async () => button(rows(forbidden.host)[0]!, "Autorizar")!.click());
    await forbidden.settle(() => forbidden.host.querySelector("[data-testid='email-senders-forbidden']") !== null);
    assert.match(forbidden.host.textContent ?? "", /\[PENDIENTE COPY\] Solo un administrador puede cambiar remitentes/);
    for (const control of rows(forbidden.host)[0]!.querySelectorAll("button")) {
      if (control.getAttribute("data-testid") !== "email-sender-tag") assert.equal(control.disabled, true);
    }
    await act(async () => button(rows(forbidden.host)[0]!, "Bloquear")!.click());
    assert.equal(forbiddenCalls, 1);
  } finally { await forbidden.close(); }
});

test("the verification tag exposes its tooltip to pointer and keyboard", async () => {
  const page = await mount({ list: async () => [mixed[0]!], update: async (body) => ({ ...mixed[0]!, ...body }) });
  try {
    await page.settle(() => page.host.querySelector("[data-testid='email-sender-tag']") !== null);
    const tag = page.host.querySelector<HTMLButtonElement>("[data-testid='email-sender-tag']")!;
    assert.equal(tag.textContent, "Verificado");
    assert.match(tag.className, /min-h-11/);
    await act(async () => { tag.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })); });
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, TOOLTIP_DELAY_MS + 30)); });
    const tip = document.querySelector("[role='tooltip']");
    assert.equal(tip?.textContent, "El correo pasó la verificación del remitente.");
    assert.equal(tag.getAttribute("aria-describedby"), tip?.id);
    await act(async () => { tag.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
    assert.equal(document.querySelector("[role='tooltip']"), null);
    tag.focus();
    assert.equal(document.activeElement, tag);
    assert.equal(tag.matches(":focus-visible"), true);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, TOOLTIP_DELAY_MS + 30)); });
    assert.equal(document.querySelector("[role='tooltip']")?.textContent, "El correo pasó la verificación del remitente.");
  } finally { await page.close(); }
});
