import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  dossierDecisionResumeTarget,
  guestConversionBenefitKey,
  latestDecisionResumeMessageId,
  newConversationConversionMode,
  pendingGuestActionSummary,
  SingleUseGuestAction,
  type GuestPendingAction,
} from "../lib/guest-conversion";

const root = join(import.meta.dir, "..");

describe("guest conversion contract", () => {
  test("keeps the four contextual reasons typed and localized", () => {
    const actions: GuestPendingAction[] = [
      {
        reason: "simulation_limit",
        conversationId: "conversation-1",
        actionId: "run-2",
        action: {
          type: "run_backtest",
          label: "Run backtest",
          payload: { confirmation_id: "confirmation-1" },
        },
      },
      {
        reason: "save_decision",
        conversationId: "conversation-1",
        actionId: "decision-1",
        target: {
          surface: "result_card",
          artifactId: "artifact-1",
        },
      },
      {
        reason: "new_conversation",
        conversationId: "conversation-1",
        actionId: "new-chat-1",
      },
      {
        reason: "keep_history",
        conversationId: "conversation-1",
        actionId: "keep-1",
      },
    ];

    expect(actions.map((action) => guestConversionBenefitKey(action.reason))).toEqual([
      "guest.conversion.simulation_limit",
      "guest.conversion.save_decision",
      "guest.conversion.new_conversation",
      "guest.conversion.keep_history",
    ]);
    expect(pendingGuestActionSummary(actions[0])).toEqual({
      reason: "simulation_limit",
      conversation_id: "conversation-1",
      action_id: "run-2",
    });
    expect(pendingGuestActionSummary(actions[1])).toEqual({
      reason: "save_decision",
      conversation_id: "conversation-1",
      action_id: "decision-1",
      artifact_id: "artifact-1",
    });
  });

  test("resumes a pending action at most once", () => {
    const action: GuestPendingAction = {
      reason: "save_decision",
      conversationId: "conversation-1",
      actionId: "decision-1",
      target: {
        surface: "result_card",
        artifactId: "artifact-1",
      },
    };
    const latch = new SingleUseGuestAction(action);

    expect(latch.take()).toEqual(action);
    expect(latch.take()).toBeNull();
  });

  test("keeps dossier resume context ephemeral while binding the handoff to evidence", () => {
    const action: GuestPendingAction = {
      reason: "save_decision",
      conversationId: "conversation-1",
      actionId: "decision-1",
      target: {
        surface: "omnisearch_dossier",
        artifactId: "artifact-1",
        runId: "run-1",
        decisionState: "watching",
        note: "Keep this exact note",
      },
    };

    expect(pendingGuestActionSummary(action)).toEqual({
      reason: "save_decision",
      conversation_id: "conversation-1",
      action_id: "decision-1",
      artifact_id: "artifact-1",
    });
    expect(new SingleUseGuestAction(action).take()).toEqual(action);
    expect(dossierDecisionResumeTarget(action.target)).toEqual(action.target);
    expect(
      dossierDecisionResumeTarget({
        surface: "result_card",
        artifactId: "artifact-1",
      }),
    ).toBeNull();
  });

  test("resumes a decision on only the newest matching result projection", () => {
    const messages = [
      {
        id: "older-result",
        kind: "strategy_result",
        result: { evidenceArtifactId: "evidence-1" },
      },
      {
        id: "newest-result",
        kind: "strategy_result",
        result: { evidenceArtifactId: "evidence-1" },
      },
      {
        id: "other-result",
        kind: "strategy_result",
        result: { evidenceArtifactId: "evidence-2" },
      },
    ];

    expect(
      latestDecisionResumeMessageId(messages, "evidence-1"),
    ).toBe("newest-result");
    expect(latestDecisionResumeMessageId(messages, null)).toBeNull();
  });


  test("keeps the shared legal footer mode-safe in English and Spanish", () => {
    const shared = readFileSync(
      join(root, "components/auth/AuthForm.tsx"),
      "utf-8",
    );
    const en = JSON.parse(
      readFileSync(join(root, "public/locales/en/common.json"), "utf-8"),
    );
    const es = JSON.parse(
      readFileSync(join(root, "public/locales/es-419/common.json"), "utf-8"),
    );

    expect(shared).toContain('"auth.legal.continuing_prefix"');
    expect(shared).toContain('"landing.legal_prefix"');
    expect(en.auth.legal.continuing_prefix).toBe(
      "By continuing, you agree to our",
    );
    expect(es.auth.legal.continuing_prefix).toBe(
      "Al continuar, aceptas nuestros",
    );
  });




  test("derives the New-chat auth mode from server-owned public access truth", () => {
    expect(newConversationConversionMode(false)).toBe("login");
    expect(newConversationConversionMode(true)).toBe("signup");
    expect(guestConversionBenefitKey("new_conversation", "login")).toBe(
      "guest.conversion.new_conversation",
    );
    expect(guestConversionBenefitKey("new_conversation", "signup")).toBe(
      "guest.conversion.new_conversation_create",
    );
  });



});
