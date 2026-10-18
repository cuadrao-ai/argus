"use client";

import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AuthFormSubmission } from "@/components/auth/AuthForm";
import {
  createGuestHandoff,
  registerGuestAccount,
} from "@/lib/guest-api";
import {
  getMe,
  loginWithEmail,
  normalizeApiLanguage,
  signupWithEmail,
} from "@/lib/argus-api";
import { EmailOtpRejectedError } from "@/lib/email-otp";
import type { UserResponse } from "@/lib/guest-account";
import {
  pendingGuestActionSummary,
  verifiedClaimAction,
  SingleUseGuestAction,
  type GuestConversionMode,
  type GuestConversionReason,
  type GuestPendingAction,
} from "@/lib/guest-conversion";
import { authenticatedRequestHeaders } from "@/lib/chat-auth-ownership";
import { randomId } from "@/lib/random-id";

type UseGuestConversionInput = {
  account: UserResponse | null;
  conversationId: string | null;
  refreshAccount: (expectedUserId?: string) => Promise<UserResponse | null>;
  refreshHistory: () => void | Promise<unknown>;
  onAuthenticationStart: () => void;
  onAuthenticationComplete: (userId: string | null) => void;
  onResume: (action: GuestPendingAction) => void | Promise<void>;
};

export function useGuestConversion({
  account,
  conversationId,
  refreshAccount,
  refreshHistory,
  onResume,
  onAuthenticationStart,
  onAuthenticationComplete,
}: UseGuestConversionInput) {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const [reason, setReason] =
    useState<GuestConversionReason>("keep_history");
  const [initialMode, setInitialMode] =
    useState<GuestConversionMode>("login");
  const [resetAt, setResetAt] = useState<string | null>(null);
  const [resetKind, setResetKind] = useState<"daily" | "workspace">("daily");
  const latchRef = useRef<SingleUseGuestAction | null>(null);
  const handoffPreparedRef = useRef(false);
  const sourceConversationId =
    conversationId ?? account?.guest?.conversation_id ?? null;

  const requestConversion = useCallback(
    (
      nextReason: GuestConversionReason,
      pendingAction?: GuestPendingAction | null,
      nextInitialMode: GuestConversionMode = "login",
      nextResetAt: string | null = null,
      nextResetKind: "daily" | "workspace" = "daily",
    ) => {
      setReason(nextReason);
      setInitialMode(nextInitialMode);
      setResetAt(nextResetAt);
      setResetKind(nextResetKind);
      latchRef.current = pendingAction
        ? new SingleUseGuestAction(pendingAction)
        : null;
      handoffPreparedRef.current = false;
      setIsOpen(true);
    },
    [],
  );

  const close = useCallback(() => {
    setIsOpen(false);
    handoffPreparedRef.current = false;
  }, []);

  const authenticate = useCallback(
    async (submission: AuthFormSubmission) => {
      onAuthenticationStart();
      try {
      let destinationUserId: unknown;
      const latch = latchRef.current;
      if (submission.mode === "signup") {
        if (!sourceConversationId) {
          const registered = await signupWithEmail({
            email: submission.email,
            password: submission.password,
            language: normalizeApiLanguage(account?.user.language),
            display_name: submission.displayName || null,
            age_confirmed_at: submission.ageConfirmedAt ?? "",
          });
          destinationUserId = registered.response.user?.id;
          if (registered.needsEmailConfirmation) {
            onAuthenticationComplete(account?.user.id ?? null);
            return { status: "email_confirmation_required" as const };
          }
        } else {
          const pending = latch?.take();
          if (pending) {
            latchRef.current = new SingleUseGuestAction(pending);
          }
          const registered = await registerGuestAccount({
            email: submission.email,
            password: submission.password,
            language: normalizeApiLanguage(account?.user.language),
            display_name: submission.displayName || null,
            source_conversation_id: sourceConversationId,
            pending_action: pending
              ? pendingGuestActionSummary(pending)
              : {
                  reason: "keep_history",
                  conversation_id: sourceConversationId,
                  action_id: randomId(),
                },
            age_confirmed_at: submission.ageConfirmedAt ?? "",
          });
          handoffPreparedRef.current = true;
          destinationUserId = registered.response.user?.id;
          if (registered.needsEmailConfirmation) {
            onAuthenticationComplete(account?.user.id ?? null);
            return { status: "email_confirmation_required" as const };
          }
          const claimed = registered.response.guest_claim;
          if (!claimed) {
            throw new Error("The temporary conversation could not be claimed.");
          }
          const expected = verifiedClaimAction(
            claimed,
            sourceConversationId,
            latchRef.current,
          );
          if (expected) {
            latchRef.current = new SingleUseGuestAction(expected);
          }
        }
      } else {
        if (sourceConversationId && !handoffPreparedRef.current) {
          const pending = latch?.take();
          if (pending) {
            latchRef.current = new SingleUseGuestAction(pending);
          }
          await createGuestHandoff({
            destination_email: submission.email,
            source_conversation_id: sourceConversationId,
            pending_action: pending
              ? pendingGuestActionSummary(pending)
              : {
                  reason: "keep_history",
                  conversation_id: sourceConversationId,
                  action_id: randomId(),
                },
          });
          handoffPreparedRef.current = true;
        }

        const authenticated = await loginWithEmail({
          email: submission.email,
          password: submission.password,
        });
        destinationUserId = authenticated.user?.id;
        if (handoffPreparedRef.current && sourceConversationId) {
          const claimed = authenticated.guest_claim;
          if (!claimed) {
            throw new Error("The temporary conversation could not be claimed.");
          }
          const expected = verifiedClaimAction(
            claimed,
            sourceConversationId,
            latchRef.current,
          );
          if (expected) {
            latchRef.current = new SingleUseGuestAction(expected);
          }
        }
      }

      if (typeof destinationUserId !== "string") throw new Error(t("chat.error_generic"));
      const refreshed = await refreshAccount(destinationUserId);
      onAuthenticationComplete(refreshed?.user.id ?? null);
      } catch (error) {
        try {
          if (!account?.user.id) throw error;
          await authenticatedRequestHeaders(account.user.id);
          onAuthenticationComplete(account.user.id);
        } catch { onAuthenticationComplete(null); }
        throw error;
      }
      const actionLatch = latchRef.current;
      const action = actionLatch?.take() ?? null;
      setIsOpen(false);
      handoffPreparedRef.current = false;
      // Recents is a projection: its latency or failure cannot delay the
      // verified action after the claim has completed.
      void Promise.resolve().then(refreshHistory).catch(() => undefined);
      if (action) {
        await onResume(action);
      }
    },
    [
      account,
      t,
      onResume,
      onAuthenticationStart,
      onAuthenticationComplete,
      refreshAccount,
      refreshHistory,
      sourceConversationId,
    ],
  );

  const finishConfirmedSignup = useCallback(async () => {
    const me = await getMe();
    const userId = me?.user.id;
    if (typeof userId !== "string" || userId.length === 0) {
      throw new EmailOtpRejectedError();
    }
    const refreshed = await refreshAccount(userId);
    onAuthenticationComplete(refreshed?.user.id ?? null);
    setIsOpen(false);
    handoffPreparedRef.current = false;
    void Promise.resolve().then(refreshHistory).catch(() => undefined);
  }, [onAuthenticationComplete, refreshAccount, refreshHistory]);

  return {
    isOpen,
    reason,
    initialMode,
    resetAt,
    resetKind,
    publicAccountAccessEnabled:
      account?.public_account_access_enabled ?? false,
    locale:
      account?.user.language === "es-419"
        ? ("es-419" as const)
        : ("en-US" as const),
    requestConversion,
    close,
    authenticate,
    finishConfirmedSignup,
  };
}
