"use client";

import { toolJobsFromMetadata } from "@/lib/chat-backtest-jobs";
import { toolCardsFromMetadata } from "@/lib/tool-result-card";
import { useEffect, useLayoutEffect, useState, type RefObject } from "react";

import type { ChatFinalPayload } from "@/lib/argus-api";
import type { TranscriptMutation } from "@/lib/chat-transcript-session-cache";
import type {
  ConversationActivityMutationOptions,
  UseConversationActivityResult,
} from "./useConversationActivity";

export type ConversationActivityViewportInputs = Readonly<{
  accountScopeKey: string | null;
  activeRouteConversationId: string | null;
  activeConversationId: string | null;
  activeConversationIdRef: string | null;
  readyTranscriptConversationId: string | null;
  transcriptRoot: HTMLElement | null;
  sentinel: HTMLElement | null;
  transcriptGeneration: number;
  transcriptCanonicalReady: boolean;
  scrollRestorationComplete: boolean;
  hydrationComplete: boolean;
  attentionCursor: string | null;
  manualUnreadGuard: boolean;
  markReadPending: boolean;
}>;

type ObserveLatestActivityOptions = Readonly<{
  root: HTMLElement;
  sentinel: HTMLElement;
  onIntersectionChange: (intersecting: boolean) => void;
}>;

export type ConversationActivityViewportEffectsAdapter = Readonly<{
  observeLatestActivity: (options: ObserveLatestActivityOptions) => () => void;
  subscribeWindowFocus: (callback: () => void) => () => void;
  subscribeWindowBlur: (callback: () => void) => () => void;
  subscribeVisibilityChange: (callback: () => void) => () => void;
  isDocumentVisible: () => boolean;
  isWindowFocused: () => boolean;
}>;

export type ConversationActivityViewportRuntime = Readonly<{
  start: () => void;
  dispose: () => void;
  updateInputs: (inputs: ConversationActivityViewportInputs) => void;
}>;

type CreateConversationActivityViewportRuntimeOptions = Readonly<{
  inputs: ConversationActivityViewportInputs;
  effects: ConversationActivityViewportEffectsAdapter;
  markRead: (
    conversationId: string,
    throughCursor: string,
    options?: ConversationActivityMutationOptions,
  ) => Promise<void>;
  resetViewEpoch: (conversationId: string) => void;
}>;

export type ConversationActivityTranscriptReadiness = Readonly<{
  stageCached: (conversationId: string) => void;
  stageCanonical: (conversationId: string) => void;
  clear: () => void;
  snapshot: (conversationId: string | null) => Readonly<{
    generation: number;
    canonicalReady: boolean;
  }>;
}>;

export const createConversationActivityTranscriptReadiness =
  (): ConversationActivityTranscriptReadiness => {
    let ownerConversationId: string | null = null;
    let generation = 0;
    let canonicalReady = false;
    const stage = (conversationId: string | null, ready: boolean) => {
      ownerConversationId = conversationId;
      canonicalReady = ready;
      generation += 1;
    };
    return {
      stageCached: (conversationId) => stage(conversationId, false),
      stageCanonical: (conversationId) => stage(conversationId, true),
      clear: () => {
        if (ownerConversationId !== null || canonicalReady) stage(null, false);
      },
      snapshot: (conversationId) => ({
        generation,
        canonicalReady:
          Boolean(conversationId) &&
          conversationId === ownerConversationId &&
          canonicalReady,
      }),
    };
  };

export const synchronizeConversationViewRefs = (
  activeConversationIdRef: { current: string | null },
  currentViewRef: { current: string },
  conversationId: string | null,
  currentView: string,
): void => {
  activeConversationIdRef.current = conversationId;
  currentViewRef.current = currentView;
};

export const clearConversationActivityTranscript = (
  readiness: ConversationActivityTranscriptReadiness,
  readyTranscriptConversationIdRef: { current: string | null },
): void => {
  readiness.clear();
  readyTranscriptConversationIdRef.current = null;
};

export const conversationActivityMutationRequiresCanonicalHydration = (
  mutation: TranscriptMutation,
): boolean =>
  mutation !== "message_send" && mutation !== "retry" &&
  mutation !== "recovery" && mutation !== "conversation_rename";

const hasNonEmptyFinalValue = (value: unknown): boolean =>
  typeof value === "string" && value.trim().length > 0;

export const chatFinalPayloadOwnsVisibleTerminalArtifact = (
  payload: ChatFinalPayload,
): boolean => {
  const savedStrategyId = (payload as ChatFinalPayload & {
    saved_strategy_id?: unknown;
  }).saved_strategy_id;
  const persistedMessage = hasNonEmptyFinalValue(payload.message_id);
  return (
    hasNonEmptyFinalValue(payload.assistant_response) ||
    hasNonEmptyFinalValue(payload.assistant_prompt) ||
    payload.confirmation != null ||
    payload.confirmation_cancelled != null ||
    payload.run != null ||
    toolCardsFromMetadata(payload).length > 0 ||
    toolJobsFromMetadata(payload).length > 0 ||
    (persistedMessage && hasNonEmptyFinalValue(payload.stage_outcome)) ||
    (persistedMessage && payload.recovery != null) ||
    hasNonEmptyFinalValue(savedStrategyId)
  );
};

export const promoteVisibleConversationActivityTerminal = (options: Readonly<{
  conversationId: string;
  identityAuthorized: boolean;
  finalPayload: ChatFinalPayload;
  requestKind: "chat_turn" | "backtest_job";
  activeConversationIdRef: { current: string | null };
  currentViewRef: { current: string };
  readyTranscriptConversationIdRef: { current: string | null };
  transcriptReadiness: ConversationActivityTranscriptReadiness;
}>): boolean => {
  if (
    !options.identityAuthorized ||
    !chatFinalPayloadOwnsVisibleTerminalArtifact(options.finalPayload) ||
    options.requestKind !== "chat_turn" ||
    options.currentViewRef.current !== "chat" ||
    options.activeConversationIdRef.current !== options.conversationId
  ) return false;
  options.transcriptReadiness.stageCanonical(options.conversationId);
  options.readyTranscriptConversationIdRef.current = options.conversationId;
  return true;
};

type ConversationActivityTerminalRequest = Readonly<{
  conversationId: string;
  kind: "chat_turn" | "backtest_job";
}>;

type ConversationActivityTerminalReadinessSessionOptions = Readonly<{
  getRequest: () => ConversationActivityTerminalRequest;
  activeConversationIdRef: { current: string | null };
  currentViewRef: { current: string };
  readyTranscriptConversationIdRef: { current: string | null };
  transcriptReadiness: ConversationActivityTranscriptReadiness;
  reconcileCanonical: (conversationId: string) => void;
}>;

export type ConversationActivityTerminalReadinessSession = Readonly<{
  stage: () => boolean;
  accept: (payload: ChatFinalPayload, identityAuthorized: boolean) => boolean;
  reject: (identityAuthorized: boolean) => boolean;
  finish: (identityAuthorized: boolean) => boolean;
}>;

export const promoteCanonicalConversationActivityTranscript = (options: Readonly<{
  conversationId: string;
  activeConversationIdRef: { current: string | null };
  currentViewRef: { current: string };
  readyTranscriptConversationIdRef: { current: string | null };
  transcriptReadiness: ConversationActivityTranscriptReadiness;
}>): boolean => {
  if (
    options.currentViewRef.current !== "chat" ||
    options.activeConversationIdRef.current !== options.conversationId
  ) return false;
  options.transcriptReadiness.stageCanonical(options.conversationId);
  options.readyTranscriptConversationIdRef.current = options.conversationId;
  return true;
};

export const createConversationActivityTerminalReadinessSession = (
  options: ConversationActivityTerminalReadinessSessionOptions,
): ConversationActivityTerminalReadinessSession => {
  let settled = false;
  const visibleRequest = (): ConversationActivityTerminalRequest | null => {
    const request = options.getRequest();
    return options.currentViewRef.current === "chat" &&
      options.activeConversationIdRef.current === request.conversationId
      ? request
      : null;
  };
  return {
    stage: () => {
      const request = visibleRequest();
      if (!request) return false;
      options.transcriptReadiness.stageCached(request.conversationId);
      return true;
    },
    accept: (payload, identityAuthorized) => {
      if (settled || !identityAuthorized) return false;
      const request = visibleRequest();
      if (!request) return false;
      const promoted = promoteVisibleConversationActivityTerminal({
        conversationId: request.conversationId,
        identityAuthorized,
        finalPayload: payload,
        requestKind: request.kind,
        activeConversationIdRef: options.activeConversationIdRef,
        currentViewRef: options.currentViewRef,
        readyTranscriptConversationIdRef:
          options.readyTranscriptConversationIdRef,
        transcriptReadiness: options.transcriptReadiness,
      });
      if (promoted) settled = true;
      return promoted;
    },
    reject: (identityAuthorized) => {
      if (settled || !identityAuthorized) return false;
      const request = visibleRequest();
      if (!request || request.kind !== "chat_turn") return false;
      // A pre-admission rejection adds no canonical assistant artifact. Keep the
      // existing transcript and the local question available for editing.
      settled = promoteCanonicalConversationActivityTranscript({
        ...options,
        conversationId: request.conversationId,
      });
      return settled;
    },
    finish: (identityAuthorized) => {
      if (settled || !identityAuthorized) return false;
      const request = visibleRequest();
      if (!request || request.kind === "backtest_job") return false;
      settled = true;
      options.reconcileCanonical(request.conversationId);
      return true;
    },
  };
};

const createBrowserEffectsAdapter =
  (): ConversationActivityViewportEffectsAdapter => ({
    observeLatestActivity: ({ root, sentinel, onIntersectionChange }) => {
      if (typeof IntersectionObserver === "undefined") return () => undefined;
      const observer = new IntersectionObserver(
        (entries) => {
          const entry = entries.find((candidate) => candidate.target === sentinel);
          if (entry) onIntersectionChange(entry.isIntersecting);
        },
        { root, threshold: 1 },
      );
      observer.observe(sentinel);
      return () => observer.disconnect();
    },
    subscribeWindowFocus: (callback) => {
      if (typeof window === "undefined") return () => undefined;
      window.addEventListener("focus", callback);
      return () => window.removeEventListener("focus", callback);
    },
    subscribeWindowBlur: (callback) => {
      if (typeof window === "undefined") return () => undefined;
      window.addEventListener("blur", callback);
      return () => window.removeEventListener("blur", callback);
    },
    subscribeVisibilityChange: (callback) => {
      if (typeof document === "undefined") return () => undefined;
      document.addEventListener("visibilitychange", callback);
      return () => document.removeEventListener("visibilitychange", callback);
    },
    isDocumentVisible: () =>
      typeof document === "undefined" || document.visibilityState === "visible",
    isWindowFocused: () =>
      typeof document === "undefined" || document.hasFocus(),
  });

const readKey = (
  accountScopeKey: string,
  conversationId: string,
  cursor: string,
): string => JSON.stringify([accountScopeKey, conversationId, cursor]);

const proofFingerprint = (inputs: ConversationActivityViewportInputs): string =>
  JSON.stringify([
    inputs.accountScopeKey,
    inputs.activeRouteConversationId,
    inputs.activeConversationId,
    inputs.activeConversationIdRef,
    inputs.readyTranscriptConversationId,
    inputs.transcriptRoot?.dataset.conversationId ?? null,
    inputs.transcriptGeneration,
    inputs.transcriptCanonicalReady,
    inputs.scrollRestorationComplete,
    inputs.hydrationComplete,
    inputs.attentionCursor,
    inputs.manualUnreadGuard,
  ]);

const observerOwnershipFingerprint = (
  inputs: ConversationActivityViewportInputs,
): string =>
  JSON.stringify([
    inputs.accountScopeKey,
    inputs.activeRouteConversationId,
    inputs.activeConversationId,
    inputs.activeConversationIdRef,
    inputs.readyTranscriptConversationId,
    inputs.transcriptRoot?.dataset.conversationId ?? null,
    inputs.transcriptGeneration,
    inputs.transcriptCanonicalReady,
    inputs.scrollRestorationComplete,
  ]);

class ConversationActivityViewportOwner
  implements ConversationActivityViewportRuntime
{
  private inputs: ConversationActivityViewportInputs;
  private started = false;
  private sentinelIntersecting = false;
  private meaningfulTrigger = 0;
  private observerEpoch = 0;
  private lifecycleEpoch = 0;
  private accountEpoch = 0;
  private readSequence = 0;
  private environmentFingerprint = "";
  private cancelObserver: (() => void) | null = null;
  private unsubscribeFocus: (() => void) | null = null;
  private unsubscribeBlur: (() => void) | null = null;
  private unsubscribeVisibility: (() => void) | null = null;
  private readonly acknowledgedReads = new Set<string>();
  private readonly inFlightReads = new Map<string, string>();
  private readonly resolvedReads = new Map<
    string,
    Readonly<{
      accountScopeKey: string;
      conversationId: string;
      cursor: string;
      token: string;
    }>
  >();
  private readonly failedReadTrigger = new Map<string, number>();

  constructor(
    private readonly options: CreateConversationActivityViewportRuntimeOptions,
  ) {
    this.inputs = options.inputs;
  }

  start = (): void => {
    if (this.started) return;
    this.started = true;
    this.lifecycleEpoch += 1;
    this.environmentFingerprint = this.currentEnvironmentFingerprint();
    this.unsubscribeFocus = this.options.effects.subscribeWindowFocus(
      this.handleEnvironmentChange,
    );
    this.unsubscribeBlur = this.options.effects.subscribeWindowBlur(
      this.handleEnvironmentChange,
    );
    this.unsubscribeVisibility =
      this.options.effects.subscribeVisibilityChange(
        this.handleEnvironmentChange,
      );
    this.attachObserver();
  };

  dispose = (): void => {
    if (!this.started) return;
    this.started = false;
    this.lifecycleEpoch += 1;
    this.observerEpoch += 1;
    this.cancelObserver?.();
    this.cancelObserver = null;
    this.unsubscribeFocus?.();
    this.unsubscribeBlur?.();
    this.unsubscribeVisibility?.();
    this.unsubscribeFocus = null;
    this.unsubscribeBlur = null;
    this.unsubscribeVisibility = null;
    this.sentinelIntersecting = false;
    this.inFlightReads.clear();
    this.resolvedReads.clear();
  };

  updateInputs = (inputs: ConversationActivityViewportInputs): void => {
    const previous = this.inputs;
    const accountChanged =
      previous.accountScopeKey !== inputs.accountScopeKey;
    if (
      !accountChanged &&
      previous.activeConversationId &&
      previous.activeConversationId !== inputs.activeConversationId
    ) {
      this.options.resetViewEpoch(previous.activeConversationId);
    }
    const observerChanged =
      accountChanged ||
      previous.transcriptRoot !== inputs.transcriptRoot ||
      previous.sentinel !== inputs.sentinel ||
      observerOwnershipFingerprint(previous) !==
        observerOwnershipFingerprint(inputs);
    const proofChanged = proofFingerprint(previous) !== proofFingerprint(inputs);
    this.inputs = inputs;
    if (accountChanged) this.resetAccountScope();
    if (proofChanged) this.meaningfulTrigger += 1;
    this.settleResolvedReads();
    if (observerChanged && this.started) this.attachObserver();
    this.evaluateReadProof();
  };

  private attachObserver(): void {
    this.observerEpoch += 1;
    const epoch = this.observerEpoch;
    this.cancelObserver?.();
    this.cancelObserver = null;
    this.sentinelIntersecting = false;
    const { transcriptRoot, sentinel } = this.inputs;
    if (!this.started || !transcriptRoot || !sentinel) return;
    this.cancelObserver = this.options.effects.observeLatestActivity({
      root: transcriptRoot,
      sentinel,
      onIntersectionChange: (intersecting) => {
        if (
          !this.started ||
          epoch !== this.observerEpoch
        ) {
          return;
        }
        if (intersecting !== this.sentinelIntersecting) {
          this.sentinelIntersecting = intersecting;
          this.meaningfulTrigger += 1;
        }
        if (intersecting) this.evaluateReadProof();
      },
    });
  }

  private handleEnvironmentChange = (): void => {
    if (!this.started) return;
    const nextFingerprint = this.currentEnvironmentFingerprint();
    if (nextFingerprint === this.environmentFingerprint) return;
    this.environmentFingerprint = nextFingerprint;
    this.meaningfulTrigger += 1;
    this.evaluateReadProof();
  };

  private currentEnvironmentFingerprint(): string {
    return JSON.stringify([
      this.options.effects.isDocumentVisible(),
      this.options.effects.isWindowFocused(),
    ]);
  }

  private proofConversation(): Readonly<{
    accountScopeKey: string;
    conversationId: string;
    cursor: string;
  }> | null {
    const accountScopeKey = this.inputs.accountScopeKey;
    const conversationId = this.inputs.activeConversationId;
    const cursor = this.inputs.attentionCursor;
    if (
      !accountScopeKey ||
      !conversationId ||
      !cursor ||
      this.inputs.activeRouteConversationId !== conversationId ||
      this.inputs.activeConversationIdRef !== conversationId ||
      this.inputs.readyTranscriptConversationId !== conversationId ||
      this.inputs.transcriptRoot?.dataset.conversationId !== conversationId ||
      !this.inputs.sentinel ||
      !this.inputs.transcriptCanonicalReady ||
      !this.inputs.scrollRestorationComplete ||
      !this.inputs.hydrationComplete ||
      this.inputs.manualUnreadGuard ||
      this.inputs.markReadPending ||
      !this.sentinelIntersecting ||
      !this.options.effects.isDocumentVisible() ||
      !this.options.effects.isWindowFocused()
    ) {
      return null;
    }
    return { accountScopeKey, conversationId, cursor };
  }

  private evaluateReadProof(): void {
    if (!this.started) return;
    const proof = this.proofConversation();
    if (!proof) return;
    const key = readKey(
      proof.accountScopeKey,
      proof.conversationId,
      proof.cursor,
    );
    if (
      this.acknowledgedReads.has(key) ||
      this.inFlightReads.has(key) ||
      this.failedReadTrigger.get(key) === this.meaningfulTrigger
    ) {
      return;
    }
    const token = `${this.accountEpoch}:${this.lifecycleEpoch}:${++this.readSequence}`;
    const accountEpoch = this.accountEpoch;
    const lifecycleEpoch = this.lifecycleEpoch;
    this.inFlightReads.set(key, token);
    void this.options
      .markRead(proof.conversationId, proof.cursor, { notifySuccess: false })
      .then(() => {
        if (
          accountEpoch !== this.accountEpoch ||
          lifecycleEpoch !== this.lifecycleEpoch ||
          this.inFlightReads.get(key) !== token
        ) {
          return;
        }
        this.resolvedReads.set(key, { ...proof, token });
        this.settleResolvedReads();
      })
      .catch(() => {
        if (
          accountEpoch !== this.accountEpoch ||
          lifecycleEpoch !== this.lifecycleEpoch ||
          this.inFlightReads.get(key) !== token
        ) {
          return;
        }
        this.failedReadTrigger.set(key, this.meaningfulTrigger);
        this.inFlightReads.delete(key);
      });
  }

  private settleResolvedReads(): void {
    for (const [key, proof] of this.resolvedReads) {
      if (this.inFlightReads.get(key) !== proof.token) {
        this.resolvedReads.delete(key);
        continue;
      }
      if (this.inputs.activeConversationId !== proof.conversationId) {
        this.resolvedReads.delete(key);
        this.inFlightReads.delete(key);
        continue;
      }
      if (this.inputs.markReadPending) continue;
      if (this.inputs.attentionCursor !== proof.cursor) {
        this.acknowledgedReads.add(key);
        this.failedReadTrigger.delete(key);
      } else {
        this.failedReadTrigger.set(key, this.meaningfulTrigger);
      }
      this.resolvedReads.delete(key);
      this.inFlightReads.delete(key);
    }
  }

  private resetAccountScope(): void {
    this.accountEpoch += 1;
    this.meaningfulTrigger = 0;
    this.readSequence = 0;
    this.sentinelIntersecting = false;
    this.acknowledgedReads.clear();
    this.inFlightReads.clear();
    this.resolvedReads.clear();
    this.failedReadTrigger.clear();
  }
}

export const createConversationActivityViewportRuntime = (
  options: CreateConversationActivityViewportRuntimeOptions,
): ConversationActivityViewportRuntime =>
  new ConversationActivityViewportOwner(options);

type UseConversationActivityViewportOptions = Readonly<{
  activity: Pick<
    UseConversationActivityResult,
    | "state"
    | "hasManualUnreadGuard"
    | "isMutationPending"
    | "markRead"
    | "resetViewEpoch"
  >;
  accountScopeKey: string | null;
  activeRouteConversationId: string | null;
  activeConversationId: string | null;
  activeConversationIdRef: RefObject<string | null>;
  readyTranscriptConversationIdRef: RefObject<string | null>;
  transcriptRootRef: RefObject<HTMLDivElement | null>;
  sentinelRef: RefObject<HTMLDivElement | null>;
  transcriptReadiness: ConversationActivityTranscriptReadiness;
  pendingScrollRestoreRef: RefObject<{ conversationId: string } | null>;
  pendingMessageAnchorRef: RefObject<{ conversationId: string } | null>;
  hydrationComplete: boolean;
  testEffects?: ConversationActivityViewportEffectsAdapter;
}>;

export function useConversationActivityViewport(
  options: UseConversationActivityViewportOptions,
): void {
  const snapshotInputs = (): ConversationActivityViewportInputs => {
    const conversationId = options.activeConversationId;
    const record = conversationId
      ? options.activity.state.byConversationId[conversationId]
      : undefined;
    const readiness = options.transcriptReadiness.snapshot(conversationId);
    return {
      accountScopeKey: options.accountScopeKey,
      activeRouteConversationId: options.activeRouteConversationId,
      activeConversationId: conversationId,
      activeConversationIdRef: options.activeConversationIdRef.current,
      readyTranscriptConversationId:
        options.readyTranscriptConversationIdRef.current,
      transcriptRoot: options.transcriptRootRef.current,
      sentinel: options.sentinelRef.current,
      transcriptGeneration: readiness.generation,
      transcriptCanonicalReady: readiness.canonicalReady,
      scrollRestorationComplete:
        options.pendingScrollRestoreRef.current?.conversationId !==
          conversationId &&
        options.pendingMessageAnchorRef.current?.conversationId !==
          conversationId,
      hydrationComplete: options.hydrationComplete,
      attentionCursor: record?.canonical?.attention.cursor ?? null,
      manualUnreadGuard:
        options.activity.hasManualUnreadGuard(conversationId),
      markReadPending: conversationId
        ? options.activity.isMutationPending(conversationId, "mark_read")
        : false,
    };
  };
  const [runtime] = useState(() =>
    createConversationActivityViewportRuntime({
      inputs: snapshotInputs(),
      effects: options.testEffects ?? createBrowserEffectsAdapter(),
      markRead: options.activity.markRead,
      resetViewEpoch: options.activity.resetViewEpoch,
    }),
  );

  useLayoutEffect(() => {
    runtime.updateInputs(snapshotInputs());
  });
  useEffect(() => {
    runtime.start();
    return runtime.dispose;
  }, [runtime]);
}
