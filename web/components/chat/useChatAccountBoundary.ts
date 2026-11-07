"use client";
import { useCallback, useContext, useLayoutEffect, useRef, useState } from "react";
import { SessionRecoveryContext, useSessionRecoveryState } from "@/components/status/session-recovery-context";
import { createSessionRecovery } from "@/lib/session-recovery";
import type { ChatRequestSessionController } from "@/lib/chat-request-session";

export function useChatAccountBoundary(userId: string | null, requests: ChatRequestSessionController, clearView: () => void) {
  const shared = useContext(SessionRecoveryContext);
  const [recovery] = useState(() => shared ?? createSessionRecovery({ initialOwner: userId, allowAnonymous: true }));
  const state = useSessionRecoveryState(recovery, !shared && process.env.NEXT_PUBLIC_MOCK_AUTH !== "true");
  const owner = useRef(userId);
  const clear = useRef(clearView);
  const invalidated = useRef(false);
  const conversionPending = useRef(false);
  const admission = useRef(new AbortController());
  const retire = useCallback(() => {
    if (invalidated.current) return;
    invalidated.current = true;
    admission.current.abort();
    requests.synchronizeAccountScope(null);
    clear.current();
  }, [requests]);
  useLayoutEffect(() => recovery.onRetire(retire), [recovery, retire]);
  const invalidate = useCallback(() => {
    if (invalidated.current || conversionPending.current) return;
    retire();
    recovery.recheckAfterMismatch();
  }, [recovery, retire]);
  useLayoutEffect(() => {
    clear.current = clearView;
  }, [clearView]);
  useLayoutEffect(() => {
    const session = recovery.getSnapshot();
    if (conversionPending.current || invalidated.current) return;
    if (owner.current !== null && owner.current !== userId) invalidate();
    else if (userId && session.kind === "same-owner" && session.userId !== userId) invalidate();
    else owner.current = userId;
  }, [userId, recovery, invalidate]);
  const beginConversion = useCallback(() => {
    conversionPending.current = true;
    recovery.beginConversion();
    admission.current.abort();
    requests.synchronizeAccountScope(null);
  }, [recovery, requests]);
  const finishConversion = useCallback(() => {
    conversionPending.current = false;
    recovery.finishConversion();
  }, [recovery]);
  const expired = state.kind !== "same-owner" && (state.kind !== "pending" || state.busy);
  return { expired, invalidated, conversionPending, admission, invalidate, beginConversion, finishConversion, recovery };
}
