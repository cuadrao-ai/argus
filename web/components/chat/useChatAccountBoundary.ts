"use client";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { getSupabaseClient } from "@/lib/supabase-client";
import type { ChatRequestSessionController } from "@/lib/chat-request-session";

// Supabase owns identity; the existing request controller owns invalidation.
export function useChatAccountBoundary(userId: string | null, requests: ChatRequestSessionController, clearView: () => void) {
  const owner = useRef(userId);
  const clear = useRef(clearView);
  const invalidated = useRef(false);
  const conversionPending = useRef(false);
  const admission = useRef(new AbortController());
  const [expired, setExpired] = useState(false);
  const invalidate = useCallback(() => {
    if (invalidated.current) return;
    invalidated.current = true;
    admission.current.abort();
    requests.synchronizeAccountScope(null);
    clear.current();
    setExpired(true);
  }, [requests]);
  useLayoutEffect(() => {
    clear.current = clearView;
    if (owner.current === null) owner.current = userId;
    else if (!conversionPending.current && owner.current !== userId) invalidate();
  }, [userId, clearView, invalidate]);
  useEffect(() => {
    if (process.env.NEXT_PUBLIC_MOCK_AUTH === "true") return;
    const client = getSupabaseClient();
    if (!client) return;
    let active = true;
    const check = (nextId: string | null) => {
      if (active && !conversionPending.current && owner.current !== null && nextId !== owner.current) invalidate();
    };
    const { data } = client.auth.onAuthStateChange((_event, session) => check(session?.user.id ?? null));
    const recheck = () => { void client.auth.getSession().then(({ data, error }) => !error && check(data.session?.user.id ?? null)).catch(() => undefined); };
    recheck();
    window.addEventListener("focus", recheck);
    return () => { active = false; data.subscription.unsubscribe(); window.removeEventListener("focus", recheck); };
  }, [userId, invalidate]);
  const beginConversion = useCallback(() => {
    conversionPending.current = true;
    admission.current.abort();
    requests.synchronizeAccountScope(null);
  }, [requests]);
  const finishConversion = useCallback((nextUserId: string | null) => {
    conversionPending.current = false;
    if (!nextUserId) { invalidate(); return; }
    owner.current = nextUserId;
    admission.current = new AbortController();
    requests.synchronizeAccountScope(nextUserId);
  }, [invalidate, requests]);
  return { expired, invalidated, conversionPending, admission, invalidate, beginConversion, finishConversion };
}
