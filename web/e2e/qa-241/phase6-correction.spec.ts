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

// Bounded live regression for the #241 correction pass: provider-resolved
// asset conservation through refusal recovery, plus non-BTC, unresolved-asset,
// and Spanish future-performance controls. Evidence-first; verdicts derive
// from the captured typed metadata.

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

test("c0 account probe + usage baseline", async () => {
  const probe = await meProbe(context);
  console.log(`me.status=${probe.status} is_admin=${probe.isAdmin}`);
  expect(probe.status).toBe(200);
  expect(probe.isAdmin).toBe(false);
});

test("c1 BTC refusal regression + reload + selection + period", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "If I invest $10,000 in Bitcoin and just hold it, what will it be worth in ten years?",
    { conversationId: null },
  );
  await shot(page, "c1-btc-turn1");
  await capture("c1-btc", conversationId);

  await page.reload();
  await page.waitForTimeout(4_000);
  await shot(page, "c1-btc-after-reload");
  await capture("c1-btc.after-reload", conversationId);

  // The reload can land on a fresh composer; re-anchor the conversation so
  // the selection turn continues the recovery instead of starting a new idea.
  await reopenConversation(page, conversationId);
  await sendTurn(page, context, "Yes, run the historical test.", {
    conversationId,
  });
  await shot(page, "c1-btc-after-selection");
  await capture("c1-btc.after-selection", conversationId);

  await sendTurn(page, context, "Use January 2, 2022 through January 2, 2025.", {
    conversationId,
  });
  await shot(page, "c1-btc-after-period");
  await capture("c1-btc.after-period", conversationId);
});

test("c2 non-BTC future control (NVDA golden cross)", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "If I invest $10,000 in NVDA using a golden cross strategy, how much will it be worth in ten years?",
    { conversationId: null },
  );
  await shot(page, "c2-nvda-future");
  await capture("c2-nvda-future", conversationId);
});

test("c3 unresolved-asset control (Zorbcoin)", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "If I put $5,000 into Zorbcoin, what will it become by 2031?",
    { conversationId: null },
  );
  await shot(page, "c3-zorbcoin");
  await capture("c3-zorbcoin", conversationId);
});

test("c4 Spanish future control (es-419 profile)", async ({ browser }) => {
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
    await shot(esPage, "c4-nvda-future-es");
    const { items } = await conversationMessages(esContext, conversationId);
    saveEvidence("c4-nvda-future-es.messages", {
      conversation_id: conversationId,
      items: messageDigest(items),
    });
  } finally {
    await esContext.close();
  }
});
