import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { Children, isValidElement } from "react";

import GuestExperienceSurfaces from "../components/guest/GuestExperienceSurfaces";
import GuestConversionModal from "../components/guest/GuestConversionModal";
import type { GuestExperience } from "../components/guest/useGuestExperience";
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

function guestExperienceSurfaceFixture({
  conversionOpen,
  initialMode,
}: {
  conversionOpen: boolean;
  initialMode: "login" | "signup";
}): GuestExperience {
  return {
    conversion: {
      isOpen: conversionOpen,
      reason: "new_conversation",
      initialMode,
      publicAccountAccessEnabled: initialMode === "signup",
      close: () => undefined,
      authenticate: async () => undefined,
    },
    newConversation: {
      isOpen: false,
      isReplacing: false,
      close: () => undefined,
      startOver: async () => undefined,
      convert: () => undefined,
    },
    receiptSharing: { target: null, close: () => undefined },
  } as unknown as GuestExperience;
}

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

  test("uses one shared validated auth form in landing and centered modal", () => {
    const sharedPath = join(root, "components/auth/AuthForm.tsx");
    const modalPath = join(root, "components/guest/GuestConversionModal.tsx");
    const landing = readFileSync(join(root, "app/page.tsx"), "utf-8");

    expect(existsSync(sharedPath)).toBe(true);
    expect(existsSync(modalPath)).toBe(true);
    if (!existsSync(sharedPath) || !existsSync(modalPath)) return;
    const shared = readFileSync(sharedPath, "utf-8");
    const modal = readFileSync(modalPath, "utf-8");

    expect(landing).toContain("<AuthForm");
    expect(modal).toContain("<AuthForm");
    expect(shared).toContain("showPassword");
    expect(shared).toContain("authError");
    expect(shared).toContain("acceptanceLinks()");
    expect(shared).not.toContain('href="/terms"');
    expect(shared).not.toContain('href="/privacy"');
    expect(modal).toContain('role="dialog"');
    expect(modal).toContain('aria-modal="true"');
    expect(modal).toContain('event.key === "Escape"');
    expect(modal).toContain("restoreFocusRef");
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

  test("keeps account creation server-capability gated", () => {
    const modal = readFileSync(
      join(root, "components/guest/GuestConversionModal.tsx"),
      "utf-8",
    );
    expect(modal).toContain("publicAccountAccessEnabled");
    expect(modal).toContain(
      'publicAccountAccessEnabled ? initialMode : "request"',
    );
    expect(modal).toContain("allowModeSwitch={publicAccountAccessEnabled}");
    expect(modal).toContain("<RequestAccess");
    expect(modal).toContain("mode={mode}");
  });

  test("uses the daily reset only for the renewed-workspace precheck", () => {
    const experience = readFileSync(
      join(root, "components/guest/useGuestExperience.ts"),
      "utf-8",
    );
    const admission = experience.slice(
      experience.indexOf("const admitSend"),
      experience.indexOf("const recoverGuestSimulationRejection"),
    );
    const authoritativeRejection = experience.slice(
      experience.indexOf("const recoverGuestSimulationRejection"),
    );

    // The backend names which window holds the guest: the visitor's day
    // after a renewal, or the workspace lifetime when that is what is spent.
    expect(admission).toContain("guestSimulationPrecheckReset(");
    expect(admission).toContain("usage.allowances.execution");
    expect(admission).toContain("reset.resetKind");
    // The server-only workspace ceiling still names the actual temporary
    // workspace expiry after an authoritative rejection.
    expect(authoritativeRejection).toContain(
      "account.guest?.expires_at ?? null",
    );
  });

  test("opens quota recovery for an authoritative workspace-limit rejection", () => {
    const experience = readFileSync(
      join(root, "components/guest/useGuestExperience.ts"),
      "utf-8",
    );
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");

    expect(experience).toContain("recoverGuestSimulationRejection");
    expect(chat).toContain("isGuestSimulationConversionRejection");
    expect(chat).toContain("errorPayload.code");
    expect(chat).toContain("event.data.final_response_payload?.code ?? event.data.code");
    expect(chat).toContain("loadConversation(requestSession.identity.conversationId)");
    expect(chat.indexOf("errorPayload.code")).toBeLessThan(
      chat.indexOf("throwIfAmbiguousRunSseError", chat.indexOf('event.event === "error"')),
    );
    expect(chat).toContain("recoverGuestSimulationRejection(action)");
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

  test("mounts the conversion modal fresh so the requested mode owns its first render", () => {
    const closed = GuestExperienceSurfaces({
      experience: guestExperienceSurfaceFixture({
        conversionOpen: false,
        initialMode: "login",
      }),
    });
    const publicOpen = GuestExperienceSurfaces({
      experience: guestExperienceSurfaceFixture({
        conversionOpen: true,
        initialMode: "signup",
      }),
    });

    const modal = (surface: typeof closed) => Children.toArray(surface.props.children)
      .find((child) => isValidElement(child) && child.type === GuestConversionModal);
    expect(modal(closed)).toBeUndefined();
    const openModal = modal(publicOpen);
    expect(isValidElement<{ initialMode: string }>(openModal) && openModal.props.initialMode).toBe("signup");
  });

  test("localizes staged and public New-chat choices in English and Spanish", () => {
    const en = JSON.parse(
      readFileSync(join(root, "public/locales/en/common.json"), "utf-8"),
    );
    const es = JSON.parse(
      readFileSync(join(root, "public/locales/es-419/common.json"), "utf-8"),
    );

    expect(en.guest.new_conversation.sign_in).toBe("Sign in to keep it");
    expect(en.guest.new_conversation.create_account).toBe("Create account");
    expect(en.guest.new_conversation.public_description).toBe(
      "Start over replaces this temporary conversation. Create an account to keep it and start another.",
    );
    expect(en.guest.conversion.new_conversation_create).toBe(
      "Create an account to keep this conversation and start another.",
    );
    expect(es.guest.new_conversation.sign_in).toBe(
      "Iniciar sesión para conservarla",
    );
    expect(es.guest.new_conversation.create_account).toBe("Crear cuenta");
    expect(es.guest.new_conversation.public_description).toBe(
      "Empezar de nuevo reemplaza esta conversación temporal. Crea una cuenta para conservarla y comenzar otra.",
    );
    expect(es.guest.conversion.new_conversation_create).toBe(
      "Crea una cuenta para conservar esta conversación y comenzar otra.",
    );
  });

  test("schedules Recents after the claim without blocking the pending action", () => {
    const hookPath = join(root, "components/guest/useGuestConversion.ts");
    const chat = readFileSync(
      join(root, "components/chat/ChatInterface.tsx"),
      "utf-8",
    );
    const surfaces = readFileSync(
      join(root, "components/guest/GuestExperienceSurfaces.tsx"),
      "utf-8",
    );
    const experience = readFileSync(
      join(root, "components/guest/useGuestExperience.ts"),
      "utf-8",
    );
    expect(existsSync(hookPath)).toBe(true);
    if (!existsSync(hookPath)) return;
    const hook = readFileSync(hookPath, "utf-8");

    expect(hook).toContain("createGuestHandoff");
    expect(hook).toContain("registerGuestAccount");
    expect(hook).toContain("loginWithEmail");
    expect(hook).toContain(
      "conversationId ?? account?.guest?.conversation_id ?? null",
    );
    expect(hook).toContain("authenticated.guest_claim");
    const authenticate = hook.slice(hook.indexOf("const authenticate"));
    expect(authenticate.indexOf("createGuestHandoff")).toBeLessThan(
      authenticate.indexOf("loginWithEmail"),
    );
    expect(authenticate.indexOf("registerGuestAccount")).toBeLessThan(
      authenticate.indexOf("await refreshAccount(destinationUserId)"),
    );
    expect(authenticate).toContain('status: "email_confirmation_required"');
    expect(hook).toContain("SingleUseGuestAction");
    expect(hook).toContain("actionLatch?.take()");
    const scheduleHistory = "void Promise.resolve().then(refreshHistory).catch(() => undefined)";
    expect(authenticate).toContain(scheduleHistory);
    expect(authenticate).not.toContain("await refreshHistory()");
    expect(authenticate.indexOf("await refreshAccount(destinationUserId)")).toBeLessThan(
      authenticate.indexOf(scheduleHistory),
    );
    expect(authenticate.indexOf("setIsOpen(false)")).toBeLessThan(
      authenticate.indexOf(scheduleHistory),
    );
    expect(authenticate.indexOf(scheduleHistory)).toBeLessThan(
      authenticate.indexOf("await onResume(action)"),
    );
    expect(experience).toContain("refreshHistoryForActivity");
    expect(experience).toContain("refreshHistory: refreshHistoryForActivity");
    expect(chat).toContain("<GuestExperienceSurfaces");
    expect(surfaces).toContain("<GuestConversionModal");
    expect(surfaces).toContain("publicAccountAccessEnabled");
  });
});
