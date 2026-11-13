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

// PR #266 review-response QA: the future-window edit corridor (finding 2)
// plus one supported historical control. One attempt each.

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

test("q0 probe + usage baseline", async () => {
  const probe = await meProbe(context);
  expect(probe.status).toBe(200);
  expect(probe.isAdmin).toBe(false);
});

test("q1 future-window edit on an active confirmation", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "Backtest $10,000 in NVDA from January 2, 2020 through December 29, 2023 using a golden cross.",
    { conversationId: null },
  );
  await shot(page, "q1-card");
  await capture("q1-card", conversationId);

  await sendTurn(
    page,
    context,
    "Change the amount to $5,000 and run it 10 years into the future.",
    { conversationId },
  );
  await shot(page, "q1-future-edit");
  await capture("q1-future-edit", conversationId);
});

test("q2 historical lookback control", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "Backtest $10,000 in AAPL over the last three years.",
    { conversationId: null },
  );
  await shot(page, "q2-lookback-control");
  await capture("q2-lookback-control", conversationId);
});

