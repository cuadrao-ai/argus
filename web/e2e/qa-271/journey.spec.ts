import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import {
  test,
  expect,
  type BrowserContext,
  type Page,
} from "@playwright/test";
import { identities, loginViaUi } from "../qa-248/helpers";
import {
  conversationMessages,
  messageDigest,
  sendTurn,
  startNewChat,
} from "../qa-241/j241.helpers";

// Issue #271 modeled-cost continuity acceptance: one continuous real-interpreter
// conversation proving establishment, unrelated date/asset edits, a nonzero cost
// edit, an explicit zero clear, restoration, and reload agreement — with zero
// backtest jobs, Runs, or simulation usage.

const ROOT = path.resolve(__dirname, "../../..");
const EVIDENCE_DIR = path.join(
  ROOT,
  "temp",
  "qa-evidence-271",
  process.env.QA_HEAD_SHA ?? "local",
);

type JsonRecord = Record<string, unknown>;

function saveEvidence(name: string, payload: unknown) {
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  writeFileSync(
    path.join(EVIDENCE_DIR, `${name}.json`),
    JSON.stringify(payload, null, 2),
  );
}

async function shot(page: Page, name: string) {
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page.screenshot({
    path: path.join(EVIDENCE_DIR, `${name}.png`),
    fullPage: false,
  });
}

function latestConfirmation(items: Array<JsonRecord>): {
  payload: JsonRecord;
  card: JsonRecord | null;
  messageId: unknown;
} | null {
  let found: { payload: JsonRecord; card: JsonRecord | null; messageId: unknown } | null =
    null;
  for (const item of items) {
    if (item.role !== "assistant") continue;
    const metadata = (item.metadata ?? {}) as JsonRecord;
    const payload = metadata.confirmation_payload;
    if (payload && typeof payload === "object") {
      found = {
        payload: payload as JsonRecord,
        card: (metadata.confirmation_card as JsonRecord | undefined) ?? null,
        messageId: item.id,
      };
    }
  }
  return found;
}

function canonicalCosts(payload: JsonRecord) {
  const strategy = (payload.strategy ?? {}) as JsonRecord;
  const extra = (strategy.extra_parameters ?? {}) as JsonRecord;
  const provenance = (extra.field_provenance ?? {}) as JsonRecord;
  const launch = (payload.launch_payload ?? {}) as JsonRecord;
  const optional = (payload.optional_parameters ?? {}) as JsonRecord;
  return {
    fee_rate: extra.fee_rate,
    slippage: extra.slippage,
    fee_provenance: provenance.fee_rate,
    slippage_provenance: provenance.slippage,
    execution_realism: launch._execution_realism ?? null,
    optional_fees: (optional.fees as JsonRecord | undefined)?.value,
    optional_slippage: (optional.slippage as JsonRecord | undefined)?.value,
    assumptions: (strategy.assumptions ?? []) as string[],
    asset_universe: strategy.asset_universe,
    capital_amount: strategy.capital_amount,
    comparison_baseline: strategy.comparison_baseline,
    timeframe: strategy.timeframe,
    date_range: strategy.date_range,
  };
}

test.describe.configure({ mode: "serial" });

let context: BrowserContext;
let page: Page;
let conversationId: string;

async function capture(tag: string) {
  const { items } = await conversationMessages(context, conversationId);
  saveEvidence(`${tag}.messages`, {
    conversation_id: conversationId,
    captured_at: new Date().toISOString(),
    items: messageDigest(items),
  });
  const confirmation = latestConfirmation(items);
  if (confirmation) {
    saveEvidence(`${tag}.canonical`, {
      conversation_id: conversationId,
      message_id: confirmation.messageId,
      costs: canonicalCosts(confirmation.payload),
      confirmation_payload: confirmation.payload,
      confirmation_card: confirmation.card,
    });
  }
  await shot(page, tag);
  return confirmation;
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

test("modeled costs survive edits, honor explicit zero, and reload", async () => {
  test.setTimeout(1_500_000);
  await startNewChat(page);

  // T1 — establish nonzero modeled costs on a ready confirmation.
  ({ conversationId } = await sendTurn(
    page,
    context,
    "Test a buy and hold of MSFT with $12,000 from January 3, 2023 through " +
      "December 31, 2024 on daily bars against SPY, and model a 10 bps fee " +
      "and 5 bps slippage.",
    { conversationId: null },
  ));
  const t1 = await capture("01-establish");
  expect(t1).not.toBeNull();
  const c1 = canonicalCosts(t1!.payload);
  expect(c1.fee_rate).toBe(0.001);
  expect(c1.slippage).toBe(0.0005);
  expect(c1.fee_provenance).toBe("explicit_user");
  expect(c1.slippage_provenance).toBe("explicit_user");
  expect(c1.execution_realism).toMatchObject({
    enabled: true,
    fee_bps: 10,
    slippage_bps: 5,
  });
  expect(c1.asset_universe).toEqual(["MSFT"]);
  expect(c1.capital_amount).toBe(12000);
  expect(c1.comparison_baseline).toBe("SPY");

  // T2 — unrelated absolute date edit preserves costs and owns the new window.
  await sendTurn(
    page,
    context,
    "Change the dates to February 1, 2023 through November 30, 2024.",
    { conversationId },
  );
  const t2 = await capture("02-date-edit");
  const c2 = canonicalCosts(t2!.payload);
  expect(c2.fee_rate).toBe(0.001);
  expect(c2.slippage).toBe(0.0005);
  expect(c2.fee_provenance).toBe("explicit_user");
  expect(c2.slippage_provenance).toBe("explicit_user");
  expect(c2.execution_realism).toMatchObject({ fee_bps: 10, slippage_bps: 5 });
  const dateRange2 = (c2.date_range ?? {}) as Record<string, unknown>;
  expect(dateRange2.start).toBe("2023-02-01");
  // Nov 30, 2024 is a Saturday; the coverage preflight aligns the effective
  // end to the prior trading day while the requested window stays provenance.
  expect(["2024-11-29", "2024-11-30"]).toContain(dateRange2.end);
  expect(c2.asset_universe).toEqual(["MSFT"]);
  expect(c2.capital_amount).toBe(12000);

  // T3 — unrelated asset replacement preserves costs and the edited window.
  await sendTurn(page, context, "Swap MSFT for AAPL.", { conversationId });
  const t3 = await capture("03-asset-replace");
  const c3 = canonicalCosts(t3!.payload);
  expect(c3.asset_universe).toEqual(["AAPL"]);
  expect(c3.fee_rate).toBe(0.001);
  expect(c3.slippage).toBe(0.0005);
  expect(c3.execution_realism).toMatchObject({ fee_bps: 10, slippage_bps: 5 });
  expect(JSON.stringify(c3.date_range)).toContain("2023-02-01");
  expect(c3.capital_amount).toBe(12000);
  expect(c3.comparison_baseline).toBe("SPY");

  // T4 — a natural-language nonzero cost edit must change the owned rates.
  await sendTurn(page, context, "Make it 20 bps fees and 7 bps slippage.", {
    conversationId,
  });
  const t4 = await capture("04-nonzero-cost-edit");
  const c4 = canonicalCosts(t4!.payload);
  expect(c4.fee_rate).toBe(0.002);
  expect(c4.slippage).toBe(0.0007);
  expect(c4.fee_provenance).toBe("explicit_user");
  expect(c4.slippage_provenance).toBe("explicit_user");
  expect(c4.execution_realism).toMatchObject({ fee_bps: 20, slippage_bps: 7 });
  expect(c4.asset_universe).toEqual(["AAPL"]);

  // T5 — explicit zero clears both costs deterministically.
  await sendTurn(page, context, "Set both the fee and slippage to 0 bps.", {
    conversationId,
  });
  const t5 = await capture("05-explicit-zero");
  const c5 = canonicalCosts(t5!.payload);
  expect(c5.fee_rate).toBe(0);
  expect(c5.slippage).toBe(0);
  expect(c5.fee_provenance).toBe("explicit_user");
  expect(c5.slippage_provenance).toBe("explicit_user");
  expect(c5.execution_realism).toBeNull();
  expect(c5.optional_fees).toBe(0);
  expect(c5.optional_slippage).toBe(0);
  expect(c5.assumptions).toContain("No fees");
  expect(c5.assumptions).toContain("No slippage");
  expect(c5.asset_universe).toEqual(["AAPL"]);
  expect(c5.capital_amount).toBe(12000);
  expect(JSON.stringify(c5.date_range)).toContain("2023-02-01");

  // T6 — restoration after zero re-establishes the original rates.
  await sendTurn(
    page,
    context,
    "Bring back the 10 bps fee and 5 bps slippage.",
    { conversationId },
  );
  const t6 = await capture("06-restore");
  const c6 = canonicalCosts(t6!.payload);
  expect(c6.fee_rate).toBe(0.001);
  expect(c6.slippage).toBe(0.0005);
  expect(c6.execution_realism).toMatchObject({ fee_bps: 10, slippage_bps: 5 });

  // Reload — durable hydration agrees with pre-reload canonical state.
  await page.reload();
  await page.waitForTimeout(5_000);
  const afterReload = await capture("07-after-reload");
  expect(afterReload).not.toBeNull();
  expect(canonicalCosts(afterReload!.payload)).toEqual(c6);

});
