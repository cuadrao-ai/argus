import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { formattedSourceDate } from "../components/chat/DiscoverySourcesPanel";
import { markComposerActionsInactive } from "../components/chat/chat-message-projection";
import { discoveryCandidateMention } from "../lib/chat-discovery-sidecar";

const root = join(import.meta.dir, "..");

const row = readFileSync(join(root, "components/chat/NextMoveRow.tsx"), "utf-8");
const message = readFileSync(
  join(root, "components/chat/ChatMessage.tsx"),
  "utf-8",
);
const panel = readFileSync(
  join(root, "components/chat/DiscoverySourcesPanel.tsx"),
  "utf-8",
);
const sourcesList = readFileSync(
  join(root, "components/chat/ResearchSourcesList.tsx"),
  "utf-8",
);
const chat = readFileSync(
  join(root, "components/chat/ChatInterface.tsx"),
  "utf-8",
);
const en = JSON.parse(
  readFileSync(join(root, "public/locales/en/common.json"), "utf-8"),
);
const es = JSON.parse(
  readFileSync(join(root, "public/locales/es-419/common.json"), "utf-8"),
);

describe("next-move row anatomy", () => {
  test("rest state is boxless and hover brightens the arrow and title together", () => {
    // No wash, no box, no shadow: hover is color emphasis only.
    expect(row).not.toContain("bg-black/5");
    expect(row).not.toContain("border-transparent");
    expect(row).not.toContain("shadow-");
    // Arrow and title tint together with the palette teal token, both themes.
    expect(row).toContain("group-hover/next-move:text-[#5ba897]");
    expect(row).toContain("group-active/next-move:text-[#5ba897]");
    expect(row).toContain("export function NextMoveTitle");
  });

  test("hit area spans the column and stays tappable regardless of the visible box", () => {
    expect(row).toContain("min-h-11");
    expect(row).toContain("w-full");
    expect(row).toContain("text-start");
  });

  test("the affordance glyph is decorative and mirrors for RTL locales", () => {
    expect(row).toContain('aria-hidden="true"');
    expect(row).toContain("rtl:-scale-x-100");
  });

  test("text wraps instead of clipping, including scripts without spaces", () => {
    expect(row).toContain("[overflow-wrap:anywhere]");
    expect(row).not.toContain("truncate");
    expect(row).not.toContain("whitespace-nowrap");
  });
});

describe("discovery candidates render as rows", () => {
  test("reason text is visible rather than hidden in a hover tooltip", () => {
    expect(message).toContain("<NextMoveDetail>{candidate.reason_text}</NextMoveDetail>");
    expect(message).not.toContain("title={candidate.reason_text");
  });

  test("separators are their own nodes so locales can restyle them", () => {
    expect(message).toContain("<NextMoveSeparator>·</NextMoveSeparator>");
    expect(message).toContain("<NextMoveSeparator>·</NextMoveSeparator>");
  });

  test("the tap payload is unchanged by the presentation swap", () => {
    expect(message).toContain('type: "select_discovery_candidate"');
    expect(message).toContain('labelKey: "chat.discovery_results.test_candidate"');
    expect(message).toContain("symbol: candidate.symbol");
    expect(message).toContain("name: candidate.name");
  });
});

describe("next moves answer the newest question only", () => {
  test("rows require the latest message and the conversation-level gate", () => {
    const gate = message.slice(
      message.indexOf("const showNextMoveRows ="),
      message.indexOf("const displayContent"),
    );
    expect(gate).toContain("Boolean(isLatest)");
    expect(gate).toContain("nextMovesEnabled");
  });

  test("card-scoped actions never become conversational rows", () => {
    expect(message).toContain("!actionHasCardScopedOwnership(action)");
  });

  test("persistent discovery rows obey the same in-flight lock as the composer", () => {
    // Discovery rows deliberately survive on older messages, so the per-message
    // streaming flag does not cover them. Without the shared lock they would be
    // a way to fire turns while one is already running.
    expect(chat).toContain("const turnInFlight =");
    expect(chat).toContain("turnInFlight={turnInFlight}");
    expect(message).toContain("disabled={turnInFlight}");
    expect(row).toContain("disabled={disabled}");
    // Disabled rows stay readable: they are evidence, not just an affordance.
    expect(row).toContain("disabled:opacity-55");
    expect(row).not.toContain("disabled:hidden");
  });

  test("the floating composer strip is gone and its gating survives", () => {
    expect(chat).not.toContain("const composerActions =");
    expect(chat).toContain("const nextMovesEnabled =");
    expect(chat).toContain("!hasActiveArtifactActionSet(messages)");
  });

  test("older footer options no longer reappear on hover", () => {
    // The hover reveal survives for the feedback controls only. Option rows are
    // gated on isLatest instead, because touch devices never hover.
    expect(message).toContain("footerVisibilityClass");
    const rowStart = message.indexOf("{showNextMoveRows && (");
    const rowBlock = message.slice(
      rowStart,
      message.indexOf("{shouldShowAssistantFooter && (", rowStart),
    );
    expect(rowBlock).toContain("<NextMoveRow");
    expect(rowBlock).not.toContain("footerVisibilityClass");
    expect(rowBlock).not.toContain("group-hover:opacity-100");
  });
});

describe("discovery selection carries resolved identity", () => {
  const tap = (payload: Record<string, unknown>) =>
    discoveryCandidateMention({
      type: "select_discovery_candidate",
      label: "Backtest AKAM",
      payload,
    } as never);

  test("a tapped candidate becomes an asset mention, not bare text", () => {
    expect(
      tap({ symbol: "AKAM", name: "Akamai Technologies", asset_class: "equity" }),
    ).toEqual({
      id: "asset:equity:AKAM",
      type: "asset",
      label: "Akamai Technologies",
      symbol: "AKAM",
      asset_class: "equity",
      insert_text: "AKAM",
    });
  });

  test("the resolver-owned asset class survives the tap", () => {
    expect(tap({ symbol: "SOL", name: "Solana", asset_class: "crypto" })?.asset_class).toBe(
      "crypto",
    );
    // An unrecognised class is dropped rather than passed through as truth.
    expect(tap({ symbol: "SOL", asset_class: "wildcat" })?.asset_class).toBeNull();
  });

  test("identity is only claimed when there is a symbol to claim", () => {
    expect(tap({ name: "No symbol here" })).toBeNull();
    expect(tap({ symbol: "   " })).toBeNull();
  });

  test("the mention id follows the documented asset:{class}:{symbol} shape", () => {
    // API_CONTRACT.md ties this shape to preserving a chosen identity for
    // ambiguous symbols, which is the whole point of carrying it.
    expect(tap({ symbol: "SOL", asset_class: "crypto" })?.id).toBe(
      "asset:crypto:SOL",
    );
  });

  test("no other action type produces a mention", () => {
    expect(
      discoveryCandidateMention({
        type: "select_response_option",
        label: "Compare with buy and hold",
        payload: { symbol: "AKAM" },
      } as never),
    ).toBeNull();
  });

  test("a durable retry replays the identity instead of bare chip text", () => {
    // The retry payload keeps the chat_action but carried no mentions, so
    // pressing Retry on a failed selection reintroduced the re-derivation this
    // slice fixes. The mention is rebuilt from the persisted action.
    const retry = chat.slice(
      chat.indexOf('if (action.type === "retry_last_turn")'),
      chat.indexOf('if (action.type === "retry_load_conversation")'),
    );
    expect(retry).toContain("discoveryCandidateMention(retryChatAction)");
    expect(retry).toContain("retryMention ? [retryMention]");
  });

  test("the tap sends the mention alongside the turn, and stays an ordinary turn", () => {
    // Identity travels; a prepared action does not. The turn still re-enters
    // interpretation and still requires confirmation before anything runs.
    expect(chat).toContain("const discoveryMention = discoveryCandidateMention(action)");
    expect(chat).toContain("handleSend(action.label || value, [discoveryMention], action)");
    expect(message).toContain("asset_class: candidate.asset_class");
  });
});

describe("who retires an action", () => {
  // Card actions die with their artifact, retry dies with its turn, and
  // conversational next moves are retired by the row renderer. One field holds
  // all three, so supersession must not retire what it does not own.
  test("supersession migrates card actions and clears retry, but keeps conversational options", () => {
    const superseded = markComposerActionsInactive([
      {
        id: "a",
        role: "ai",
        kind: "text",
        actions: [
          {
            id: "unsupported-strategy-rsi-threshold",
            label: "Use a supported RSI threshold rule",
            type: "select_response_option",
          },
          { id: "retry-1", label: "Retry", type: "retry_last_turn" },
        ],
      },
      {
        id: "b",
        role: "ai",
        kind: "strategy_confirmation",
        confirmation: { actions: undefined },
        actions: [{ type: "run_backtest", label: "Run backtest" }],
      },
    ] as never);

    // Conversational option survives; retry does not.
    expect(superseded[0].actions?.map((a) => a.id)).toEqual([
      "unsupported-strategy-rsi-threshold",
    ]);
    // Card action migrates onto the artifact that owns it.
    expect(superseded[1].actions).toBeUndefined();
    expect(
      (superseded[1] as { confirmation: { actions: Array<{ type: string }> } })
        .confirmation.actions.map((a) => a.type),
    ).toEqual(["run_backtest"]);
  });

  test("a message with only retry loses its actions entirely", () => {
    const superseded = markComposerActionsInactive([
      {
        id: "a",
        role: "ai",
        kind: "text",
        actions: [{ id: "retry-1", label: "Retry", type: "retry_last_turn" }],
      },
    ] as never);
    expect(superseded[0].actions).toBeUndefined();
  });
});

describe("sources panel", () => {
  test("renders persisted sidecar evidence without re-querying", () => {
    expect(panel).toContain("sources={sidecar.sources}");
    expect(sourcesList).toContain("sources.map");
    expect(sourcesList).not.toContain("fetch(");
    expect(panel).not.toContain("fetch(");
    expect(panel).not.toContain("useEffect(() => {\n    void load");
  });

  test("links open in a new tab with no opener handle or referrer", () => {
    expect(sourcesList).toContain('target="_blank"');
    expect(sourcesList).toContain('rel="noopener noreferrer"');
  });

  test("the visible domain comes from the href being opened, not the provider title", () => {
    const link = sourcesList.slice(
      sourcesList.indexOf("href={source.url}"),
      sourcesList.indexOf("</a>"),
    );
    expect(link).toContain("{source.domain}");
    // A title may be absent or misleading; the domain always renders.
    expect(link.indexOf("{source.domain}")).toBeGreaterThan(0);
  });

  test("both panel controls carry a 44px tap target despite compact visuals", () => {
    // The trigger is a 12px text line and the close button is a 16px icon.
    // Neither may rely on its visual box for touch: the trigger extends its hit
    // area with a pseudo-element so the baseline-aligned sources row is
    // unchanged, and the close button gets a real 44px box pulled into its
    // padding so the header layout is unchanged.
    const trigger = message.slice(
      message.indexOf("sources_panel_open") - 600,
      message.indexOf("sources_panel_open"),
    );
    expect(trigger).toContain("after:h-11");
    expect(trigger).toContain("after:min-w-11");
    expect(trigger).toContain("relative");

    const close = panel.slice(
      panel.indexOf("<button\n            type=\"button\"\n            data-autofocus"),
      panel.indexOf("</button>", panel.indexOf("data-autofocus\n")),
    );
    expect(close).toContain("aria-label={closeLabel}");
    expect(close).toContain("min-h-11");
    expect(close).toContain("min-w-11");
  });

  test("is a dismissible modal with restored focus", () => {
    expect(panel).toContain('role="dialog"');
    expect(panel).toContain('aria-modal="true"');
    expect(panel).toContain('event.key === "Escape"');
    expect(panel).toContain("restoreFocusRef.current?.focus?.()");
    expect(panel).toContain("onClick={onClose}");
  });

  test("a publisher's calendar date is never shifted by the viewer's timezone", () => {
    // A bare source_date is a calendar date, not an instant. Parsed as UTC
    // midnight and formatted locally, it would read a day early west of UTC.
    expect(formattedSourceDate("2026-07-20", "en-US")).toBe("Jul 20, 2026");
    expect(formattedSourceDate("2026-01-01", "en-US")).toBe("Jan 1, 2026");
  });

  test("absent or unparseable source dates render as nothing, never as an error", () => {
    expect(formattedSourceDate(null, "en-US")).toBe("");
    expect(formattedSourceDate(undefined, "en-US")).toBe("");
    expect(formattedSourceDate("not-a-date", "en-US")).toBe("");
  });

  test("framing explains source provenance and new-tab behavior", () => {
    expect(en.chat.discovery_results.sources_panel_note).toContain(
      "Sources used to inform this answer",
    );
  });
});

describe("locale parity for the new surface", () => {
  test.each([
    "sources_panel_open_one",
    "sources_panel_open_other",
    "sources_panel_title",
    "sources_panel_note",
    "sources_panel_close",
    "sources_panel_external_link_new_tab",
  ])("%s exists in both catalogs", (key) => {
    expect(typeof en.chat.discovery_results[key]).toBe("string");
    expect(typeof es.chat.discovery_results[key]).toBe("string");
    expect(en.chat.discovery_results[key].length).toBeGreaterThan(0);
    expect(es.chat.discovery_results[key].length).toBeGreaterThan(0);
  });

  test("a single source reads as one source, not '1 sources'", () => {
    for (const catalog of [en, es]) {
      const singular = catalog.chat.discovery_results.sources_panel_open_one;
      const plural = catalog.chat.discovery_results.sources_panel_open_other;
      expect(singular).toContain("{{count}}");
      expect(plural).toContain("{{count}}");
      expect(singular).not.toBe(plural);
    }
    expect(en.chat.discovery_results.sources_panel_open_one).toContain("source ");
    expect(en.chat.discovery_results.sources_panel_open_other).toContain("sources ");
  });
});
