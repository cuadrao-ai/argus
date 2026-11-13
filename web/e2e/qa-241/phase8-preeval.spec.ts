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

// Final pre-eval browser recheck: three journeys, one attempt each.

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

test("p0 probe + usage baseline", async () => {
  const probe = await meProbe(context);
  expect(probe.status).toBe(200);
  expect(probe.isAdmin).toBe(false);
});

test("p1 BTC future empty-intent corridor", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "If I invest $10,000 in Bitcoin and just hold it, what will it be worth in ten years?",
    { conversationId: null },
  );
  await shot(page, "p1-btc-future");
  await capture("p1-btc-future", conversationId);
});

test("p2 Spanish NVDA future (es-419 profile)", async ({ browser }) => {
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
    await shot(esPage, "p2-nvda-future-es");
    const { items } = await conversationMessages(esContext, conversationId);
    saveEvidence("p2-nvda-future-es.messages", {
      conversation_id: conversationId,
      items: messageDigest(items),
    });
  } finally {
    await esContext.close();
  }
});

test("p3 historical lookback control", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "Backtest $10,000 in AAPL over the last three years.",
    { conversationId: null },
  );
  await shot(page, "p3-lookback-control");
  await capture("p3-lookback-control", conversationId);
});
