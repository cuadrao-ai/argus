import type { Session, SupabaseClient } from "@supabase/supabase-js";
import { observeBrowserAuth } from "./browser-auth-generation";
import { getSupabaseClient } from "./supabase-client";

export type SessionRecoveryState =
  | { kind: "pending" | "missing" | "error"; busy: boolean }
  | { kind: "same-owner"; userId: string; scope: number; busy: false }
  | { kind: "different-owner"; userId: string; busy: boolean; canContinue: boolean };

type RecoveryOptions = {
  initialOwner?: string | null;
  allowAnonymous?: boolean;
  onIdentityChange?: (userId: string | null) => void;
  verifyAccess?: (userId: string, signal: AbortSignal) => Promise<AccessOutcome>;
};
type AccessOutcome = "allowed" | "missing" | "error";

export function createSessionRecovery({ initialOwner = null, allowAnonymous = false, onIdentityChange, verifyAccess }: RecoveryOptions = {}) {
  let state: SessionRecoveryState = initialOwner
    ? { kind: "same-owner", userId: initialOwner, scope: 0, busy: false }
    : { kind: "pending", busy: false };
  let owner = initialOwner;
  let changedAccount = false;
  let scope = 0;
  let active = false;
  let converting = false;
  let revision = 0;
  let checking = false;
  let signedOutDuringCheck = false;
  let client: SupabaseClient | null = null;
  let unsubscribe: (() => void) | undefined;
  let access: { controller: AbortController; signedOut: boolean } | null = null;
  const listeners = new Set<() => void>();
  const retirement = new Set<() => void>();

  const publish = (next: SessionRecoveryState) => {
    state = next;
    for (const listener of listeners) listener();
  };
  const supersedeCheck = () => { revision += 1; checking = false; signedOutDuringCheck = false; };
  const stopAccess = () => { access?.controller.abort(); access = null; };
  const userIdOf = (session: Session | null) => {
    if (!session || (!allowAnonymous && session.user.is_anonymous)) return null;
    return session.user.id;
  };
  const retire = () => {
    if (state.kind === "same-owner") for (const cleanup of retirement) cleanup();
  };
  const close = (kind: "pending" | "missing" | "error") => {
    if (kind !== "pending") stopAccess();
    observeBrowserAuth(null);
    retire();
    onIdentityChange?.(null);
    const busy = kind === "pending";
    if (state.kind !== kind || state.busy !== busy) publish({ kind, busy });
  };

  const checkAccess = async (userId: string, navigate?: () => void) => {
    if (!active || access || state.kind !== "different-owner" || state.userId !== userId) return;
    const attempt = { controller: new AbortController(), signedOut: false };
    const { signal } = attempt.controller;
    access = attempt;
    if (!state.busy) publish({ kind: "different-owner", userId, busy: true, canContinue: false });
    const current = () => active && access === attempt;
    let outcome: AccessOutcome;
    try {
      // Keep SDK work outside the auth callback, which runs under its session lock.
      await Promise.resolve();
      if (!current()) return;
      signal.throwIfAborted();
      if (verifyAccess) {
        outcome = await verifyAccess(userId, signal);
      } else {
        const result = await client?.auth.getSession();
        const currentUserId = result && userIdOf(result.data.session);
        outcome = !result || result.error ? "error" : !currentUserId ? "missing" : currentUserId === userId ? "allowed" : "error";
      }
    } catch (error) { outcome = attempt.signedOut && error === signal.reason ? "missing" : "error"; }
    if (!current()) return;
    access = null;
    if (outcome !== "allowed") { close(outcome); return; }
    if (attempt.signedOut) { close("missing"); return; }
    if (navigate) { navigate(); return; }
    publish({ kind: "different-owner", userId, busy: false, canContinue: true });
  };

  const accept = (userId: string | null) => {
    if (!userId) { close("missing"); return; }
    if (state.kind === "same-owner" && state.userId === userId) return;
    observeBrowserAuth(userId);
    if (owner !== null && owner !== userId) changedAccount = true;
    owner ??= userId;
    if (changedAccount) {
      if (state.kind === "different-owner" && state.userId === userId) {
        if (!state.canContinue) void checkAccess(userId);
        return;
      }
      stopAccess();
      retire();
      onIdentityChange?.(userId);
      publish({ kind: "different-owner", userId, busy: true, canContinue: false });
      void checkAccess(userId);
    } else {
      onIdentityChange?.(userId);
      publish({ kind: "same-owner", userId, scope: ++scope, busy: false });
    }
  };

  const connect = () => {
    if (client) return client;
    const next = getSupabaseClient();
    if (!next) throw new Error("Auth client unavailable");
    let subscribed = true;
    const { data } = next.auth.onAuthStateChange((event, session) => {
      if (!active || !subscribed || converting) return;
      // The startup read owns initial identity. Its callback can be late or error-derived.
      if (event === "INITIAL_SESSION" || (!session && event !== "SIGNED_OUT")) return;
      if (event === "SIGNED_OUT" && (checking || access)) {
        // A failed refresh can emit SIGNED_OUT before the read returns its error.
        if (checking) signedOutDuringCheck = true;
        if (access) { access.signedOut = true; access.controller.abort(); }
        close("pending");
        return;
      }
      supersedeCheck();
      accept(userIdOf(session));
    });
    unsubscribe = () => { subscribed = false; data.subscription.unsubscribe(); };
    client = next;
    return next;
  };

  const check = async () => {
    if (!active || converting || checking || access) return;
    const attempt = ++revision;
    checking = true;
    signedOutDuringCheck = false;
    if (state.kind === "error") publish({ kind: "error", busy: true });
    const current = () => active && revision === attempt;
    try {
      const auth = connect().auth;
      if (!current()) return;
      const { data, error } = await auth.getSession();
      if (!current()) return;
      if (error) close("error");
      else accept(signedOutDuringCheck ? null : userIdOf(data.session));
    } catch {
      if (current()) close("error");
    } finally {
      if (current()) checking = false;
    }
  };
  const onFocus = () => { void check(); };
  const onVisible = () => { if (document.visibilityState === "visible") onFocus(); };

  return {
    getSnapshot: () => state,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    onRetire(cleanup: () => void) { retirement.add(cleanup); return () => { retirement.delete(cleanup); }; },
    start() {
      active = true;
      window.addEventListener("focus", onFocus);
      document.addEventListener("visibilitychange", onVisible);
      void check();
      return () => {
        active = false;
        supersedeCheck();
        stopAccess();
        unsubscribe?.();
        client = null;
        window.removeEventListener("focus", onFocus);
        document.removeEventListener("visibilitychange", onVisible);
      };
    },
    retry() { void check(); },
    continueTo(navigate: () => void) {
      if (state.kind !== "different-owner" || !state.canContinue) return;
      supersedeCheck();
      void checkAccess(state.userId, navigate);
    },
    recheckAfterMismatch() {
      if (!active || converting) return;
      supersedeCheck();
      close("error");
      void check();
    },
    beginConversion() { converting = true; supersedeCheck(); stopAccess(); },
    finishConversion(userId: string | null) {
      if (!active || !converting) return;
      converting = false;
      owner = userId;
      accept(userId);
    },
  };
}

export type SessionRecovery = ReturnType<typeof createSessionRecovery>;
