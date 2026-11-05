import { afterEach, describe, expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReceiptBody from "../components/receipt/ReceiptBody";
import ReceiptActionBar from "../components/receipt/ReceiptActionBar";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  fetchPublicReceipt,
  headlineReceiptMetric,
  isPublicReceiptId,
  publicReceiptPath,
  type PublicReceiptPayload,
  type PublicReceiptView,
} from "../lib/public-receipt-contract";
import {
  formatReceiptDate,
  interpolate,
  receiptCopy,
  receiptLanguageFromAcceptLanguage,
} from "../lib/receipt-copy";
import { benchmarkVerdict, receiptPlan } from "../lib/receipt-plan";
import enCommon from "../public/locales/en/common.json";
import esCommon from "../public/locales/es-419/common.json";

const WEB_ROOT = join(import.meta.dir, "..");
const RECEIPT_ROUTE = join(WEB_ROOT, "app/r/[receiptId]/page.tsx");
const RECEIPT_LAYOUT = join(WEB_ROOT, "app/r/layout.tsx");
const OG_IMAGE_ROUTE = join(WEB_ROOT, "app/r/[receiptId]/opengraph-image.tsx");
const RECEIPT_BODY = join(WEB_ROOT, "components/receipt/ReceiptBody.tsx");
const ACTION_BAR = join(WEB_ROOT, "components/receipt/ReceiptActionBar.tsx");

function source(path: string): string {
  return readFileSync(path, "utf8");
}

/**
 * Structural assertions below are about code, not prose. Comments on these files
 * legitimately name the things the code must not touch (that is what the comments
 * are for), so they are stripped before scanning.
 */
function code(path: string): string {
  return source(path)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "")
    .replace(/([^:])\/\/.*$/gm, "$1");
}

/** The closed key set, read from the contract so no list is kept here by hand. */
function strategyFactKeys(): string[] {
  // Comments are stripped first: they legitimately quote the vocabulary the union
  // deliberately excludes, and a naive scan reads those quotes as members.
  const contract = code(join(WEB_ROOT, "lib/public-receipt-contract.ts"));
  const start = contract.indexOf("PublicReceiptStrategyFactKey =");
  const union = contract.slice(start, contract.indexOf(";", start));
  const keys = [...union.matchAll(/"(\w+)"/g)].map((match) => match[1]);
  if (keys.length < 10) throw new Error("strategy fact key union not parsed");
  return keys;
}

const VALID_ID = "abcdefghijklmnopqrstuvwx";

const PAYLOAD: PublicReceiptPayload = {
  schema_version: 1,
  idea_title: "AAPL buy and hold",
  asset_class: "equity",
  symbols: ["AAPL"],
  assumptions: [
    { key: "long_only" },
    { key: "equal_weight" },
    { key: "no_costs" },
    { key: "benchmark", value: "SPY" },
  ],
  date_range: { start: "2024-01-02", end: "2024-03-01" },
  metrics: [
    { key: "max_drawdown_pct", value: "-6.2%" },
    { key: "total_return_pct", value: "+18.4%" },
    { key: "benchmark_return_pct", value: "+9.1%" },
    { key: "delta_vs_benchmark_pct", value: "9.3" },
  ],
  benchmark_symbol: "SPY",
  strategy_facts: [
    { key: "indicator", value: "RSI" },
    { key: "indicator_period", value: "14" },
  ],
  visual: null,
  owner_note: null,
  content_language: "en",
  framing: "historical_simulation_not_advice",
  provenance_mark: "tested_with_argus",
};

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function stubFetch(
  responder: () => Response | Promise<Response> | never,
): void {
  globalThis.fetch = (async () => responder()) as typeof fetch;
}

describe("public receipt id", () => {
  test("accepts an unguessable token and refuses anything short or odd", () => {
    expect(isPublicReceiptId(VALID_ID)).toBe(true);
    expect(isPublicReceiptId("short")).toBe(false);
    expect(isPublicReceiptId("has spaces in it aaaaaaaaaa")).toBe(false);
    expect(isPublicReceiptId("../../etc/passwd")).toBe(false);
    expect(isPublicReceiptId("a".repeat(65))).toBe(false);
  });

  test("path prefix matches the backend contract", () => {
    expect(publicReceiptPath(VALID_ID)).toBe(`/r/${VALID_ID}`);
  });
});

describe("fetching a receipt", () => {
  test("a malformed id never reaches the network", async () => {
    let called = false;
    globalThis.fetch = (async () => {
      called = true;
      return new Response("{}", { status: 200 });
    }) as typeof fetch;
    expect(await fetchPublicReceipt("nope")).toEqual({ kind: "revoked" });
    expect(called).toBe(false);
  });

  test("an available receipt returns its frozen payload", async () => {
    const view: PublicReceiptView = {
      public_id: VALID_ID,
      status: "available",
      indexing: "noindex, nofollow",
      created_at: "2026-08-07T12:00:00Z",
      payload: PAYLOAD,
    };
    stubFetch(() => new Response(JSON.stringify(view), { status: 200 }));
    const result = await fetchPublicReceipt(VALID_ID);
    expect(result).toEqual({
      kind: "available",
      payload: PAYLOAD,
      createdAt: "2026-08-07T12:00:00Z",
    });
  });

  test("only the backend saying revoked makes a receipt revoked", async () => {
    stubFetch(
      () =>
        new Response(
          JSON.stringify({
            public_id: VALID_ID,
            status: "revoked",
            indexing: "noindex, nofollow",
          }),
          { status: 200 },
        ),
    );
    expect(await fetchPublicReceipt(VALID_ID)).toEqual({ kind: "revoked" });
  });

  test("a transient failure is never presented as a revocation", async () => {
    // Permanent and temporary are different facts. An unknown id already answers
    // 200 with status revoked, so a 404 means the endpoint is absent, which happens
    // when sharing is on here and off on the API. That is a deployment state.
    for (const status of [404, 500, 502, 503, 504]) {
      stubFetch(() => new Response("{}", { status }));
      expect(await fetchPublicReceipt(VALID_ID)).toEqual(
        { kind: "unavailable" },
      );
    }

    stubFetch(() => {
      throw new Error("network down");
    });
    expect(await fetchPublicReceipt(VALID_ID)).toEqual({ kind: "unavailable" });

    // An unrecognised shape is not evidence that anything was revoked either.
    stubFetch(() => new Response(JSON.stringify({ nonsense: true }), { status: 200 }));
    expect(await fetchPublicReceipt(VALID_ID)).toEqual({ kind: "unavailable" });
  });

  test("410 is the one status that does mean gone", async () => {
    stubFetch(() => new Response("{}", { status: 410 }));
    expect(await fetchPublicReceipt(VALID_ID)).toEqual({ kind: "revoked" });
  });

  test("the request carries no credentials and no auth header", () => {
    const contract = code(join(WEB_ROOT, "lib/public-receipt-contract.ts"));
    expect(contract).not.toContain("credentials");
    expect(contract).not.toContain("Authorization");
    expect(contract).not.toContain("getSupabaseClient");
    expect(contract).toContain('cache: "no-store"');
  });
});

describe("never indexable", () => {
  test("both the layout and the page declare noindex and nofollow", () => {
    for (const path of [RECEIPT_LAYOUT, RECEIPT_ROUTE]) {
      const body = source(path);
      expect(body).toContain("index: false");
      expect(body).toContain("follow: false");
      expect(body).toContain("googleBot");
    }
  });

  test("the preview image is marked noindex at the header level too", () => {
    const body = source(OG_IMAGE_ROUTE);
    expect(body).toContain("X-Robots-Tag");
    expect(body).toContain("noimageindex");
    expect(body).toContain("no-store");
  });

  test("no user-facing control can turn indexing on", () => {
    // A discoverability toggle is the specific failure this design exists to
    // avoid, so no such control may exist anywhere on the surface.
    for (const path of [RECEIPT_ROUTE, RECEIPT_LAYOUT, RECEIPT_BODY]) {
      const body = code(path).toLowerCase();
      expect(body).not.toContain("discoverab");
      expect(body).not.toMatch(/(?:^|[^a-z])index:\s*true/);
      expect(body).not.toContain('"index, follow"');
      expect(body).not.toContain("setrobots");
    }
  });

  test("a view is reported by the rendered page, not by reading the receipt", () => {
    // The read endpoint answers the metadata pass and the preview image too, so
    // counting there would log views for a pasted link nobody opened.
    const contract = code(join(WEB_ROOT, "lib/public-receipt-contract.ts"));
    expect(contract).not.toContain("receipt-funnel");
    expect(source(join(WEB_ROOT, "components/receipt/ReceiptViewBeacon.tsx"))).toContain(
      'reportReceiptFunnelStage("viewed", kind)',
    );
    expect(source(RECEIPT_BODY)).toContain("<ReceiptViewBeacon");
    expect(source(join(WEB_ROOT, "components/receipt/ReceiptNotice.tsx"))).not.toContain("<ReceiptViewBeacon");
    // The image never reports anything.
    expect(code(OG_IMAGE_ROUTE)).not.toContain("receipt-funnel");
  });

  test("the metadata pass and the page render share one backend read", () => {
    const contract = source(join(WEB_ROOT, "lib/public-receipt-contract.ts"));
    expect(contract).toContain("cache(fetchPublicReceipt)");
    expect(source(RECEIPT_ROUTE)).toContain("readPublicReceipt");
    expect(source(RECEIPT_ROUTE)).not.toContain("await fetchPublicReceipt");
  });

  test("an outage renders distinctly from a revocation, page and card alike", () => {
    // Platforms cache preview images and metadata, so a temporary failure dressed
    // as a permanent one would pin a revoked-looking card to a live receipt, and
    // Argus cannot clear a cache it does not own.
    const image = code(OG_IMAGE_ROUTE);
    expect(image).toContain('result.kind === "unavailable"');
    expect(image).toContain("status: 503");
    expect(image).toContain("Retry-After");
    expect(image).toContain('result.kind === "revoked"');
    // The gone card is reachable only from the revoked branch.
    expect(image.indexOf('result.kind === "unavailable"')).toBeLessThan(
      image.indexOf("copy.gone"),
    );

    const page = code(RECEIPT_ROUTE);
    expect(page).toContain('result.kind === "unavailable"');
    expect(page.indexOf('result.kind === "unavailable"')).toBeLessThan(
      page.indexOf("copy.tombstone.title"),
    );

    // The page keeps its own distinct copy for the temporary case.
    const notice = source(join(WEB_ROOT, "components/receipt/ReceiptNotice.tsx"));
    expect(notice).toContain('kind === "revoked" ? copy.tombstone : copy.unavailable');
    for (const bundle of [enCommon.receipt, esCommon.receipt]) {
      expect(bundle.unavailable.title).not.toBe(bundle.tombstone.title);
      expect(bundle.unavailable.detail).not.toBe(bundle.tombstone.detail);
    }
  });

  test("the route is never cached, so revocation lands on the next request", () => {
    const body = source(RECEIPT_ROUTE);
    expect(body).toContain('dynamic = "force-dynamic"');
    expect(body).toContain("revalidate = 0");
  });
});

describe("the preview image inherits the never-expose list", () => {
  test("it renders a named subset of the frozen payload and nothing else", () => {
    const body = source(OG_IMAGE_ROUTE);
    expect(body).toContain("PREVIEW_FIELDS");
    for (const field of ["headline_metric.value", "benchmark_verdict"]) {
      expect(body).toContain(field);
    }
  });

  test("the card publishes less than the page, on purpose", () => {
    // A 1200 pixel card lands in a chat bubble around 250 to 320 pixels wide, so
    // everything on it divides by roughly four. The title, symbols and dates were
    // unreadable at that size, and platforms render og:title as text beside the
    // image anyway, so keeping them inside the image only competed with the number.
    const body = source(OG_IMAGE_ROUTE);
    const start = body.indexOf("export const PREVIEW_FIELDS");
    const allowlist = body.slice(start, body.indexOf("] as const", start));
    for (const dropped of ["idea_title", "symbols", "date_range"]) {
      expect(allowlist).not.toContain(dropped);
    }
  });

  test("it never reads a private record and never calls a provider", () => {
    const body = code(OG_IMAGE_ROUTE).toLowerCase();
    for (const forbidden of [
      "conversation",
      "artifact",
      "memory",
      "transcript",
      "openrouter",
      "alpaca",
      "supabase",
      "owner_id",
      "owner_note",
    ]) {
      expect(body).not.toContain(forbidden);
    }
  });

  test("it carries the provenance mark and the not-advice framing", () => {
    const body = source(OG_IMAGE_ROUTE);
    expect(body).toContain("copy.provenance");
    expect(body).toContain("copy.framing");
    for (const bundle of [enCommon.receipt, esCommon.receipt]) {
      expect(bundle.provenance.length).toBeGreaterThan(0);
      expect(bundle.framing.short.length).toBeGreaterThan(0);
    }
    expect(enCommon.receipt.framing.short).toContain("Not a tip");
  });

  test("it follows the receipt's own language, not a viewer's", () => {
    // A crawler fetching the card has no language of its own, and the frozen facts
    // on the card are already in the receipt's language.
    const body = code(OG_IMAGE_ROUTE);
    expect(body).toContain("cardCopy(language)");
    expect(body).toContain("result.payload.content_language");
    expect(body).toContain("result.payload.turns[0].content_language");
    expect(body).not.toContain("accept-language");
    expect(body).not.toContain("const FRAMING");
    expect(body).not.toContain("const PROVENANCE");
  });
});

describe("the rendered page", () => {
  test("carries the provenance mark and prominent not-advice framing", () => {
    const body = source(RECEIPT_BODY);
    expect(body).toContain("copy.thread.notice");
    expect(body).toContain("ReceiptTurnContent");
    const markup = renderToStaticMarkup(createElement(ReceiptBody, { payload: PAYLOAD, createdAt: null, language: "en", copy: receiptCopy("en") }));
    expect(markup).toContain(receiptCopy("en").framing.detail);
  });

  test("renders no field outside the closed payload", () => {
    const body = source(RECEIPT_BODY);
    const referenced = [...body.matchAll(/payload\.(\w+)/g)].map(
      (match) => match[1],
    );
    const closed = new Set(Object.keys(PAYLOAD));
    expect([...new Set(referenced)].filter((key) => !closed.has(key))).toEqual([]);
  });

  test("shows no attribution: the owner is never named", () => {
    const body = source(RECEIPT_BODY).toLowerCase();
    for (const forbidden of ["display_name", "username", "avatar", "shared by"]) {
      expect(body).not.toContain(forbidden);
    }
  });
});

describe("try argus", () => {
  test("lands on bare guest entry with no carried state and no new parameter", () => {
    const body = source(ACTION_BAR);
    expect(body).toContain('href="/"');
    const markup = renderToStaticMarkup(createElement(ReceiptActionBar, { framing: "Context", action: "Continue with Argus", kind: "research_answer" }));
    expect(markup.match(/href="([^"]+)"/)?.[1]).toBe("/");
    expect(body).not.toContain("searchParams");
    expect(body).not.toContain("prefill");
  });
});

describe("headline metric", () => {
  test("prefers total return over whatever happens to be first", () => {
    expect(headlineReceiptMetric(PAYLOAD)?.key).toBe("total_return_pct");
  });

  test("falls back to the first metric, and to nothing when there are none", () => {
    const onlyDrawdown = { ...PAYLOAD, metrics: [PAYLOAD.metrics[0]] };
    expect(headlineReceiptMetric(onlyDrawdown)?.key).toBe("max_drawdown_pct");
    expect(headlineReceiptMetric({ ...PAYLOAD, metrics: [] })).toBeNull();
  });
});

describe("viewer language", () => {
  test("reads the request rather than a stored preference", () => {
    expect(receiptLanguageFromAcceptLanguage(null)).toBe("en");
    expect(receiptLanguageFromAcceptLanguage("en-GB,en;q=0.9")).toBe("en");
    expect(receiptLanguageFromAcceptLanguage("de-DE,de;q=0.9")).toBe("en");
  });

  test("both languages have the whole receipt namespace", () => {
    const flatten = (node: unknown, prefix = ""): string[] => {
      if (typeof node !== "object" || node === null) return [prefix];
      return Object.entries(node as Record<string, unknown>).flatMap(
        ([key, value]) => flatten(value, prefix ? `${prefix}.${key}` : key),
      );
    };
    expect(flatten(esCommon.receipt).sort()).toEqual(
      flatten(enCommon.receipt).sort(),
    );
  });

  test("no em dash in receipt copy, in either language", () => {
    for (const bundle of [enCommon.receipt, esCommon.receipt]) {
      expect(JSON.stringify(bundle)).not.toContain("—");
    }
  });

  test("copy resolves and interpolates", () => {
    expect(receiptCopy("en").provenance).toBe("Tested with Cuadrao");
    expect(
      interpolate(receiptCopy("en").frozen_note, { date: "August 7, 2026" }),
    ).toContain("August 7, 2026");
  });

  test("a missing or unparseable date degrades to the undated note", () => {
    expect(formatReceiptDate(null, "en")).toBeNull();
    expect(formatReceiptDate("not-a-date", "en")).toBeNull();
    expect(formatReceiptDate("2026-08-07T12:00:00Z", "en")).toBe("August 7, 2026");
  });
});

describe("the strategy a receipt shows", () => {
  test("the rules shown are composed from the frozen facts", () => {
    const plan = source(join(WEB_ROOT, "lib/receipt-plan.ts"));
    expect(plan).toContain("payload.strategy_facts");
    expect(source(join(WEB_ROOT, "components/receipt/ReceiptTurnContent.tsx"))).toContain("plan.rows.map");
  });

  test("labels are the viewer's language and values stay frozen", () => {
    // Freezing an English label would put untranslatable chrome in the payload.
    // Keys come from the contract rather than a list kept here by hand, because a
    // hand-kept list is what let a crossover ship with no window labels: adding a
    // key to the union now fails until both languages can render it.
    for (const bundle of [enCommon.receipt, esCommon.receipt]) {
      for (const key of strategyFactKeys()) {
        expect(
          (bundle.strategy_facts as Record<string, string>)[key]?.length,
        ).toBeGreaterThan(0);
      }
      // Direction is not published, so a label for it would be dead copy.
      expect(
        (bundle.strategy_facts as Record<string, string>).direction,
      ).toBeUndefined();
    }
    expect(enCommon.receipt.strategy_facts.indicator).not.toBe(
      esCommon.receipt.strategy_facts.indicator,
    );
  });

  test("the frozen key set matches the backend enum exactly", () => {
    // Two enums that have to agree. A key the backend can freeze but the page
    // cannot name would render as a raw identifier on a public page.
    const schema = source(
      join(WEB_ROOT, "../src/argus/api/public_excerpt_schemas.py"),
    ).replace(/^\s*#.*$/gm, "");
    const start = schema.indexOf("StrategyFactKey = Literal[");
    const literal = schema.slice(start, schema.indexOf("]", start));
    const backend = [...literal.matchAll(/"(\w+)"/g)].map((match) => match[1]);
    expect([...strategyFactKeys()].sort()).toEqual([...backend].sort());
  });
});

describe("a view is only counted when a receipt was shown", () => {
  test("the outage notice does not fire the beacon", () => {
    const notice = source(join(WEB_ROOT, "components/receipt/ReceiptNotice.tsx"));
    expect(notice).not.toContain("<ReceiptViewBeacon");
    expect(notice).toContain("kind={null}");
  });
});

describe("the public route escapes the client i18n gate", () => {
  test("so a shared link is not blank without JavaScript", () => {
    // The gate returns a placeholder instead of children until i18n initialises,
    // which left the initial HTML empty and the page permanently blank with JS off.
    const provider = source(join(WEB_ROOT, "components/I18nProvider.tsx"));
    expect(provider).toContain("PUBLIC_RECEIPT_PATH_PREFIX");
    expect(provider).toContain("!isInitialized && !rendersWithoutI18n");
    // The receipt surface consumes no i18next resources, which is what makes this safe.
    for (const file of [
      "components/receipt/ReceiptBody.tsx",
      "components/receipt/ReceiptNotice.tsx",
      "components/receipt/ReceiptActionBar.tsx",
      "components/receipt/ProvenanceMark.tsx",
    ]) {
      expect(source(join(WEB_ROOT, file))).not.toContain("useTranslation");
    }
  });
});

describe("the strategy name a receipt renders", () => {
  test("is composed from the executed facts, never from a frozen label", () => {
    // The label and the name were frozen from different records: the label from the
    // result card, the name from the run's own config. The label is gone from the
    // payload entirely now, because it was also written in the author's language.
    // Even the fallback for a shape with no sentence of its own reads the closed
    // strategy_type token and translates it.
    const plan = source(join(WEB_ROOT, "lib/receipt-plan.ts"));
    expect(plan).not.toContain("strategy_label");
    expect(plan).toContain("plan.unnamed");
    expect(plan).toContain("strategy_type_values");
    expect(source(join(WEB_ROOT, "lib/public-receipt-contract.ts"))).not.toContain(
      "strategy_label",
    );
  });
});

describe("the plan sentence", () => {
  const copy = receiptCopy("en");
  const spanish = receiptCopy("es-419");

  function withFacts(
    facts: PublicReceiptPayload["strategy_facts"],
  ): PublicReceiptPayload {
    return { ...PAYLOAD, strategy_facts: facts };
  }

  test("states a crossover's entry and its mirrored exit in words", () => {
    const { rows, settings } = receiptPlan(
      withFacts([
        { key: "strategy_type", value: "moving average crossover" },
        { key: "fast_indicator", value: "sma" },
        { key: "fast_period", value: "20" },
        { key: "slow_indicator", value: "sma" },
        { key: "slow_period", value: "50" },
      ]),
      copy,
    );
    expect(rows[0].text).toBe(
      "Bought when the 20 day average rose above the 50 day average.",
    );
    // The indicator names live on the exact line, so the sentence stays readable.
    expect(rows[0].exact).toBe("SMA 20 · SMA 50");
    expect(rows[1].text).toBe("Sold when it crossed back below.");
    // A mirrored exit has no parameters of its own to state.
    expect(rows[1].exact).toBeNull();
    expect(settings).toHaveLength(4);
  });

  test("states a differing exit as its own sentence", () => {
    const { rows } = receiptPlan(
      withFacts([
        { key: "strategy_type", value: "moving average crossover" },
        { key: "fast_indicator", value: "sma" },
        { key: "fast_period", value: "20" },
        { key: "slow_indicator", value: "sma" },
        { key: "slow_period", value: "50" },
        { key: "exit_fast_indicator", value: "ema" },
        { key: "exit_fast_period", value: "9" },
        { key: "exit_slow_indicator", value: "ema" },
        { key: "exit_slow_period", value: "21" },
      ]),
      copy,
    );
    expect(rows[1].text).toBe(
      "Sold when the 9 day average fell below the 21 day average.",
    );
    expect(rows[1].exact).toBe("EMA 9 · EMA 21");
  });

  test("splits an indicator threshold into its buy and its sell", () => {
    const { rows } = receiptPlan(
      withFacts([
        { key: "strategy_type", value: "rsi threshold" },
        { key: "indicator", value: "RSI" },
        { key: "indicator_period", value: "14" },
        { key: "entry_threshold", value: "30" },
        { key: "exit_threshold", value: "70" },
      ]),
      copy,
    );
    expect(rows).toHaveLength(2);
    expect(rows[0].text).toBe("Bought when RSI fell to 30.");
    expect(rows[0].exact).toBe("RSI 14");
    expect(rows[1].text).toBe("Sold when RSI climbed back to 70.");
  });

  test("a strategy that never sells says so and stops at one rule", () => {
    // buy_and_hold and dca_accumulation both set every exit to false in the engine,
    // so there is no sell rule to describe and no empty half to fill.
    const held = receiptPlan(
      withFacts([{ key: "strategy_type", value: "buy and hold" }]),
      copy,
    );
    expect(held.rows).toHaveLength(1);
    expect(held.rows[0].text).toContain("never sold");

    const recurring = receiptPlan(
      withFacts([
        { key: "strategy_type", value: "dca accumulation" },
        { key: "cadence", value: "monthly" },
      ]),
      copy,
    );
    expect(recurring.rows).toHaveLength(1);
    expect(recurring.rows[0].text).toBe(
      "Bought every month, whatever the price was that day. It never sold.",
    );
    // The cadence is the subject of the sentence, so restating it would repeat.
    expect(recurring.rows[0].exact).toBeNull();
  });

  test("reads in the viewer's language while the values stay frozen", () => {
    const { rows } = receiptPlan(
      withFacts([
        { key: "strategy_type", value: "dca accumulation" },
        { key: "cadence", value: "monthly" },
      ]),
      spanish,
    );
    expect(rows[0].text).toBe(
      "Compró cada mes, sin importar el precio de ese día. Nunca vendió.",
    );
  });

  test("the comparison is stated as a verdict, not left as two numbers", () => {
    const ahead = {
      ...PAYLOAD,
      metrics: [
        { key: "total_return_pct", value: "+18.4%" },
        { key: "benchmark_return_pct", value: "+9.1%" },
      ],
    } satisfies PublicReceiptPayload;
    expect(benchmarkVerdict(ahead, copy)).toBe("9.3 pts ahead of SPY");
    const behind = {
      ...PAYLOAD,
      metrics: [
        { key: "total_return_pct", value: "+2.0%" },
        { key: "benchmark_return_pct", value: "+9.1%" },
      ],
    } satisfies PublicReceiptPayload;
    expect(benchmarkVerdict(behind, copy)).toBe("7.1 pts behind SPY");
  });

  test("states the difference of the two shown returns, even beside an older frozen delta", () => {
    // A receipt frozen before one owner stated the gap carries the engine's 9.4
    // beside +18.4% and +9.1%; the page states the 9.3 those figures show.
    const frozen = {
      ...PAYLOAD,
      metrics: [
        { key: "total_return_pct", value: "+18.4%" },
        { key: "benchmark_return_pct", value: "+9.1%" },
        { key: "delta_vs_benchmark_pct", value: "9.4" },
      ],
    } satisfies PublicReceiptPayload;
    expect(benchmarkVerdict(frozen, copy)).toBe("9.3 pts ahead of SPY");
    const withoutHeadline = {
      ...PAYLOAD,
      metrics: [
        { key: "benchmark_return_pct", value: "+9.1%" },
        { key: "delta_vs_benchmark_pct", value: "-9.4" },
      ],
    } satisfies PublicReceiptPayload;
    expect(benchmarkVerdict(withoutHeadline, copy)).toBe("9.4 pts behind SPY");
  });

  test("says nothing when the payload names no benchmark at all", () => {
    // A payload that names one always carries its numbers: the projection refuses
    // to freeze a benchmark symbol it has no figure for.
    const unbenchmarked = {
      ...PAYLOAD,
      benchmark_symbol: null,
    } satisfies PublicReceiptPayload;
    expect(benchmarkVerdict(unbenchmarked, copy)).toBeNull();
  });

  test("says nothing rather than guessing when a figure will not parse", () => {
    const unparseable = {
      ...PAYLOAD,
      benchmark_symbol: null,
      metrics: [{ key: "total_return_pct", value: "n/a" }],
    };
    expect(benchmarkVerdict(unparseable, copy)).toBeNull();
  });
});

describe("the action bar", () => {
  test("is fixed to the bottom and clears the iOS home indicator", () => {
    const bar = source(ACTION_BAR);
    expect(bar).toContain("fixed inset-x-0 bottom-0");
    expect(bar).toContain("pb-[env(safe-area-inset-bottom)]");
    // env() reports zero unless the viewport opts into the full screen, so the
    // inset handling above is dead without this.
    expect(source(RECEIPT_LAYOUT)).toContain('viewportFit: "cover"');
  });

  test("never ships the button without the framing attached", () => {
    // A permanently visible call to action on a page a stranger did not ask for is
    // only acceptable paired with what the page actually is.
    const bar = source(ACTION_BAR);
    expect(bar).toContain("framing");
    // Not optional and not defaulted: the prop is required by the type.
    expect(bar).toContain("framing: string;");
    expect(bar).not.toContain("framing?");
    for (const surface of [join(WEB_ROOT, "components/receipt/ReceiptNotice.tsx")]) {
      expect(source(surface)).toContain("copy.framing.headline");
    }
  });

  test("the clearance constant does not live in a client module", () => {
    // A "use client" module turns every export into a client reference, so a server
    // component importing a plain string from it gets a stub. The stub stringifies
    // into the class attribute as a JavaScript error message and the padding never
    // applies, which is invisible to a source scan and visible in the rendered page.
    // Comments stripped: this module documents the directive it must not carry.
    const layout = code(join(WEB_ROOT, "lib/receipt-layout.ts"));
    expect(layout).toContain("RECEIPT_ACTION_BAR_CLEARANCE");
    expect(layout).not.toContain("use client");
    expect(code(ACTION_BAR)).not.toContain("RECEIPT_ACTION_BAR_CLEARANCE");
  });

  test("the clearance is valid CSS calc, spaces and all", () => {
    // calc() requires whitespace around its operators, and Tailwind writes that as
    // an underscore. Without it the declaration is dropped silently.
    const layout = source(join(WEB_ROOT, "lib/receipt-layout.ts"));
    expect(layout).toContain("calc(112px_+_env(safe-area-inset-bottom))");
  });

  test("the tombstone leaves room for its fixed bar while the thread has an in-flow composer", () => {
    // A page that renders the bar without the clearance hides its own last line,
    // and two hand-copied paddings would drift.
    for (const surface of [join(WEB_ROOT, "components/receipt/ReceiptNotice.tsx")]) {
      const body = source(surface);
      expect(body).toContain("RECEIPT_ACTION_BAR_CLEARANCE");
      expect(body).not.toContain("pb-14");
      expect(body).not.toContain("pb-16");
    }
    expect(source(ACTION_BAR)).toContain("pb-[env(safe-area-inset-bottom)]");
  });

  test("its position owes nothing to JavaScript", () => {
    // No scroll listener and no reveal, so it cannot behave differently before
    // hydration than after it. The click beacon is the funnel contract and stays.
    const bar = code(ACTION_BAR);
    for (const forbidden of [
      "addEventListener",
      "useEffect",
      "useState",
      "scrollY",
      "IntersectionObserver",
    ]) {
      expect(bar).not.toContain(forbidden);
    }
    expect(bar).toContain("reportReceiptFunnelStage");
  });

  test("the tombstone gets it too", () => {
    const notice = source(join(WEB_ROOT, "components/receipt/ReceiptNotice.tsx"));
    expect(notice).toContain("ReceiptActionBar");
  });

  test("the in-flow call to action block is gone from both surfaces", () => {
    // It was about 200px on every page and put the only action 1.4 screens down.
    for (const surface of [RECEIPT_BODY, join(WEB_ROOT, "components/receipt/ReceiptNotice.tsx")]) {
      const body = source(surface);
      expect(body).not.toContain("TryArgusCallToAction");
      expect(body).not.toContain("copy.cta.headline");
      expect(body).not.toContain("copy.cta.detail");
    }
  });

  test("the framing on the bar is not the paragraph already in flow", () => {
    // Layered, not duplicated: the in-flow block explains what the page is, the bar
    // carries the standing caveat.
    for (const bundle of [enCommon.receipt, esCommon.receipt]) {
      expect(bundle.framing.headline).not.toBe(bundle.framing.detail);
      expect(bundle.framing.headline.length).toBeLessThan(
        bundle.framing.detail.length,
      );
    }
    // And the in-flow block no longer repeats the headline the bar now carries.
    expect(source(RECEIPT_BODY)).not.toContain("copy.framing.headline}{\" \"}");
    const markup = renderToStaticMarkup(createElement(ReceiptBody, { payload: PAYLOAD, createdAt: null, language: "en", copy: receiptCopy("en") }));
    expect(markup).toContain(receiptCopy("en").framing.detail);
  });
});
