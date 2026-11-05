import { describe, expect, test } from "bun:test";
import { readFileSync } from "fs";
import { join } from "path";

/* Flag-off equivalence: with NEXT_PUBLIC_RESEARCH_RAIL_ENABLED unset, every
 * rail surface stays dark and the pre-rail strings render byte-for-byte. */

const root = join(__dirname, "..");
const source = (path: string) => readFileSync(join(root, path), "utf-8");

describe("research rail flag-off equivalence", () => {
  test("the flag defaults off", () => {
    const flags = source("lib/private-alpha-flags.ts");
    expect(flags).toContain(
      'process.env.NEXT_PUBLIC_RESEARCH_RAIL_ENABLED === "true"',
    );
  });

  test("flag-off placeholders resolve to the exact pre-rail strings", () => {
    const en = JSON.parse(source("public/locales/en/common.json"));
    const es = JSON.parse(source("public/locales/es-419/common.json"));
    expect(en.chat.input_placeholder_prerail).toBe("Describe an investing idea");
    expect(es.chat.input_placeholder_prerail).toBe(
      "Describe una idea de inversión...",
    );
    expect(en.guest?.shell?.input_placeholder_prerail).toBeUndefined();
    expect(es.guest?.shell?.input_placeholder_prerail).toBeUndefined();
    expect(en.chat.followup_placeholder).toBe("Add a follow-up");

    const chat = source("components/chat/ChatInterface.tsx");
    expect(chat).toContain('"chat.input_placeholder_prerail"');
    expect(chat).not.toContain('"guest.shell.input_placeholder_prerail"');
  });

  test("flag-off empty chat has no investing pills", () => {
    const emptyChat = source("components/chat/EmptyChatSurface.tsx");
    expect(emptyChat).toContain("const showGreeting = researchRailEnabled;");
    const starterActions = source("components/chat/StarterActions.tsx");
    expect(starterActions).toContain("if (!workspaceEntries?.length) return null;");
    expect(starterActions).not.toContain("chat.starter_actions.tsla.label");
  });

  test("flag-off cards and jobs are untouched surfaces", () => {
    const copy = source("lib/backtest-job-card-copy.ts");
    expect(copy).toContain('job.operation_scope === "chat.research"');
    const card = source("components/chat/StrategyConfirmationCard.tsx");
    // Change feedback renders only from backend-provided adjustment data,
    // which the backend only emits with the rail flag on: motion on the new
    // chip and an inline period note, never a narration banner.
    expect(card).toContain("confirmation.assets_adjustment?.added");
    expect(card).toContain("argus-chip-appear");
    expect(card).toContain("confirmation-period-change-note");
    expect(card).not.toContain("research_peers");
    const rows = source("lib/chat-next-experiments.ts");
    expect(rows).toContain('"add_confirmation_peer"');
  });
});
