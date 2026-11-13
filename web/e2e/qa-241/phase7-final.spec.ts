import { test, expect, type BrowserContext, type Page } from "@playwright/test";
import { identities, loginViaUi } from "../qa-248/helpers";
import {
  conversationMessages,
  meProbe,
  messageDigest,
  saveEvidence,
  sendTurn,
  shot,
  startNewChat,
} from "./j241.helpers";

// Final release-captain pass: bounded browser regression for the two P1
// corrections (typed temporal direction; runtime-owned provider records).
// Evidence-first; verdicts derive from persisted typed metadata.

test.describe.configure({ mode: "serial" });

test.beforeEach(async () => {
  test.setTimeout(600_000);
});

let context: BrowserContext;
let page: Page;

async function capture(tag: string, conversationId: string) {
  const { items } = await conversationMessages(context, conversationId);
  saveEvidence(`${tag}.messages`, {
    conversation_id: conversationId,
    captured_at: new Date().toISOString(),
    items: messageDigest(items),
  });
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

test("r0 probe + usage baseline", async () => {
  const probe = await meProbe(context);
  expect(probe.status).toBe(200);
  expect(probe.isAdmin).toBe(false);
});

test("r1 BTC future (empty-intent route target) + reload", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "If I invest $10,000 in Bitcoin and just hold it, what will it be worth in ten years?",
    { conversationId: null },
  );
  await shot(page, "r1-btc-future");
  await capture("r1-btc-future", conversationId);
  await page.reload();
  await page.waitForTimeout(4_000);
  await capture("r1-btc-future.after-reload", conversationId);
});

test("r2 Spanish future control (es-419 profile)", async ({ browser }) => {
  const ids = identities();
  const esContext = await browser.newContext();
  const esPage = await esContext.newPage();
  try {
    await loginViaUi(esPage, ids.secondEmail, ids.secondPassword);
    await startNewChat(esPage);
    const { conversationId } = await sendTurn(
      esPage,
      esContext,
      "Si invierto $10,000 en NVDA con una estrategia de cruce dorado, ¿cuánto tendré dentro de diez años?",
      { conversationId: null },
    );
    await shot(esPage, "r2-nvda-future-es");
    const { items } = await conversationMessages(esContext, conversationId);
    saveEvidence("r2-nvda-future-es.messages", {
      conversation_id: conversationId,
      items: messageDigest(items),
    });
  } finally {
    await esContext.close();
  }
});

test("r3 explicit historical lookback control", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "Backtest $10,000 in AAPL over the last three years.",
    { conversationId: null },
  );
  await shot(page, "r3-lookback-control");
  await capture("r3-lookback-control", conversationId);
});

test("r4 unresolved-asset future control (Zorbcoin)", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "If I put $5,000 into Zorbcoin, what will it become by 2031?",
    { conversationId: null },
  );
  await shot(page, "r4-zorbcoin");
  await capture("r4-zorbcoin", conversationId);
});

test("r5 provider-resolved NVDA future conservation", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "If I invest $10,000 in NVDA using a golden cross strategy, how much will it be worth in ten years?",
    { conversationId: null },
  );
  await shot(page, "r5-nvda-future");
  await capture("r5-nvda-future", conversationId);
});

