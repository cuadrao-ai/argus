import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";

import { createConversationActivityRuntime } from "../components/chat/useConversationActivity";
import type { ConversationActivity, HistoryItem } from "../lib/argus-api";
import type { ChatFinalPayload } from "../lib/argus-api";
import type { ConversationActivityHistorySnapshot } from "../lib/conversation-activity-state";
import {
  createChatRequestSessionController,
  type ChatRequestCallbackKind,
  visibleRequestStatus,
} from "../lib/chat-request-session";
import { activeConversationRouteStateFromUrl } from "../lib/chat-conversation-routing";
import {
  ConversationActivityLiveRegion,
  consumeConversationActivityAnnouncement,
  conversationActivityAnnouncementDescriptor,
  conversationActivityAnnouncementMessage,
} from "../components/chat/ConversationActivityAnnouncement";

const interpolateDefault = (
  _key: string,
  options: Readonly<{ defaultValue: string; title: string }>,
): string => options.defaultValue.replace("{{title}}", options.title);

const chatInterfaceSource = readFileSync(
  join(import.meta.dir, "../components/chat/ChatInterface.tsx"),
  "utf-8",
);

const idleActivity = (): ConversationActivity => ({
  operation: { status: "idle", kind: null, updated_at: null },
  attention: { status: "none", cursor: null },
});

const chat = (conversationId: string): HistoryItem => ({
  type: "chat",
  id: conversationId,
  conversation_id: conversationId,
  title: conversationId,
  title_source: "ai_generated",
  subtitle: "Recent work",
  pinned: false,
  created_at: "2026-08-01T12:00:00Z",
  activity: idleActivity(),
});

type Deferred<T> = Readonly<{
  promise: Promise<T>;
  resolve: (value: T) => void;
}>;

const deferred = <T,>(): Deferred<T> => {
  let resolvePromise: ((value: T) => void) | null = null;
  const promise = new Promise<T>((resolve) => {
    resolvePromise = resolve;
  });
  return {
    promise,
    resolve: (value) => resolvePromise?.(value),
  };
};

const drainMicrotasks = async (): Promise<void> => {
  await Promise.resolve();
  await Promise.resolve();
};

function requestHarness(options: Readonly<{
  refreshHistory?: () =>
    | ConversationActivityHistorySnapshot
    | readonly HistoryItem[]
    | void
    | Promise<ConversationActivityHistorySnapshot | readonly HistoryItem[] | void>;
}> = {}) {
  let visibleConversationId = "conversation-a";
  let currentView = "chat";
  let routeUrl = "http://localhost:3000/chat?conversation=conversation-a";
  const invalidations: string[] = [];
  const runtime = createConversationActivityRuntime({
    historyItems: [],
    activeConversationId: "conversation-a",
    accountScopeKey: "account-a",
    refreshHistory: options.refreshHistory ?? (() => undefined),
    invalidateInactiveTranscript: (conversationId) => {
      invalidations.push(conversationId);
    },
    onMutationNotice: () => undefined,
    patchActivity: async () => idleActivity(),
    getActivity: async () => idleActivity(),
    effects: {
      schedulePoll: () => () => undefined,
      subscribeWindowFocus: () => () => undefined,
      subscribeVisibilityChange: () => () => undefined,
      isDocumentVisible: () => true,
    },
  });
  const requestIds = ["request-a", "request-b", "request-c"];
  const controller = createChatRequestSessionController({
    activity: runtime,
    accountScopeKey: "account-a",
    routeContext: {
      activeConversationId: visibleConversationId,
      currentView,
      routeState: activeConversationRouteStateFromUrl(routeUrl),
    },
    createRequestId: () => requestIds.shift() ?? "request-extra",
  });
  return {
    runtime,
    controller,
    invalidations,
    showConversation(conversationId: string) {
      visibleConversationId = conversationId;
      currentView = "chat";
      routeUrl = `http://localhost:3000/chat?conversation=${conversationId}`;
      runtime.updateActiveConversationId(conversationId);
      controller.updateRouteContext({
        activeConversationId: visibleConversationId,
        currentView,
        routeState: activeConversationRouteStateFromUrl(routeUrl),
      });
    },
    showSettings() {
      currentView = "settings";
      routeUrl = "http://localhost:3000/settings";
      controller.updateRouteContext({
        activeConversationId: visibleConversationId,
        currentView,
        routeState: activeConversationRouteStateFromUrl(routeUrl),
      });
    },
  };
}

describe("production chat request-session ownership", () => {
  test("hides stale transport status as soon as canonical activity unlocks", () => {
    expect(visibleRequestStatus("Checking what completed…", true)).toBe(
      "Checking what completed…",
    );
    expect(visibleRequestStatus("Checking what completed…", false)).toBeNull();
    expect(visibleRequestStatus(null, true)).toBeNull();
  });

  test("routes every callback kind by request and visible conversation ownership", () => {
    const harness = requestHarness();
    const requestA = harness.controller.begin("conversation-a", "chat_turn");
    expect(requestA).not.toBeNull();
    harness.showConversation("conversation-b");
    const requestB = harness.controller.begin("conversation-b", "chat_turn");
    expect(requestB).not.toBeNull();

    const backgroundOwned: ChatRequestCallbackKind[] = [
      "stage",
      "title",
      "done",
      "error",
      "catch",
      "run_replay",
      "ambiguity",
    ];
    const visibleOnly: ChatRequestCallbackKind[] = [
      "token",
      "final",
      "save_cleanup",
      "cancel",
    ];
    for (const kind of backgroundOwned) {
      expect(
        harness.controller.authorize(requestA!, kind, "conversation-a"),
      ).toBe(true);
    }
    for (const kind of visibleOnly) {
      expect(
        harness.controller.authorize(requestA!, kind, "conversation-a"),
      ).toBe(false);
      expect(
        harness.controller.authorize(requestB!, kind, "conversation-b"),
      ).toBe(true);
    }
    expect(
      harness.controller.authorize(requestA!, "title", "conversation-b"),
    ).toBe(false);
    expect(harness.controller.canWriteVisible(requestA!)).toBe(false);
    expect(harness.controller.canWriteVisible(requestB!)).toBe(true);

    harness.showSettings();
    expect(harness.controller.authorize(requestB!, "token")).toBe(false);
    expect(harness.controller.authorize(requestB!, "done")).toBe(true);
  });

  test("transport completion stays checking and is idempotent until canonical idle", () => {
    const harness = requestHarness();
    const requestA = harness.controller.begin("conversation-a", "backtest_job");
    expect(requestA).not.toBeNull();
    harness.showConversation("conversation-b");
    const requestB = harness.controller.begin("conversation-b", "chat_turn");
    expect(requestB).not.toBeNull();

    expect(harness.controller.finishTransport(requestA!)).toBe(true);
    expect(harness.controller.finishTransport(requestA!)).toBe(false);
    expect(harness.runtime.isRequestCurrent("conversation-a", "request-a")).toBe(
      true,
    );
    expect(harness.runtime.getState().byConversationId["conversation-a"]?.request?.status)
      .toBe("checking");
    expect(harness.runtime.isRequestCurrent("conversation-b", "request-b")).toBe(
      true,
    );

    const transportFinishedRevision = harness.runtime.getState()
      .byConversationId["conversation-a"]?.request?.transportFinishedRevision;
    expect(transportFinishedRevision).toBeNumber();
    harness.runtime.updateInputs({
      historyItems: [chat("conversation-a")],
      historyActivityRevision: transportFinishedRevision! + 1,
      activeConversationId: "conversation-b",
      accountScopeKey: "account-a",
    });

    expect(harness.controller.authorize(requestA!, "done")).toBe(false);
    expect(harness.runtime.isRequestCurrent("conversation-b", "request-b")).toBe(
      true,
    );
    expect(harness.invalidations).toEqual(["conversation-a"]);
  });

  test("keeps final authorized when newer idle history arrives before transport finishes", async () => {
    const preFinalRefresh = deferred<ConversationActivityHistorySnapshot>();
    const harness = requestHarness({
      refreshHistory: () => preFinalRefresh.promise,
    });
    const request = harness.controller.begin("conversation-a", "chat_turn");
    expect(request).not.toBeNull();

    preFinalRefresh.resolve({
      items: [chat("conversation-a")],
      revision: request!.identity.issuedRevision + 1,
    });
    await drainMicrotasks();

    expect(harness.runtime.isRequestCurrent("conversation-a", "request-a")).toBe(
      true,
    );
    expect(harness.runtime.isConversationLocked("conversation-a")).toBe(true);
    expect(harness.controller.authorize(request!, "final")).toBe(true);
  });

  test("settles on a post-done canonical refresh even when idle truth is identical", async () => {
    const preFinalRefresh = deferred<ConversationActivityHistorySnapshot>();
    const postDoneRefresh = deferred<ConversationActivityHistorySnapshot>();
    const refreshes = [preFinalRefresh, postDoneRefresh];
    let refreshIndex = 0;
    const harness = requestHarness({
      refreshHistory: () => refreshes[refreshIndex++]!.promise,
    });
    const request = harness.controller.begin("conversation-a", "chat_turn");
    expect(request).not.toBeNull();

    preFinalRefresh.resolve({
      items: [chat("conversation-a")],
      revision: request!.identity.issuedRevision + 1,
    });
    await drainMicrotasks();
    expect(harness.controller.authorize(request!, "final")).toBe(true);
    expect(harness.controller.authorize(request!, "done")).toBe(true);
    expect(harness.controller.finishTransport(request!)).toBe(true);

    const transportFinishedRevision = harness.runtime.getState()
      .byConversationId["conversation-a"]?.request?.transportFinishedRevision;
    expect(transportFinishedRevision).toBeNumber();
    postDoneRefresh.resolve({
      items: [chat("conversation-a")],
      revision: transportFinishedRevision! + 1,
    });
    await drainMicrotasks();

    expect(harness.runtime.isRequestCurrent("conversation-a", "request-a")).toBe(
      false,
    );
  });

  test("404 transfer retires only the nonexistent owner and keeps the same request id", () => {
    const harness = requestHarness();
    const requestA = harness.controller.begin("conversation-a", "chat_turn");
    expect(requestA).not.toBeNull();

    const transferred = harness.controller.transfer(
      requestA!,
      "conversation-created",
    );

    expect(transferred?.identity.requestId).toBe("request-a");
    expect(transferred?.controller).toBe(requestA?.controller);
    expect(harness.controller.authorize(requestA!, "catch")).toBe(false);
    expect(harness.controller.authorize(transferred!, "catch")).toBe(true);
    expect(harness.runtime.isConversationLocked("conversation-a")).toBe(false);
    expect(harness.runtime.isConversationLocked("conversation-created")).toBe(true);
  });

  test("an old save cleanup cannot mutate a newer same-conversation request", () => {
    const harness = requestHarness();
    const oldSave = harness.controller.begin("conversation-a", "chat_turn");
    expect(oldSave).not.toBeNull();
    expect(harness.controller.finishTransport(oldSave!)).toBe(true);
    const transportFinishedRevision = harness.runtime.getState()
      .byConversationId["conversation-a"]?.request?.transportFinishedRevision;
    expect(transportFinishedRevision).toBeNumber();
    harness.runtime.updateInputs({
      historyItems: [chat("conversation-a")],
      historyActivityRevision: transportFinishedRevision! + 1,
      activeConversationId: "conversation-a",
      accountScopeKey: "account-a",
    });
    const newSave = harness.controller.begin("conversation-a", "chat_turn");

    expect(newSave).not.toBeNull();
    expect(harness.controller.authorize(oldSave!, "save_cleanup")).toBe(false);
    expect(harness.controller.authorize(newSave!, "save_cleanup")).toBe(true);
  });

  test("synchronous account reset aborts A and B and rejects every late callback", () => {
    const harness = requestHarness();
    const requestA = harness.controller.begin("conversation-a", "chat_turn");
    harness.showConversation("conversation-b");
    const requestB = harness.controller.begin("conversation-b", "backtest_job");
    expect(requestA).not.toBeNull();
    expect(requestB).not.toBeNull();

    expect(harness.controller.synchronizeAccountScope(null)).toBe(true);

    expect(requestA?.controller.signal.aborted).toBe(true);
    expect(requestB?.controller.signal.aborted).toBe(true);
    for (const kind of [
      "stage",
      "token",
      "title",
      "final",
      "done",
      "error",
      "catch",
      "save_cleanup",
      "cancel",
      "run_replay",
      "ambiguity",
    ] as const) {
      expect(
        harness.controller.authorize(requestA!, kind, "conversation-a"),
      ).toBe(false);
      expect(
        harness.controller.authorize(requestB!, kind, "conversation-b"),
      ).toBe(false);
    }
    expect(harness.runtime.getState().byConversationId).toEqual({});
  });

  test("promotes an authorized ordinary final for existing and newly created visible transcripts", async () => {
    const viewport = await import(
      "../components/chat/useConversationActivityViewport"
    );
    expect(viewport.conversationActivityMutationRequiresCanonicalHydration("message_send")).toBe(false);
    expect(viewport.conversationActivityMutationRequiresCanonicalHydration("retry")).toBe(false);
    expect(viewport.conversationActivityMutationRequiresCanonicalHydration("recovery")).toBe(false);
    expect(viewport.conversationActivityMutationRequiresCanonicalHydration("durable_job_completion")).toBe(true);
    for (const conversationId of ["conversation-a", "conversation-created"]) {
      const harness = requestHarness();
      harness.showConversation(conversationId);
      const request = harness.controller.begin(conversationId, "chat_turn");
      expect(request).not.toBeNull();
      const readiness = viewport.createConversationActivityTranscriptReadiness();
      const readyTranscriptConversationIdRef = { current: null as string | null };
      const activeConversationIdRef = { current: conversationId as string | null };
      const currentViewRef = { current: "chat" };
      if (conversationId === "conversation-a") readiness.stageCanonical(conversationId);
      const previousGeneration = readiness.snapshot(conversationId).generation;

      const promoted = viewport.promoteVisibleConversationActivityTerminal({
        conversationId: request!.identity.conversationId,
        identityAuthorized: harness.controller.authorize(request!, "final"),
        finalPayload: { assistant_response: "Done" },
        requestKind: request!.kind,
        activeConversationIdRef,
        currentViewRef,
        readyTranscriptConversationIdRef,
        transcriptReadiness: readiness,
      });

      expect(promoted).toBe(true);
      expect(readyTranscriptConversationIdRef.current).toBe(conversationId);
      expect(readiness.snapshot(conversationId)).toEqual({
        generation: previousGeneration + 1,
        canonicalReady: true,
      });
    }
  });

  test("rejects a late ordinary final after its conversation loses visible ownership", async () => {
    const viewport = await import(
      "../components/chat/useConversationActivityViewport"
    );
    const harness = requestHarness();
    const requestA = harness.controller.begin("conversation-a", "chat_turn");
    expect(requestA).not.toBeNull();
    harness.showConversation("conversation-b");
    const readiness = viewport.createConversationActivityTranscriptReadiness();
    readiness.stageCanonical("conversation-b");
    const readyTranscriptConversationIdRef = { current: "conversation-b" as string | null };

    const promoted = viewport.promoteVisibleConversationActivityTerminal({
      conversationId: requestA!.identity.conversationId,
      identityAuthorized: harness.controller.authorize(requestA!, "final"),
      finalPayload: { assistant_response: "Done" },
      requestKind: requestA!.kind,
      activeConversationIdRef: { current: "conversation-b" },
      currentViewRef: { current: "chat" },
      readyTranscriptConversationIdRef,
      transcriptReadiness: readiness,
    });

    expect(promoted).toBe(false);
    expect(readyTranscriptConversationIdRef.current).toBe("conversation-b");
    expect(readiness.snapshot("conversation-a").canonicalReady).toBe(false);
    expect(readiness.snapshot("conversation-b").canonicalReady).toBe(true);
  });

  test("recognizes typed visible final artifacts without accepting whitespace", async () => {
    const { chatFinalPayloadOwnsVisibleTerminalArtifact } = await import(
      "../components/chat/useConversationActivityViewport"
    );
    const accepted: ChatFinalPayload[] = [
      { assistant_response: "Answer" },
      { assistant_response: "", stage_outcome: "completed", message_id: "message-1" },
      { confirmation: {} as NonNullable<ChatFinalPayload["confirmation"]> },
      { confirmation_cancelled: { confirmation_id: "confirmation-1" } },
      { recovery: { code: "retryable" }, message_id: "message-2" },
      { saved_strategy_id: "strategy-1" } as ChatFinalPayload,
    ];
    for (const payload of accepted) {
      expect(chatFinalPayloadOwnsVisibleTerminalArtifact(payload)).toBe(true);
    }
    for (const payload of [
      {},
      { assistant_response: "   " },
      { stage_outcome: "completed", message_id: "   " },
      { stage_outcome: "   ", message_id: "message-3" },
      { backtest_job: {} as NonNullable<ChatFinalPayload["backtest_job"]> },
    ] satisfies ChatFinalPayload[]) {
      expect(chatFinalPayloadOwnsVisibleTerminalArtifact(payload)).toBe(false);
    }
  });

  test("never promotes a backtest request final before canonical transcript hydration", async () => {
    const viewport = await import(
      "../components/chat/useConversationActivityViewport"
    );
    const readiness = viewport.createConversationActivityTranscriptReadiness();
    const readyTranscriptConversationIdRef = { current: null as string | null };

    expect(viewport.promoteVisibleConversationActivityTerminal({
      conversationId: "conversation-a",
      identityAuthorized: true,
      finalPayload: { backtest_job: {} as NonNullable<ChatFinalPayload["backtest_job"]> },
      requestKind: "backtest_job",
      activeConversationIdRef: { current: "conversation-a" },
      currentViewRef: { current: "chat" },
      readyTranscriptConversationIdRef,
      transcriptReadiness: readiness,
    })).toBe(false);
    expect(readyTranscriptConversationIdRef.current).toBeNull();
    expect(readiness.snapshot("conversation-a").canonicalReady).toBe(false);
  });

  test("settles each staged chat request through one visible artifact or canonical reconcile", async () => {
    const viewport = await import(
      "../components/chat/useConversationActivityViewport"
    );
    for (const terminal of ["persisted_recovery", "response_only_save"] as const) {
      const readiness = viewport.createConversationActivityTranscriptReadiness();
      readiness.stageCanonical("conversation-a");
      const reconciles: string[] = [];
      const session = viewport.createConversationActivityTerminalReadinessSession({
        getRequest: () => ({ conversationId: "conversation-a", kind: "chat_turn" }),
        activeConversationIdRef: { current: "conversation-a" },
        currentViewRef: { current: "chat" },
        readyTranscriptConversationIdRef: { current: "conversation-a" },
        transcriptReadiness: readiness,
        reconcileCanonical: (conversationId) => reconciles.push(conversationId),
      });

      expect(session.stage()).toBe(true);
      expect(readiness.snapshot("conversation-a").canonicalReady).toBe(false);
      expect(session.accept(
        terminal === "persisted_recovery"
          ? { message_id: "message-recovery", recovery: { code: "runtime_failure" } }
          : { assistant_response: "Saved" },
        true,
      )).toBe(true);
      expect(readiness.snapshot("conversation-a").canonicalReady).toBe(true);
      expect(session.finish(true)).toBe(false);
      expect(reconciles).toEqual([]);
    }

    const readiness = viewport.createConversationActivityTranscriptReadiness();
    readiness.stageCanonical("conversation-a");
    const reconciles: string[] = [];
    const session = viewport.createConversationActivityTerminalReadinessSession({
      getRequest: () => ({ conversationId: "conversation-a", kind: "chat_turn" }),
      activeConversationIdRef: { current: "conversation-a" },
      currentViewRef: { current: "chat" },
      readyTranscriptConversationIdRef: { current: "conversation-a" },
      transcriptReadiness: readiness,
      reconcileCanonical: (conversationId) => reconciles.push(conversationId),
    });
    expect(session.stage()).toBe(true);
    expect(session.accept({}, true)).toBe(false);
    expect(session.finish(true)).toBe(true);
    expect(session.finish(true)).toBe(false);
    expect(reconciles).toEqual(["conversation-a"]);
  });

  test("defers backtest readiness until the canonical job response is rendered", async () => {
    const viewport = await import(
      "../components/chat/useConversationActivityViewport"
    );
    const readiness = viewport.createConversationActivityTranscriptReadiness();
    readiness.stageCanonical("conversation-a");
    const readyRef = { current: "conversation-a" as string | null };
    const reconciles: string[] = [];
    const activeRef = { current: "conversation-a" as string | null };
    const viewRef = { current: "chat" };
    const session = viewport.createConversationActivityTerminalReadinessSession({
      getRequest: () => ({ conversationId: "conversation-a", kind: "backtest_job" }),
      activeConversationIdRef: activeRef,
      currentViewRef: viewRef,
      readyTranscriptConversationIdRef: readyRef,
      transcriptReadiness: readiness,
      reconcileCanonical: (conversationId) => reconciles.push(conversationId),
    });

    expect(session.stage()).toBe(true);
    expect(session.accept({ backtest_job: {} as NonNullable<ChatFinalPayload["backtest_job"]> }, true)).toBe(false);
    expect(session.finish(true)).toBe(false);
    expect(reconciles).toEqual([]);
    expect(viewport.promoteCanonicalConversationActivityTranscript({
      conversationId: "conversation-a",
      activeConversationIdRef: activeRef,
      currentViewRef: viewRef,
      readyTranscriptConversationIdRef: readyRef,
      transcriptReadiness: readiness,
    })).toBe(true);
    expect(readiness.snapshot("conversation-a").canonicalReady).toBe(true);
  });

  test("inactive terminal settlement cannot overwrite the visible transcript owner", async () => {
    const viewport = await import(
      "../components/chat/useConversationActivityViewport"
    );
    const readiness = viewport.createConversationActivityTranscriptReadiness();
    readiness.stageCanonical("conversation-b");
    const readyRef = { current: "conversation-b" as string | null };
    const reconciles: string[] = [];
    const session = viewport.createConversationActivityTerminalReadinessSession({
      getRequest: () => ({ conversationId: "conversation-a", kind: "chat_turn" }),
      activeConversationIdRef: { current: "conversation-b" },
      currentViewRef: { current: "chat" },
      readyTranscriptConversationIdRef: readyRef,
      transcriptReadiness: readiness,
      reconcileCanonical: (conversationId) => reconciles.push(conversationId),
    });

    expect(session.stage()).toBe(false);
    expect(session.accept({ assistant_response: "Late" }, true)).toBe(false);
    expect(session.finish(true)).toBe(false);
    expect(readyRef.current).toBe("conversation-b");
    expect(readiness.snapshot("conversation-b").canonicalReady).toBe(true);
    expect(reconciles).toEqual([]);
  });
});

describe("active conversation activity announcements", () => {
  test("wires only the active owned title and typed operation label selector", () => {
    expect(chatInterfaceSource).toContain(
      "title={activeTitleRecord ? headerConversationTitle : null}",
    );
    expect(chatInterfaceSource).toContain(
      "selectOperationLabel={conversationActivity.selectOperationLabel}",
    );
  });

  test("renders one atomic sr-only polite status region", () => {
    const html = renderToStaticMarkup(
      <ConversationActivityLiveRegion
        announcementKey="conversation-a:1:new-activity"
        message="New activity is ready in Tesla dip idea."
      />,
    );

    expect(html).toContain('data-testid="conversation-activity-announcement"');
    expect(html).toContain('class="sr-only"');
    expect(html).toContain('role="status"');
    expect(html).toContain('aria-live="polite"');
    expect(html).toContain('aria-atomic="true"');
    expect(html).toContain("New activity is ready in Tesla dip idea.");
  });

  test("waits for an unloaded conversation title before one correct-title consumption", () => {
    const harness = requestHarness();
    const request = harness.controller.begin("conversation-a", "chat_turn");
    expect(request).not.toBeNull();
    const transition = harness.runtime.getAnnouncement("conversation-a");
    expect(transition).not.toBeNull();

    const beforeTitle = consumeConversationActivityAnnouncement({
      activity: harness.runtime,
      conversationId: "conversation-a",
      transition: transition!,
      title: null,
    });
    expect(beforeTitle).toBeNull();
    expect(harness.runtime.getAnnouncement("conversation-a")?.key).toBe(
      transition?.key,
    );

    const resolved = consumeConversationActivityAnnouncement({
      activity: harness.runtime,
      conversationId: "conversation-a",
      transition: transition!,
      title: "Tesla dip idea",
    });

    expect(resolved).toMatchObject({
      conversationId: "conversation-a",
      key: transition?.key,
      presentation: "working",
    });
    expect(
      conversationActivityAnnouncementMessage(
        resolved,
        "Tesla dip idea",
        interpolateDefault,
      ),
    ).toBe("Cuadrao is working on Tesla dip idea.");
    expect(harness.runtime.getAnnouncement("conversation-a")).toBeNull();
  });

  test("retains the captured message through a Strict Effects setup cleanup setup replay", () => {
    const harness = requestHarness();
    harness.controller.begin("conversation-a", "chat_turn");
    const captured = harness.runtime.getAnnouncement("conversation-a");
    expect(captured).not.toBeNull();
    let logicalAcknowledgments = 0;
    const unsubscribe = harness.runtime.subscribe(() => {
      if (harness.runtime.getAnnouncement("conversation-a") === null) {
        logicalAcknowledgments += 1;
      }
    });
    let mountedMessage: ReturnType<
      typeof consumeConversationActivityAnnouncement
    > = null;
    const strictEffectSetup = () => {
      mountedMessage = consumeConversationActivityAnnouncement({
        activity: harness.runtime,
        conversationId: "conversation-a",
        transition: captured!,
        title: "Tesla dip idea",
      });
      return () => undefined;
    };

    strictEffectSetup()();
    strictEffectSetup();
    unsubscribe();
    const html = renderToStaticMarkup(
      <ConversationActivityLiveRegion
        announcementKey={mountedMessage?.key ?? "none"}
        message={conversationActivityAnnouncementMessage(
          mountedMessage,
          "Tesla dip idea",
          interpolateDefault,
        )}
      />,
    );

    expect(logicalAcknowledgments).toBe(1);
    expect(html).toContain("Cuadrao is working on Tesla dip idea.");
  });

  test("uses transition-specific copy and leaves optimistic manual unread to its toast", () => {
    expect(
      conversationActivityAnnouncementDescriptor("new_activity", "Tesla dip idea"),
    ).toEqual({
      key: "chat.activity.announce_new_activity",
      defaultValue: "{{title}} is ready.",
      title: "Tesla dip idea",
    });
    expect(
      conversationActivityAnnouncementDescriptor("needs_input", "Tesla dip idea"),
    ).toMatchObject({ key: "chat.activity.announce_needs_input" });
    expect(
      conversationActivityAnnouncementDescriptor("needs_attention", "Tesla dip idea"),
    ).toMatchObject({ key: "chat.activity.announce_needs_attention" });
    expect(
      conversationActivityAnnouncementDescriptor("manual_unread", "Tesla dip idea"),
    ).toBeNull();
  });

  test("rebuilds the consumed status sentence when the placeholder title is replaced", () => {
    const acknowledgments: string[] = [];
    const consumed = consumeConversationActivityAnnouncement({
      activity: {
        acknowledgeAnnouncement: (conversationId, key) => {
          acknowledgments.push(`${conversationId}|${key}`);
        },
      },
      conversationId: "conversation-a",
      transition: { key: "conversation-a:2:needs-input", presentation: "needs_input" },
      title: "New chat",
    });
    const statusRegion = (title: string | null) =>
      renderToStaticMarkup(
        <ConversationActivityLiveRegion
          announcementKey={consumed?.key ?? "none"}
          message={conversationActivityAnnouncementMessage(
            consumed,
            title,
            interpolateDefault,
          )}
        />,
      );

    expect(statusRegion("New chat")).toContain("New chat needs your input.");
    const retitled = statusRegion("Tesla dip idea");
    expect(retitled).toContain("Tesla dip idea needs your input.");
    expect(retitled).not.toContain("New chat");
    expect(acknowledgments).toEqual([
      "conversation-a|conversation-a:2:needs-input",
    ]);
  });
});
