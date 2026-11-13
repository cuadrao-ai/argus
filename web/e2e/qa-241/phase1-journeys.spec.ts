import { test, expect, type BrowserContext, type Page } from "@playwright/test";
import { identities, loginViaUi } from "../qa-248/helpers";
import {
  conversationMessages,
  historySnapshot,
  meProbe,
  messageDigest,
  saveEvidence,
  sendTurn,
  shot,
  startNewChat,
} from "./j241.helpers";

// Phase 1 reproduction driver for issue #241 (capability truth) at the exact
// integration head. Capture-first: journeys record durable evidence; only the
// mechanics needed to keep the run coherent are asserted here. Verdicts against
// the locked design spec are derived from the captured evidence afterward.

const FACTS_EN = "$10,000 in AAPL from January 2, 2022 through January 2, 2025";

test.describe.configure({ mode: "serial" });

test.beforeEach(async () => {
  test.setTimeout(600_000);
});

let context: BrowserContext;
let page: Page;

async function captureJourney(
  tag: string,
  conversationId: string,
) {
  const { items } = await conversationMessages(context, conversationId);
  saveEvidence(`${tag}.messages`, {
    conversation_id: conversationId,
    captured_at: new Date().toISOString(),
    items: messageDigest(items),
  });
}

async function reloadAndCapture(tag: string, conversationId: string) {
  await page.reload();
  await page.waitForTimeout(4_000);
  await shot(page, `${tag}-after-reload`);
  await captureJourney(`${tag}.after-reload`, conversationId);
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

test("00 login + account probe", async () => {
  const probe = await meProbe(context);
  console.log(
    `me.status=${probe.status} is_admin=${probe.isAdmin} language=${probe.language}`,
  );
  expect(probe.status).toBe(200);
  expect(probe.isAdmin).toBe(false);
  saveEvidence("00-account-probe", {
    status: probe.status,
    is_admin: probe.isAdmin,
    language: probe.language,
  });
  saveEvidence("00-history-before", await historySnapshot(context));
});

test("01 golden cross control (EN)", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(page, context, `Backtest ${FACTS_EN} using a golden cross.`, {
    conversationId: null,
  });
  await shot(page, "01-golden-cross-turn1");
  await captureJourney("01-golden-cross", conversationId);
  await reloadAndCapture("01-golden-cross", conversationId);
});

test("02 momentum breakout (EN) + reload + explicit selection", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    `Backtest ${FACTS_EN} using a momentum breakout strategy.`,
    { conversationId: null },
  );
  await shot(page, "02-momentum-turn1");
  await captureJourney("02-momentum", conversationId);
  await reloadAndCapture("02-momentum", conversationId);

  // Explicit typed selection: prefer a visible option chip; otherwise select in words.
  const crossoverChip = page.getByRole("button", {
    name: /moving.average|crossover|cruce/i,
  });
  if (await crossoverChip.count()) {
    await crossoverChip.first().click();
    await page.waitForTimeout(12_000);
  } else {
    await sendTurn(page, context, "Use the supported moving-average crossover instead.", {
      conversationId,
    });
  }
  await shot(page, "02-momentum-after-selection");
  await captureJourney("02-momentum.after-selection", conversationId);
});

test("03 news sentiment rule (EN)", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    `Backtest ${FACTS_EN}, buying when news sentiment turns positive and selling when it turns negative.`,
    { conversationId: null },
  );
  await shot(page, "03-news-sentiment-turn1");
  await captureJourney("03-news-sentiment", conversationId);
  await reloadAndCapture("03-news-sentiment", conversationId);
});

test("04 future performance (EN, NVDA) + selection + period ask", async () => {
  await startNewChat(page);
  const { conversationId } = await sendTurn(
    page,
    context,
    "If I invest $10,000 in NVDA using a golden cross strategy, how much will it be worth in ten years?",
    { conversationId: null },
  );
  await shot(page, "04-future-nvda-turn1");
  await captureJourney("04-future-nvda", conversationId);
  await reloadAndCapture("04-future-nvda", conversationId);

  // Explicit historical-path selection, in words (typed chip preferred when present).
  const historicalChip = page.getByRole("button", {
    name: /historical|hist[óo]ric|backtest|buy and hold|crossover/i,
  });
  if (await historicalChip.count()) {
    await historicalChip.first().click();
    await page.waitForTimeout(12_000);
  } else {
    await sendTurn(page, context, "Yes, run the historical test.", { conversationId });
  }
  await shot(page, "04-future-nvda-after-selection");
  await captureJourney("04-future-nvda.after-selection", conversationId);

  // If Argus asked for a historical period, supply one and observe the draft.
  await sendTurn(page, context, "Use January 2, 2022 through January 2, 2025.", {
    conversationId,
  });
  await shot(page, "04-future-nvda-after-period");
  await captureJourney("04-future-nvda.after-period", conversationId);
});

test("05+06 Spanish journeys on the es-419 profile", async ({ browser }) => {
  const ids = identities();
  const esContext = await browser.newContext();
  const esPage = await esContext.newPage();
  try {
    await loginViaUi(esPage, ids.secondEmail, ids.secondPassword);
    const probe = await meProbe(esContext);
    console.log(`es-profile me.status=${probe.status} is_admin=${probe.isAdmin} language=${probe.language}`);
    expect(probe.status).toBe(200);
    expect(probe.isAdmin).toBe(false);

    await startNewChat(esPage);
    const future = await sendTurn(
      esPage,
      esContext,
      "Si invierto $10,000 en NVDA con una estrategia de cruce dorado, ¿cuánto tendré dentro de diez años?",
      { conversationId: null },
    );
    await shot(esPage, "05-future-nvda-es-turn1");
    const futureItems = await conversationMessages(esContext, future.conversationId);
    saveEvidence("05-future-nvda-es.messages", {
      conversation_id: future.conversationId,
      items: messageDigest(futureItems.items),
    });
    await esPage.reload();
    await esPage.waitForTimeout(4_000);
    await shot(esPage, "05-future-nvda-es-after-reload");
    const reloaded = await conversationMessages(esContext, future.conversationId);
    saveEvidence("05-future-nvda-es.after-reload.messages", {
      conversation_id: future.conversationId,
      items: messageDigest(reloaded.items),
    });

    await startNewChat(esPage);
    const sentiment = await sendTurn(
      esPage,
      esContext,
      "Prueba $10,000 en AAPL del 2 de enero de 2022 al 2 de enero de 2025, comprando cuando el sentimiento de las noticias sea positivo y vendiendo cuando sea negativo.",
      { conversationId: null },
    );
    await shot(esPage, "06-news-sentiment-es-turn1");
    const sentimentItems = await conversationMessages(
      esContext,
      sentiment.conversationId,
    );
    saveEvidence("06-news-sentiment-es.messages", {
      conversation_id: sentiment.conversationId,
      items: messageDigest(sentimentItems.items),
    });
  } finally {
    await esContext.close();
  }
});

test("07 future variants: basket, no capital, unresolved asset", async () => {
  await startNewChat(page);
  const first = await sendTurn(
    page,
    context,
    "What will a basket of NVDA and MSFT be worth in five years if I put in $2,000 each?",
    { conversationId: null },
  );
  await shot(page, "07-future-basket");
  await captureJourney("07-future-basket", first.conversationId);

  await startNewChat(page);
  const second = await sendTurn(
    page,
    context,
    "How much money would I make over the next three years holding Tesla?",
    { conversationId: null },
  );
  await shot(page, "07-future-no-capital");
  await captureJourney("07-future-no-capital", second.conversationId);

  await startNewChat(page);
  const third = await sendTurn(
    page,
    context,
    "If I put $5,000 into Zorbcoin, what will it become by 2031?",
    { conversationId: null },
  );
  await shot(page, "07-future-unresolved-asset");
  await captureJourney("07-future-unresolved-asset", third.conversationId);
});

test("99 usage + history after journeys", async () => {
  saveEvidence("99-history-after", await historySnapshot(context));
});
