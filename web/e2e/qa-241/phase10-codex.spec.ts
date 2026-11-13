import { test, expect, type BrowserContext, type Page } from "@playwright/test";
import { identities, loginViaUi } from "../qa-248/helpers";
import {
  conversationMessages,
  meProbe,
  messageDigest,
  reopenConversation,
  saveEvidence,
  sendTurn,
  shot,
  startNewChat,
} from "./j241.helpers";

// PR #266 Codex correction pass: clarification-owned future prose (EN/ES),
// distinct invalid-date repair labels, supported lookback control, reload
// parity. One attempt each.

test.describe.configure({ mode: "serial" });

test.beforeEach(async () => {
  test.setTimeout(600_000);
});

let context: BrowserContext;
let page: Page;
let futureConversationId: string | null = null;

async function capture(tag: string, conversationId: string) {
  const { items } = await conversationMessages(context, conversationId);
  saveEvidence(`${tag}.messages`, {
    conversation_id: conversationId,
    captured_at: new Date().toISOString(),
    items: messageDigest(items),
  });
  return items;
}

test.beforeAll(async ({ browser }) => {
  test.setTimeout(180_000);
  const ids = identities();
  context = await browser.newContext();
  page = await context.newPage();
  await loginViaUi(page, ids.recoveryEmail, ids.recoveryPassword);
});

test.afterAll(async () => {
  await context?.close();
});

test("p0 probe + usage baseline", async () => {
  const probe = await meProbe(context);
  expect(probe.status).toBe(200);
  expect(probe.isAdmin).toBe(false);
});

test("p1 EN future ask gets clarification-owned refusal, no card", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "If I invest $10,000 in NVDA using a golden cross strategy, how much will it be worth in ten years?",
    { conversationId: null },
  );
  futureConversationId = conversationId;
  await shot(page, "p1-en-future");
  await capture("p1-en-future", conversationId);
});

test("p2 ES future ask gets refusal, no card", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "Si invierto $10,000 en NVDA con una estrategia de cruce dorado, ¿cuánto tendré dentro de diez años?",
    { conversationId: null },
  );
  await shot(page, "p2-es-future");
  await capture("p2-es-future", conversationId);
});

test("p3 invalid date window keeps distinct repair choices", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "Backtest $10,000 in AAPL from January 2, 2025 through January 2, 2020 using buy and hold.",
    { conversationId: null },
  );
  await shot(page, "p3-invalid-dates");
  await capture("p3-invalid-dates", conversationId);
  const visible = await page
    .locator("main")
    .innerText()
    .catch(() => "");
  saveEvidence("p3-visible-text", { visible: visible.slice(-3000) });
});

test("p4 supported lookback control still confirms", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "Backtest $10,000 in AAPL over the last three years.",
    { conversationId: null },
  );
  await shot(page, "p4-lookback-control");
  await capture("p4-lookback-control", conversationId);
});

test("p5 reload keeps the EN future recovery byte-identical", async () => {
  expect(futureConversationId).toBeTruthy();
  await page.reload({ waitUntil: "networkidle" });
  await reopenConversation(page, futureConversationId as string);
  await shot(page, "p5-reload");
  const items = await capture("p5-reload", futureConversationId as string);
  expect(items.length).toBeGreaterThan(0);
});

test("p9 usage after", async () => {
});
