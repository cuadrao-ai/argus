import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  decideGuestNewConversationGate,
  decideGuestSimulationGate,
  guestSimulationPrecheckReset,
  isExactGuestRunReplay,
} from "../lib/guest-capability-gates";

describe("guest capability gate policy", () => {
  test("allows exact replay before converting a third unique guest simulation", () => {
    expect(
      decideGuestSimulationGate({
        accountKind: "guest",
        availableNow: false,
        exactReplay: true,
      }),
    ).toEqual({ kind: "allow" });
    expect(
      decideGuestSimulationGate({
        accountKind: "guest",
        availableNow: false,
        exactReplay: false,
      }),
    ).toEqual({ kind: "convert", reason: "simulation_limit" });
    expect(
      isExactGuestRunReplay(
        [
          {
            selectedAction: {
              type: "run_backtest",
              payload: { confirmation_id: "confirmation-1" },
            },
          },
        ],
        {
          type: "run_backtest",
          payload: { confirmation_id: "confirmation-1" },
        },
      ),
    ).toBe(true);
    expect(
      isExactGuestRunReplay(
        [
          {
            selectedAction: {
              type: "run_backtest",
              payload: { confirmation_id: "confirmation-1" },
            },
          },
        ],
        {
          type: "run_backtest",
          payload: { idempotency_key: "resumed-action-2" },
        },
      ),
    ).toBe(false);
  });

  test("names the horizon the backend says holds the guest", () => {
    const workspaceExpiresAt = "2026-08-10T12:00:00Z";
    const dayEnd = "2026-08-04T00:00:00Z";

    // The visitor's day is spent while the workspace still has room.
    expect(
      guestSimulationPrecheckReset({
        day: { period_end: dayEnd },
        guest_session: { period_end: workspaceExpiresAt },
        limiting_window: "day",
      }),
    ).toEqual({ resetAt: dayEnd, resetKind: "daily" });
    // #546: the workspace is spent although the day reset at midnight.
    expect(
      guestSimulationPrecheckReset({
        day: { period_end: dayEnd },
        guest_session: { period_end: workspaceExpiresAt },
        limiting_window: "guest_session",
      }),
    ).toEqual({ resetAt: workspaceExpiresAt, resetKind: "workspace" });
    expect(
      guestSimulationPrecheckReset({
        day: null,
        guest_session: null,
        limiting_window: null,
      }),
    ).toEqual({ resetAt: null, resetKind: "daily" });
  });

  test("resets an empty guest chat and asks before replacing accepted content", () => {
    expect(
      decideGuestNewConversationGate({
        accountKind: "guest",
        hasAcceptedContent: false,
      }),
    ).toEqual({ kind: "reset_empty" });
    expect(
      decideGuestNewConversationGate({
        accountKind: "guest",
        hasAcceptedContent: true,
      }),
    ).toEqual({ kind: "choose_non_empty" });
    expect(
      decideGuestNewConversationGate({
        accountKind: "registered",
        hasAcceptedContent: true,
      }),
    ).toEqual({ kind: "allow" });
  });

  test("keeps a composer draft when admission is blocked before send", () => {
    const composer = readFileSync(
      join(import.meta.dir, "../components/chat/ChatInput.tsx"),
      "utf-8",
    );

    expect(composer).toContain("const accepted = await onSend");
    expect(composer).toContain("if (accepted === false) return");
  });

  test("does not consume a confirmation action before guest admission", () => {
    const chat = readFileSync(
      join(import.meta.dir, "../components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const handleAction = chat.slice(
      chat.indexOf("const handleAction ="),
      chat.indexOf("// ── Chat options helpers"),
    );

    expect(handleAction).not.toContain("confirmationActionEffectFromAction");
    expect(chat).toContain("consumeConfirmationActionOnMessages");
  });

  test("carries the exact evidence artifact through the decision gate", () => {
    const result = readFileSync(
      join(import.meta.dir, "../components/chat/StrategyResultCard.tsx"),
      "utf-8",
    );

    expect(result).toContain(
      "onDecisionUnavailable?.(result.evidenceArtifactId!)",
    );
  });
});

describe("no send is refused in silence", () => {
  // The class, not the two instances: any path that declines a real message
  // has to leave the person something to react to. Two refusals are allowed
  // to stay quiet because nothing was asked of Argus, and they are named here
  // so a new silent one cannot hide among them.
  const chat = readFileSync(
    join(import.meta.dir, "../components/chat/ChatInterface.tsx"),
    "utf-8",
  );
  const SILENT_BY_DESIGN = [
    "if (!trimmed) return false;",
    "if (sendAdmissionInFlightRef.current || isStreamingResponse) {",
  ];

  function sendHandlerBody() {
    const start = chat.indexOf("const handleSend = async (");
    expect(start).toBeGreaterThan(-1);
    const end = chat.indexOf("\n  const ", start + 40);
    expect(end).toBeGreaterThan(start);
    return chat.slice(start, end);
  }

  test("every bare refusal in the send handler is one of the named exceptions", () => {
    const body = sendHandlerBody();
    const lines = body.split("\n");
    const bare: string[] = [];
    let scanned = 0;
    lines.forEach((line, index) => {
      if (!/^\s*return false;\s*$/.test(line)) return;
      scanned += 1;
      // Surfaced here, or delegated to admitSend, which surfaces on its own
      // for every refusal that is not a superseded admission. The sibling
      // block above is what holds admitSend to that.
      const preceding = lines.slice(Math.max(0, index - 8), index + 1).join("\n");
      if (
        /refuseSend|showToast|setGuestSubmissionError|onGateError|admitSend/.test(
          preceding,
        )
      ) {
        return;
      }
      if (SILENT_BY_DESIGN.some((allowed) => preceding.includes(allowed))) return;
      bare.push(
        `${index + 1}: ${lines.slice(Math.max(0, index - 1), index + 1).join(" / ").trim()}`,
      );
    });
    // Guards the scan itself: an empty result has to mean every refusal was
    // classified, not that the slice found none to look at.
    expect(lines.length).toBeGreaterThan(200);
    expect(scanned).toBeGreaterThanOrEqual(2);
    expect(bare).toEqual([]);
  });

  test("the busy refusal says the same thing on both paths", () => {
    const body = sendHandlerBody();
    const busy = body.match(/refuseSend\("chat\.send_busy", SEND_BUSY_FALLBACK\)/g) ?? [];
    expect(busy.length).toBe(2);
  });
});
