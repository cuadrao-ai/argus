import type { ChatActionOption } from "@/components/chat/types";
import { retryLastTurnActionFromMessage } from "./chat-retry-actions";
import type { RecoveryDisplay } from "./chat-recovery-display";
import { DAILY_CAP_RECOVERY_CODE } from "./daily-cap-reset-time";
import { parseRetryAfterSeconds } from "./retry-after";

export const GUEST_COMPUTE_CLAIM_UNAVAILABLE_CODE =
  "guest_compute_claim_unavailable";

export const REGISTERED_COMPUTE_CLAIM_UNAVAILABLE_CODE =
  "registered_compute_claim_unavailable";

type ComputeClaimUnavailableCode =
  | typeof GUEST_COMPUTE_CLAIM_UNAVAILABLE_CODE
  | typeof REGISTERED_COMPUTE_CLAIM_UNAVAILABLE_CODE;

export const GUEST_COMPUTE_CLAIM_RETRY_IN_KEY =
  "chat.recovery.guest_compute_claim_retry_in";

export function isComputeClaimUnavailable(
  code: string | null | undefined,
): code is ComputeClaimUnavailableCode {
  return code === GUEST_COMPUTE_CLAIM_UNAVAILABLE_CODE ||
    code === REGISTERED_COMPUTE_CLAIM_UNAVAILABLE_CODE;
}

export function localizedComputeClaimMessage(
  code: string | null | undefined,
  translate: (key: string) => string,
  fallback: string,
): string {
  if (!isComputeClaimUnavailable(code)) {
    return fallback;
  }
  return translate(`chat.recovery.${code}`);
}

export function computeClaimTransportPatch(input: {
  code: string | null | undefined;
  retryAfterHeader: string | null | undefined;
  retryAction: ChatActionOption | null;
  nowMs?: number;
}): {
  assistantRecoveryCode?: string;
  actions?: ChatActionOption[];
} {
  if (!isComputeClaimUnavailable(input.code)) {
    return {};
  }
  const nowMs = input.nowMs ?? Date.now();
  const waitSeconds = parseRetryAfterSeconds(input.retryAfterHeader, nowMs);
  return {
    assistantRecoveryCode: input.code,
    actions: input.retryAction
      ? [
          {
            ...input.retryAction,
            availableAtMs: nowMs + waitSeconds * 1000,
          },
        ]
      : undefined,
  };
}

export function claimErrorRetryAction(input: {
  code: string | null | undefined;
  retryAction: ChatActionOption | null;
  message: string;
  assistantMessageId: string;
  chatAction?: ChatActionOption | null;
}): ChatActionOption | null {
  if (!isComputeClaimUnavailable(input.code)) {
    return input.retryAction;
  }
  if (input.retryAction) {
    return input.retryAction;
  }
  if (!input.chatAction?.type) {
    return null;
  }
  return retryLastTurnActionFromMessage(input.message, {
    assistantMessageId: input.assistantMessageId,
    chatAction: input.chatAction,
  });
}

export function claimErrorKeepsLocalTranscript(
  code: string | null | undefined,
): boolean {
  return isComputeClaimUnavailable(code);
}

export function admissionErrorTerminalPayload(
  assistantMessageId: string,
  code: ComputeClaimUnavailableCode,
): {
  message_id: string;
  recovery: { code: ComputeClaimUnavailableCode };
} {
  return {
    message_id: assistantMessageId,
    recovery: { code },
  };
}

export function claimErrorMessagePatch(input: {
  code: string | null | undefined;
  retryAfterHeader: string | null | undefined;
  retryAction: ChatActionOption | null;
  message: string;
  assistantMessageId: string;
  chatAction?: ChatActionOption | null;
  nowMs?: number;
}) {
  return computeClaimTransportPatch({
    code: input.code,
    retryAfterHeader: input.retryAfterHeader,
    retryAction: claimErrorRetryAction(input),
    nowMs: input.nowMs,
  });
}

type AdmissionTransportReadiness = {
  accept: (
    payload: ReturnType<typeof admissionErrorTerminalPayload>,
    identityAuthorized: boolean,
  ) => boolean;
  finish: (identityAuthorized: boolean) => boolean;
  reject: (identityAuthorized: boolean) => boolean;
};

export function settleAdmissionTransportReadiness(
  terminalReadiness: AdmissionTransportReadiness,
  recovery: RecoveryDisplay | null,
  assistantMessageId: string,
  authorized: boolean,
): void {
  const code = recovery?.kind === "recovery_code" ? recovery.code : null;
  if (code === DAILY_CAP_RECOVERY_CODE) {
    terminalReadiness.reject(authorized);
  } else if (isComputeClaimUnavailable(code)) {
    terminalReadiness.accept(
      admissionErrorTerminalPayload(assistantMessageId, code),
      authorized,
    );
  }
  terminalReadiness.finish(authorized);
}
