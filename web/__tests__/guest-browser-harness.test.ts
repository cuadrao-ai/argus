import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  BrowserSafetyMonitor,
  CONFIRMATION_CONTINUITY_ASSERTION_MESSAGES,
  assertSafeEvidence,
  benignLoopbackNavigationAbort,
  binaryEvidenceDiffers,
  browserSafetyDetail,
  confirmationContinuityChecks,
  distinctConfirmationFacts,
  emptyEvidence,
  expectedMutationDeltasOnly,
  latestConfirmationFacts,
  latestResultFacts,
  productExecutionSafetyDetails,
  productFailedRequestsForCheck,
  rekeyGuestQaConfirmationMetadata,
  resultTruthStayedStable,
  strictUtcTimestampsEqual,
  type ConfirmationFacts,
  type PersistedMessageItem,
} from "../e2e/support/guest-qa";
import { guestQaEndpointConfig } from "../e2e/support/guest-qa-endpoints";

const requestedRange = { start: "2025-07-25", end: "2026-07-25" };
const effectiveRange = { start: "2025-07-25", end: "2026-07-24" };

function confirmationMessage(
  messageId: string,
  confirmationId: string,
  symbol: string,
  overrides: {
    benchmark?: string | null;
    requested?: Record<string, string>;
    effective?: Record<string, string>;
  } = {},
): PersistedMessageItem {
  const launchPayload: Record<string, unknown> = {
    requested_date_range: overrides.requested ?? requestedRange,
  };
  if (overrides.benchmark !== null) {
    launchPayload.benchmark_symbol = overrides.benchmark ?? "SPY";
  }
  return {
    id: messageId,
    conversation_id: "conversation-fixture",
    role: "assistant",
    content: "redacted fixture prose",
    metadata: {
      confirmation_payload: {
        strategy: {
          asset_universe: [symbol],
          date_range: overrides.effective ?? effectiveRange,
        },
        launch_payload: launchPayload,
        validation: {
          status: "ready_to_run",
          executable: true,
        },
      },
      confirmation_card: {
        confirmation_id: confirmationId,
        confirmation_state: "active",
        status: "ready_to_run",
        assumptions: ["Benchmark: SPY"],
        actions: [
          {
            type: "run_backtest",
            label: "Run backtest",
            payload: {
              confirmation_id: confirmationId,
              artifact_id: confirmationId,
              idempotency_key: confirmationId,
            },
          },
        ],
      },
      active_confirmation_reference: {
        artifact_id: confirmationId,
        metadata: { confirmation_id: confirmationId },
      },
      artifact_references: [
        {
          artifact_id: confirmationId,
          metadata: { confirmation_id: confirmationId },
        },
      ],
    },
  };
}

const initial = confirmationMessage(
  "message-initial",
  "confirmation-initial",
  "AAPL",
);
const refined = confirmationMessage(
  "message-refined",
  "confirmation-refined",
  "MSFT",
);

describe("guest QA isolated endpoint configuration", () => {
  test("preserves the existing local defaults", () => {
    expect(guestQaEndpointConfig({})).toEqual({
      appOrigin: "http://localhost:3000",
      appPort: 3000,
      apiOrigin: "http://localhost:8000",
      apiPort: 8000,
      apiBase: "http://localhost:8000/api/v1",
      databaseContainer: "supabase_db_argus-qa",
    });
  });

  test("accepts lane-unique loopback ports and database container", () => {
    expect(
      guestQaEndpointConfig({
        ARGUS_GUEST_QA_APP_PORT: "59900",
        ARGUS_GUEST_QA_API_PORT: "59901",
        ARGUS_GUEST_QA_DB_CONTAINER: "supabase_db_argus-guest-settlement-proof",
      }),
    ).toEqual({
      appOrigin: "http://localhost:59900",
      appPort: 59900,
      apiOrigin: "http://localhost:59901",
      apiPort: 59901,
      apiBase: "http://localhost:59901/api/v1",
      databaseContainer: "supabase_db_argus-guest-settlement-proof",
    });
  });

  test("fails closed for malformed ports and unsafe container names", () => {
    expect(() =>
      guestQaEndpointConfig({ ARGUS_GUEST_QA_APP_PORT: "0" }),
    ).toThrow("ARGUS_GUEST_QA_APP_PORT");
    expect(() =>
      guestQaEndpointConfig({ ARGUS_GUEST_QA_API_PORT: "8000/path" }),
    ).toThrow("ARGUS_GUEST_QA_API_PORT");
    expect(() =>
      guestQaEndpointConfig({
        ARGUS_GUEST_QA_APP_PORT: "4100",
        ARGUS_GUEST_QA_API_PORT: "4100",
      }),
    ).toThrow("must be different");
    expect(() =>
      guestQaEndpointConfig({ ARGUS_GUEST_QA_API_PORT: "65536" }),
    ).toThrow("ARGUS_GUEST_QA_API_PORT");
    expect(() =>
      guestQaEndpointConfig({
        ARGUS_GUEST_QA_DB_CONTAINER: "supabase_db_argus-qa; docker rm",
      }),
    ).toThrow("ARGUS_GUEST_QA_DB_CONTAINER");
  });
});

describe("guest QA strict UTC timestamp comparison", () => {
  test("treats API and Postgres UTC encodings of the same microsecond as equal", () => {
    expect(
      strictUtcTimestampsEqual(
        "2026-08-01T08:03:09.708198Z",
        "2026-08-01 08:03:09.708198+00",
      ),
    ).toBe(true);
  });

  test("rejects a real one-microsecond difference", () => {
    expect(
      strictUtcTimestampsEqual(
        "2026-08-01T08:03:09.708198Z",
        "2026-08-01 08:03:09.708199+00",
      ),
    ).toBe(false);
  });

  test("fails closed for invalid timestamps and non-UTC offsets", () => {
    expect(
      strictUtcTimestampsEqual(
        "not-a-timestamp",
        "2026-08-01T08:03:09.708198Z",
      ),
    ).toBe(false);
    expect(
      strictUtcTimestampsEqual(
        "2026-08-01T09:03:09.708198+01:00",
        "2026-08-01T08:03:09.708198Z",
      ),
    ).toBe(false);
  });
});

describe("guest Check 4 confirmation selection", () => {
  test("rejects a stale confirmation while waiting for a distinct artifact", () => {
    const initialFacts = latestConfirmationFacts([initial]);

    expect(distinctConfirmationFacts([initial], initialFacts)).toBeNull();
  });

  test("rejects a candidate when either identity is reused", () => {
    const initialFacts = latestConfirmationFacts([initial]);
    const reusedMessageId = confirmationMessage(
      "message-initial",
      "confirmation-refined",
      "MSFT",
    );
    const reusedConfirmationId = confirmationMessage(
      "message-refined",
      "confirmation-initial",
      "MSFT",
    );

    expect(
      distinctConfirmationFacts([initial, reusedMessageId], initialFacts),
    ).toBeNull();
    expect(
      distinctConfirmationFacts([initial, reusedConfirmationId], initialFacts),
    ).toBeNull();
  });

  test("selects the newest confirmation with distinct message and confirmation ids", () => {
    const initialFacts = latestConfirmationFacts([initial]);
    const newest = confirmationMessage(
      "message-newest",
      "confirmation-newest",
      "MSFT",
    );

    expect(
      distinctConfirmationFacts([initial, refined, newest], initialFacts),
    ).toMatchObject({
      messageId: "message-newest",
      confirmationId: "confirmation-newest",
      assetUniverse: ["MSFT"],
      benchmark: "SPY",
      requestedDateRange: requestedRange,
      effectiveDateRange: effectiveRange,
    });
  });

  test("requires a typed benchmark instead of searching card JSON", () => {
    const misleadingCard = confirmationMessage(
      "message-missing-benchmark",
      "confirmation-missing-benchmark",
      "MSFT",
      { benchmark: null },
    );

    expect(() => latestConfirmationFacts([misleadingCard])).toThrow(
      "typed benchmark",
    );
  });
});

describe("guest Check 11 deterministic confirmation setup", () => {
  test("creates a distinct run identity without changing typed strategy facts", () => {
    const metadata = structuredClone(initial.metadata ?? {});

    const rekeyed = rekeyGuestQaConfirmationMetadata(
      metadata,
      "confirmation-second",
    );
    const originalFacts = latestConfirmationFacts([initial]);
    const rekeyedFacts = latestConfirmationFacts([
      {
        ...initial,
        id: "message-second",
        metadata: rekeyed,
      },
    ]);
    const runAction = (
      (rekeyed.confirmation_card as Record<string, unknown>).actions as Array<
        Record<string, unknown>
      >
    ).find((action) => action.type === "run_backtest");

    expect(rekeyedFacts.confirmationId).toBe("confirmation-second");
    expect(rekeyedFacts.assetUniverse).toEqual(originalFacts.assetUniverse);
    expect(rekeyedFacts.benchmark).toBe(originalFacts.benchmark);
    expect(rekeyedFacts.requestedDateRange).toEqual(
      originalFacts.requestedDateRange,
    );
    expect(rekeyedFacts.effectiveDateRange).toEqual(
      originalFacts.effectiveDateRange,
    );
    expect(runAction?.payload).toEqual({
      confirmation_id: "confirmation-second",
      artifact_id: "confirmation-second",
      idempotency_key: "confirmation-second",
    });
    expect(
      (rekeyed.confirmation_payload as Record<string, unknown>).confirmation_id,
    ).toBeUndefined();
    expect(
      (rekeyed.confirmation_payload as Record<string, unknown>).artifact_id,
    ).toBeUndefined();
    expect(
      (rekeyed.active_confirmation_reference as Record<string, unknown>)
        .artifact_id,
    ).toBe("confirmation-second");
    expect(
      (rekeyed.artifact_references as Array<Record<string, unknown>>)[0]
        .artifact_id,
    ).toBe("confirmation-second");
    expect(
      (initial.metadata?.confirmation_card as Record<string, unknown>)
        .confirmation_id,
    ).toBe("confirmation-initial");
  });

  test("fails closed when the source has no typed run action", () => {
    const metadata = structuredClone(initial.metadata ?? {});
    (metadata.confirmation_card as Record<string, unknown>).actions = [];
    expect(() =>
      rekeyGuestQaConfirmationMetadata(metadata, "confirmation-second"),
    ).toThrow("typed run action");
  });

  test("fails closed when the typed run action identity disagrees", () => {
    const metadata = structuredClone(initial.metadata ?? {});
    const card = metadata.confirmation_card as Record<string, unknown>;
    const actions = card.actions as Array<Record<string, unknown>>;
    const runAction = actions.find((action) => action.type === "run_backtest");
    if (!runAction) throw new Error("fixture is missing its run action");
    (runAction.payload as Record<string, unknown>).confirmation_id =
      "confirmation-other";

    expect(() =>
      rekeyGuestQaConfirmationMetadata(metadata, "confirmation-second"),
    ).toThrow("identity mismatch");
  });

  test("accepts a typed run action without its optional artifact alias", () => {
    const metadata = structuredClone(initial.metadata ?? {});
    const card = metadata.confirmation_card as Record<string, unknown>;
    const actions = card.actions as Array<Record<string, unknown>>;
    const runAction = actions.find((action) => action.type === "run_backtest");
    if (!runAction) throw new Error("fixture is missing its run action");
    delete (runAction.payload as Record<string, unknown>).artifact_id;

    expect(
      rekeyGuestQaConfirmationMetadata(metadata, "confirmation-second"),
    ).toBeDefined();
  });

  test("fails closed when an optional payload identity alias disagrees", () => {
    const metadata = structuredClone(initial.metadata ?? {});
    (metadata.confirmation_payload as Record<string, unknown>).confirmation_id =
      "confirmation-other";

    expect(() =>
      rekeyGuestQaConfirmationMetadata(metadata, "confirmation-second"),
    ).toThrow("identity mismatch");
  });
});

describe("guest Check 4 continuity assertions", () => {
  const exactUpdate = "Use MSFT instead of AAPL.";
  const updateMessage: PersistedMessageItem = {
    id: "message-user-update",
    conversation_id: "conversation-fixture",
    role: "user",
    content: exactUpdate,
  };
  const initialFacts = latestConfirmationFacts([initial]);
  const refinedFacts = latestConfirmationFacts([refined]);
  const expectedPassing = {
    updateMessagePersisted: true,
    assetUniverseExactlyMsft: true,
    benchmarkExactlySpy: true,
    requestedDateRangeUnchanged: true,
    effectiveDateRangeUnchanged: true,
  };

  test.each([
    {
      name: "exact update-message persistence",
      key: "updateMessagePersisted" as const,
      messages: [],
      facts: refinedFacts,
    },
    {
      name: "asset universe",
      key: "assetUniverseExactlyMsft" as const,
      messages: [updateMessage],
      facts: { ...refinedFacts, assetUniverse: ["AAPL"] },
    },
    {
      name: "benchmark",
      key: "benchmarkExactlySpy" as const,
      messages: [updateMessage],
      facts: { ...refinedFacts, benchmark: "QQQ" },
    },
    {
      name: "requested date range",
      key: "requestedDateRangeUnchanged" as const,
      messages: [updateMessage],
      facts: {
        ...refinedFacts,
        requestedDateRange: { ...requestedRange, start: "2025-08-01" },
      },
    },
    {
      name: "effective date range",
      key: "effectiveDateRangeUnchanged" as const,
      messages: [updateMessage],
      facts: {
        ...refinedFacts,
        effectiveDateRange: { ...effectiveRange, end: "2026-07-23" },
      },
    },
  ])(
    "$name fails independently with a useful assertion",
    ({ key, messages, facts }) => {
      const checks = confirmationContinuityChecks(
        initialFacts,
        facts as ConfirmationFacts,
        messages,
        exactUpdate,
      );

      expect(checks).toEqual({ ...expectedPassing, [key]: false });
      expect(
        CONFIRMATION_CONTINUITY_ASSERTION_MESSAGES[key].length,
      ).toBeGreaterThan(20);
    },
  );
});

describe("browser safety evidence", () => {
  test("ignores only the superseded loopback chat navigation fetch", () => {
    expect(
      benignLoopbackNavigationAbort({
        rawUrl: "http://localhost:3000/chat",
        method: "GET",
        rawError: "net::ERR_ABORTED",
        isNavigationRequest: false,
      }),
    ).toBe(true);
    expect(
      benignLoopbackNavigationAbort({
        rawUrl: "http://localhost:8000/api/v1/chat/stream",
        method: "POST",
        rawError: "net::ERR_ABORTED",
        isNavigationRequest: false,
      }),
    ).toBe(false);
    expect(
      benignLoopbackNavigationAbort({
        rawUrl: "https://argus.example/chat",
        method: "GET",
        rawError: "net::ERR_ABORTED",
        isNavigationRequest: true,
      }),
    ).toBe(false);
  });

  test("allows only the expected mutation delta at a conversion gate", () => {
    const before = {
      "POST /api/v1/auth/guest/handoffs": 2,
      "POST /api/v1/chat/stream": 4,
    };

    expect(
      expectedMutationDeltasOnly(
        before,
        {
          ...before,
          "POST /api/v1/auth/guest/handoffs": 3,
        },
        {
          "POST /api/v1/auth/guest/handoffs": 1,
        },
      ),
    ).toBe(true);
    expect(
      expectedMutationDeltasOnly(
        before,
        {
          ...before,
          "POST /api/v1/auth/guest/handoffs": 3,
          "POST /api/v1/chat/stream": 5,
        },
        {
          "POST /api/v1/auth/guest/handoffs": 1,
        },
      ),
    ).toBe(false);
  });

  test("records only sanitized endpoint, category, check, and phase detail", () => {
    const detail = browserSafetyDetail({
      event: "failed_request",
      rawUrl:
        "http://127.0.0.1:8000/api/v1/conversations/4f8c3dea-c926-4e33-9d50-959bd43d4868/messages?email=founder@example.com&token=secret",
      method: "POST",
      rawError: "net::ERR_CONNECTION_REFUSED bearer secret founder@example.com",
      status: null,
      context: { check: 4, phase: "teardown" },
    });
    const serialized = JSON.stringify(detail);

    expect(detail).toEqual({
      event: "failed_request",
      component: "network",
      endpoint: "POST /api/v1/conversations/:id/messages",
      status: null,
      category: "connection_refused",
      check: 4,
      phase: "teardown",
    });
    expect(serialized).not.toContain("founder@example.com");
    expect(serialized).not.toContain("secret");
    expect(serialized).not.toContain("token");
    expect(serialized).not.toContain("bearer");
    expect(serialized).not.toContain("4f8c3dea");

    expect(
      browserSafetyDetail({
        event: "console_error",
        rawError: "Hydration failed with bearer secret founder@example.com",
        context: { check: 2, phase: "product" },
      }),
    ).toEqual({
      event: "console_error",
      component: "browser_console",
      endpoint: null,
      status: null,
      category: "hydration_error",
      check: 2,
      phase: "product",
    });
  });

  test("the attached monitor records the live product-to-teardown phase change", () => {
    type StubHandler = (payload: unknown) => void;
    const handlers = new Map<string, StubHandler[]>();
    const pageStub = {
      on(event: string, handler: StubHandler) {
        handlers.set(event, [...(handlers.get(event) ?? []), handler]);
        return pageStub;
      },
      emit(event: string, payload: unknown) {
        for (const handler of handlers.get(event) ?? []) handler(payload);
      },
    };
    let phase = "product" as "product" | "teardown";
    const monitor = new BrowserSafetyMonitor(() => ({ check: 4, phase }));
    monitor.attach(
      pageStub as unknown as Parameters<BrowserSafetyMonitor["attach"]>[0],
    );

    pageStub.emit("console", {
      type: () => "error",
      text: () => "Hydration failed with founder@example.com",
    });
    pageStub.emit("response", {
      status: () => 429,
      url: () =>
        "http://127.0.0.1:8000/api/v1/backtests/4f8c3dea-c926-4e33-9d50-959bd43d4868?token=secret",
      request: () => ({ method: () => "POST" }),
    });
    phase = "teardown";
    pageStub.emit("requestfailed", {
      url: () =>
        "http://127.0.0.1:8000/api/v1/conversations/4f8c3dea-c926-4e33-9d50-959bd43d4868/messages?token=secret",
      method: () => "POST",
      failure: () => ({ errorText: "net::ERR_ABORTED bearer secret" }),
      isNavigationRequest: () => false,
    });

    expect(monitor.detailSnapshot()).toEqual([
      {
        event: "console_error",
        component: "browser_console",
        endpoint: null,
        status: null,
        category: "hydration_error",
        check: 4,
        phase: "product",
      },
      {
        event: "failed_request",
        component: "network",
        endpoint: "POST /api/v1/backtests/:id",
        status: 429,
        category: "http_client_error",
        check: 4,
        phase: "product",
      },
      {
        event: "failed_request",
        component: "network",
        endpoint: "POST /api/v1/conversations/:id/messages",
        status: null,
        category: "aborted",
        check: 4,
        phase: "teardown",
      },
    ]);
    expect(JSON.stringify(monitor.detailSnapshot())).not.toMatch(
      /founder|secret|bearer|token|4f8c3dea/i,
    );
  });

  test("selects a product-phase failed request without accepting teardown noise", () => {
    const expected = browserSafetyDetail({
      event: "failed_request",
      rawUrl: "http://127.0.0.1:8000/api/v1/chat/stream",
      method: "POST",
      rawError: "net::ERR_CONNECTION_RESET",
      context: { check: 18, phase: "product" },
    });
    const unrelated = browserSafetyDetail({
      event: "failed_request",
      rawUrl: "http://127.0.0.1:8000/api/v1/me",
      method: "GET",
      rawError: "net::ERR_ABORTED",
      context: { check: 18, phase: "teardown" },
    });

    expect(productFailedRequestsForCheck([expected, unrelated], 18)).toEqual([
      {
        event: "failed_request",
        component: "network",
        endpoint: "POST /api/v1/chat/stream",
        status: null,
        category: "connection_reset",
        check: 18,
        phase: "product",
      },
    ]);
  });

  test("preserves controlled fault-injection errors without treating them as product failures", () => {
    const product = browserSafetyDetail({
      event: "page_error",
      rawError: "Hydration failed",
      context: { check: 18, phase: "product" },
    });
    const controlled = browserSafetyDetail({
      event: "failed_request",
      rawUrl: "http://127.0.0.1:8000/api/v1/conversations",
      method: "GET",
      rawError: "net::ERR_CONNECTION_REFUSED",
      context: { check: 18, phase: "fault_injection" },
    });
    const unrelatedPageError = browserSafetyDetail({
      event: "page_error",
      rawError: "Hydration failed",
      context: { check: 18, phase: "fault_injection" },
    });
    const unrelatedExternalFailure = browserSafetyDetail({
      event: "failed_request",
      rawUrl: "https://example.invalid/api/v1/conversations",
      method: "GET",
      rawError: "net::ERR_CONNECTION_REFUSED",
      context: { check: 18, phase: "fault_injection" },
    });
    const correlatedConsole = browserSafetyDetail({
      event: "console_error",
      rawError: "net::ERR_CONNECTION_REFUSED",
      correlatedFault: true,
      context: { check: 18, phase: "fault_injection" },
    });
    const uncorrelatedConsole = browserSafetyDetail({
      event: "console_error",
      rawError: "net::ERR_CONNECTION_REFUSED",
      context: { check: 18, phase: "fault_injection" },
    });
    const teardown = browserSafetyDetail({
      event: "console_error",
      rawError: "net::ERR_CONNECTION_REFUSED",
      context: { check: 18, phase: "teardown" },
    });
    const details = [
      product,
      controlled,
      unrelatedPageError,
      unrelatedExternalFailure,
      correlatedConsole,
      uncorrelatedConsole,
      teardown,
    ];

    expect(productExecutionSafetyDetails(details)).toEqual([
      product,
      unrelatedPageError,
      unrelatedExternalFailure,
      uncorrelatedConsole,
    ]);
    expect(details).toContain(controlled);
    expect(controlled).toEqual({
      event: "failed_request",
      component: "network",
      endpoint: "GET /api/v1/conversations",
      status: null,
      category: "connection_refused",
      check: 18,
      phase: "fault_injection",
    });
    expect(correlatedConsole.phase).toBe("fault_injection");
    expect(unrelatedPageError.phase).toBe("product");
    expect(unrelatedExternalFailure.phase).toBe("product");
    expect(uncorrelatedConsole.phase).toBe("product");
  });

  test("detects credential-shaped data on a non-loopback request without retaining it", () => {
    type StubHandler = (payload: unknown) => void;
    const handlers = new Map<string, StubHandler[]>();
    const pageStub = {
      on(event: string, handler: StubHandler) {
        handlers.set(event, [...(handlers.get(event) ?? []), handler]);
        return pageStub;
      },
      emit(event: string, payload: unknown) {
        for (const handler of handlers.get(event) ?? []) handler(payload);
      },
    };
    const monitor = new BrowserSafetyMonitor();
    monitor.attach(
      pageStub as unknown as Parameters<BrowserSafetyMonitor["attach"]>[0],
    );

    pageStub.emit("request", {
      url: () => "https://example.invalid/collect?token=opaque-secret",
      method: () => "POST",
      headers: () => ({ authorization: "Bearer opaque-secret" }),
      postData: () => '{"cookie":"opaque-secret"}',
    });

    expect(monitor.hostedWrites).toBe(1);
    expect(monitor.credentialExposure).toBe(1);
    expect(JSON.stringify(monitor.detailSnapshot())).not.toContain(
      "opaque-secret",
    );
  });

  test("accepts only hashed identifiers and classified endpoint evidence", () => {
    const previousCandidate = process.env.ARGUS_CANDIDATE_SHA;
    process.env.ARGUS_CANDIDATE_SHA = "a".repeat(40);
    try {
      const safe = emptyEvidence();
      safe.owner_labels = ["b".repeat(20)];
      safe.normalized_mutation_counts = {
        "POST /api/v1/auth/guest/signup": 1,
      };
      assertSafeEvidence(safe);

      const unsafeCategory = {
        ...safe,
        browser_safety_details: [
          {
            event: "console_error" as const,
            component: "browser_console" as const,
            endpoint: null,
            status: null,
            category: "raw transcript prose",
            check: 2 as const,
            phase: "product" as const,
          },
        ],
      };
      expect(() => assertSafeEvidence(unsafeCategory)).toThrow(
        "unsafe browser safety detail",
      );

      const unsafeEndpoint = {
        ...safe,
        normalized_mutation_counts: {
          "POST /api/v1/feedback?token=opaque": 1,
        },
      };
      expect(() => assertSafeEvidence(unsafeEndpoint)).toThrow(
        "unsafe mutation endpoint",
      );
    } finally {
      if (previousCandidate === undefined) {
        delete process.env.ARGUS_CANDIDATE_SHA;
      } else {
        process.env.ARGUS_CANDIDATE_SHA = previousCandidate;
      }
    }
  });
});

describe("guest result and chart evidence", () => {
  test("requires typed result identities and selects the latest durable result", () => {
    const first: PersistedMessageItem = {
      id: "message-result-1",
      conversation_id: "conversation-fixture",
      role: "assistant",
      content: "redacted fixture prose",
      metadata: {
        result_run_id: "run-1",
        result_card: { evidenceArtifactId: "evidence-1" },
      },
    };
    const second: PersistedMessageItem = {
      ...first,
      id: "message-result-2",
      metadata: {
        result_run_id: "run-2",
        result_card: { evidenceArtifactId: "evidence-2" },
      },
    };

    expect(latestResultFacts([first, second])).toEqual({
      messageId: "message-result-2",
      runId: "run-2",
      evidenceId: "evidence-2",
    });
    expect(() =>
      latestResultFacts([
        {
          ...second,
          metadata: {
            result_card: {
              description: "run-2 evidence-2",
            },
          },
        },
      ]),
    ).toThrow("typed result");
  });

  test("distinguishes a changed chart viewport and exact immutable result truth", () => {
    expect(
      binaryEvidenceDiffers(
        new Uint8Array([1, 2, 3]),
        new Uint8Array([1, 2, 3]),
      ),
    ).toBe(false);
    expect(
      binaryEvidenceDiffers(
        new Uint8Array([1, 2, 3]),
        new Uint8Array([1, 4, 3]),
      ),
    ).toBe(true);
    expect(
      resultTruthStayedStable(
        { rows: 1, fingerprint: "truth-a" },
        { rows: 1, fingerprint: "truth-a" },
      ),
    ).toBe(true);
    expect(
      resultTruthStayedStable(
        { rows: 1, fingerprint: "truth-a" },
        { rows: 1, fingerprint: "truth-b" },
      ),
    ).toBe(false);
  });
});
