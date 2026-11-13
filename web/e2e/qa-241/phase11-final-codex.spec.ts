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

// Final Codex pass QA: DCA future-edit recovery must re-ask the period after
// the historical-period selection (no stale-window confirmation), plus one
// future refusal control. One attempt each; forced route shapes are owned by
// deterministic stage tests.

test.describe.configure({ mode: "serial" });

test.beforeEach(async () => {
  test.setTimeout(600_000);
});

let context: BrowserContext;
let page: Page;
let dcaConversationId: string | null = null;

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

test("f0 probe + usage baseline", async () => {
  const probe = await meProbe(context);
  expect(probe.status).toBe(200);
  expect(probe.isAdmin).toBe(false);
});

test("f1 dated DCA reaches a card", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "DCA $500 into AAPL every month from January 2, 2022 through January 2, 2024.",
    { conversationId: null },
  );
  dcaConversationId = conversationId;
  await shot(page, "f1-dca-card");
  await capture("f1-dca-card", conversationId);
});

test("f2 future edit enters future recovery", async () => {
  expect(dcaConversationId).toBeTruthy();
  await sendTurn(
    page,
    context,
    "Actually, run it over the next two years instead.",
    { conversationId: dcaConversationId },
  );
  await shot(page, "f2-dca-future-edit");
  await capture("f2-dca-future-edit", dcaConversationId as string);
});

test("f3 historical selection re-asks the period", async () => {
  expect(dcaConversationId).toBeTruthy();
  const historicalChip = page.getByRole("button", {
    name: /historical|hist[óo]ric/i,
  });
  if (await historicalChip.count()) {
    await historicalChip.first().click();
    await page.waitForTimeout(15_000);
  } else {
    await sendTurn(page, context, "Test it over a historical period.", {
      conversationId: dcaConversationId,
    });
  }
  await shot(page, "f3-after-selection");
  await capture("f3-after-selection", dcaConversationId as string);
});

test("f4 one-shot future refusal control", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "If I put $2,000 into ETH and hold it, what will it be worth in five years?",
    { conversationId: null },
  );
  await shot(page, "f4-eth-future");
  await capture("f4-eth-future", conversationId);
});

test("f9 usage after", async () => {
});
