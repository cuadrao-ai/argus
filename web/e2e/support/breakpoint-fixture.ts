import type { Page, Route } from "@playwright/test";

/**
 * Deterministic whole-app fixture for breakpoint work.
 *
 * Extends the mobile-shell stub to the surfaces a breakpoint pass needs that a
 * shell pass does not: allowance states, the guest conversion prompt, archived
 * and deleted rows, and a display name long enough to truncate. Every value is
 * fixed, so a capture differing between runs is a real change rather than a
 * different sentence coming back from a model.
 */

export type Account = "registered" | "guest";
export type Language = "en" | "es-419";
export type Theme = "dark" | "light";
/** `exhausted` drives the guest conversion prompt; `error` drives the retry state. */
export type UsageState = "healthy" | "nearly_out" | "exhausted" | "error";

const USER_ID = "breakpoint-user";
const CREATED_AT = "2026-08-01T12:00:00Z";
const RUN_ID = "run-alpha";
const DAY_PERIOD_END = "2026-08-01T23:59:59Z";
/* Distinct from the day end so the hourly line is not a copy of the daily one. */
const HOUR_PERIOD_END = "2026-08-01T13:00:00Z";

/* The longest title is deliberate: a name that cannot fit in a 390px rail is
   the only way a truncation bug shows up in a capture. */
export const CONVERSATIONS = [
  { id: "conversation-alpha", title: "Apple vs SPY, twelve months" },
  { id: "conversation-beta", title: "Weekly Nvidia buys" },
  {
    id: "conversation-gamma",
    title:
      "Monthly index contributions compared against a lump sum over a ten year window",
  },
];

const SPANISH_TITLES: Record<string, string> = {
  "conversation-alpha": "Apple frente a SPY, doce meses",
  "conversation-beta": "Compras semanales de Nvidia",
  "conversation-gamma":
    "Aportes mensuales al índice comparados con una suma única en una ventana de diez años",
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

const IDLE_ACTIVITY = {
  operation: { status: "idle" as const, kind: null, updated_at: CREATED_AT },
  attention: { status: "none" as const, cursor: null },
};

function conversation(id: string, title: string, archived = false) {
  return {
    type: "chat" as const,
    id,
    conversation_id: id,
    title,
    title_source: "system_generated",
    subtitle: "",
    pinned: false,
    archived,
    created_at: CREATED_AT,
    updated_at: CREATED_AT,
    activity: IDLE_ACTIVITY,
  };
}

function window_(limit: number, used: number, periodEnd: string) {
  return {
    limit,
    used,
    remaining: Math.max(0, limit - used),
    period_end: periodEnd,
  };
}

function allowances(state: UsageState, isGuest: boolean) {
  const spent = state === "exhausted" ? 1 : state === "nearly_out" ? 0.9 : 0.2;
  const day = (limit: number) =>
    window_(limit, Math.round(limit * spent), DAY_PERIOD_END);
  const hour = (limit: number) =>
    window_(limit, Math.round(limit * spent), HOUR_PERIOD_END);
  const available = state !== "exhausted";
  return {
    compute: {
      hour: null,
      day: null,
      guest_session: null,
      available_now: true,
      limiting_window: null,
    },
    grounding: {
      hour: isGuest ? null : hour(20),
      day: day(60),
      guest_session: null,
      available_now: available,
      limiting_window: isGuest ? "day" : "hour",
    },
    execution: {
      hour: isGuest ? null : hour(5),
      day: day(10),
      guest_session: null,
      available_now: available,
      limiting_window: "day",
    },
  };
}

function confirmationCard(isSpanish: boolean) {
  return {
    version: "argus_confirmation/v1",
    status: "awaiting_confirmation",
    title: isSpanish ? "Listo para probar" : "Ready to test",
    strategy_label: isSpanish ? "Comprar y mantener" : "Buy and hold",
    rows: [
      { key: "assets", label: isSpanish ? "Activos" : "Assets", value: "AAPL" },
      {
        key: "period",
        label: isSpanish ? "Período" : "Period",
        value: isSpanish
          ? "Últimos 12 meses · 2025-08-01 a 2026-08-01"
          : "Last 12 months · 2025-08-01 to 2026-08-01",
      },
      {
        key: "capital",
        label: isSpanish ? "Capital" : "Capital",
        value: "$10,000",
      },
      {
        key: "benchmark",
        label: isSpanish ? "Referencia" : "Benchmark",
        value: "SPY",
      },
    ],
    actions: [
      {
        id: "run",
        type: "run_backtest",
        label: isSpanish ? "Ejecutar prueba" : "Run test",
      },
      {
        id: "capital",
        type: "adjust_capital",
        label: isSpanish ? "Capital" : "Capital",
      },
      {
        id: "period",
        type: "adjust_period",
        label: isSpanish ? "Fechas" : "Dates",
      },
      {
        id: "benchmark",
        type: "adjust_benchmark",
        label: isSpanish ? "Referencia" : "Benchmark",
      },
      {
        id: "cancel",
        type: "cancel_confirmation",
        label: isSpanish ? "Cancelar" : "Cancel",
      },
    ],
  };
}

/**
 * Shape matters here. `isHydratableResultCard` requires title, status_label,
 * rows, assumptions, actions, and a full date_range, and the message carrying
 * it must also declare `result_run_id`. Miss any of those and the transcript
 * silently renders the plain assistant text instead of a card.
 */
function resultCard(isSpanish: boolean) {
  return {
    version: "argus_result/v1",
    run_id: RUN_ID,
    title: isSpanish ? "Apple, comprar y mantener" : "Apple buy and hold",
    strategy_label: isSpanish ? "Comprar y mantener" : "Buy and hold",
    status_label: isSpanish ? "Simulación completa" : "Simulation Complete",
    symbols: ["AAPL"],
    benchmark_symbol: "SPY",
    status: "completed",
    date_range: {
      start: "2025-08-01",
      end: "2026-08-01",
      display: isSpanish ? "1 ago 2025 a 1 ago 2026" : "Aug 1 2025 to Aug 1 2026",
    },
    /* Five metric rows with signed percentages is the shape most likely to
       overflow a narrow result table, so the fixture always carries it. */
    rows: [
      {
        key: "total_return",
        label: isSpanish ? "Retorno total" : "Total return",
        value: "+18.4%",
      },
      {
        key: "benchmark_return",
        label: isSpanish ? "Retorno de referencia" : "Benchmark return",
        value: "+11.2%",
      },
      {
        key: "max_drawdown",
        label: isSpanish ? "Caída máxima" : "Max drawdown",
        value: "-9.1%",
      },
      {
        key: "volatility",
        label: isSpanish ? "Volatilidad anualizada" : "Annualized volatility",
        value: "21.7%",
      },
      {
        key: "final_value",
        label: isSpanish ? "Valor final" : "Final value",
        value: "$11,840.00",
      },
    ],
    assumptions: [],
    actions: [],
    evidence_artifact_id: "evidence-alpha",
  };
}

function messages(language: Language) {
  const isSpanish = language === "es-419";
  return [
    {
      id: "message-user-1",
      role: "user",
      content: isSpanish
        ? "Compara Apple con SPY durante los últimos 12 meses."
        : "Compare Apple with SPY over the last 12 months.",
      created_at: CREATED_AT,
      metadata: {},
    },
    {
      id: "message-assistant-1",
      role: "assistant",
      content: isSpanish
        ? "Apple superó a SPY en el período probado."
        : "Apple outperformed SPY across the tested window.",
      created_at: CREATED_AT,
      metadata: {
        result_card: resultCard(isSpanish),
        result_run_id: RUN_ID,
      },
    },
    {
      id: "message-user-2",
      role: "user",
      content: isSpanish
        ? "Ahora pruébalo con Nvidia."
        : "Now try the same thing on Nvidia.",
      created_at: CREATED_AT,
      metadata: {},
    },
    {
      id: "message-assistant-2",
      role: "assistant",
      content: isSpanish
        ? "Confirma la configuración antes de ejecutar."
        : "Confirm the setup before running.",
      created_at: CREATED_AT,
      metadata: { confirmation_card: confirmationCard(isSpanish) },
    },
  ];
}

function searchRow(id: string, title: string, language: Language) {
  const isSpanish = language === "es-419";
  return {
    type: "conversation" as const,
    id,
    conversation_id: id,
    title,
    archived: false,
    matched_text: "Apple, SPY, twelve month window.",
    updated_at: CREATED_AT,
    match: {
      layer: "conversation" as const,
      fragment: "Apple, SPY, twelve month window.",
      count: 1,
    },
    dossier:
      id === "conversation-alpha"
        ? {
            run_id: "run-alpha",
            run_label: isSpanish
              ? "Apple, comprar y mantener"
              : "Apple buy and hold",
            completed_at: CREATED_AT,
            result_message_id: "message-assistant-1",
            tested: {
              symbols: ["AAPL"],
              strategy_family: "buy_and_hold",
              cadence: null,
              timeframe: "1d",
              start_date: "2025-08-01",
              end_date: "2026-08-01",
            },
            outcome: {
              run_label: isSpanish
                ? "Apple, comprar y mantener"
                : "Apple buy and hold",
              completed_at: CREATED_AT,
              benchmark_symbol: "SPY",
              quick_take: isSpanish
                ? "Apple superó a SPY en el período probado."
                : "Apple outperformed SPY across the tested window.",
              /* `name` is a metric CODE, not a display string: the dossier
                 looks it up in `command_palette.metric_labels.*`. */
              metrics: [
                { name: "total_return_pct", value: "+18.4%" },
                { name: "benchmark_return_pct", value: "+11.2%" },
                { name: "max_drawdown_pct", value: "-9.1%" },
                { name: "volatility_pct", value: "21.7%" },
              ],
            },
            decision: null,
            actions: [
              {
                type: "retest_run" as const,
                source_run_id: "run-alpha",
                run_label: isSpanish
                  ? "Apple, comprar y mantener"
                  : "Apple buy and hold",
                window_policy: "preserve_start_ending_latest_available" as const,
                contract_version: "argus_retest_run/v2" as const,
                state: "new_data_available" as const,
                reason_code: null,
                repair: null,
              },
            ],
          }
        : null,
    total_runs: 1,
    decided_runs: 0,
    decision_states: [],
  };
}

export async function installBreakpointFixture(
  page: Page,
  options: {
    account?: Account;
    language?: Language;
    theme?: Theme;
    usage?: UsageState;
    emptyChat?: boolean;
  } = {},
): Promise<void> {
  const account = options.account ?? "registered";
  const language = options.language ?? "en";
  const theme = options.theme ?? "dark";
  const usage = options.usage ?? "healthy";
  const emptyChat = options.emptyChat ?? false;
  const isGuest = account === "guest";
  const isSpanish = language === "es-419";

  await page.addInitScript(
    ([lang, storedTheme]) => {
      if (window.top !== window.self) return;
      window.localStorage.setItem("i18nextLng", lang);
      window.localStorage.setItem("argus:sidebar_mode", "expanded");
      window.localStorage.setItem("argus-theme", storedTheme);
    },
    [language, theme],
  );

  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path.endsWith("/api/v1/me/usage")) {
      if (usage === "error") {
        return json(
          route,
          {
            code: "usage_read_failed",
            detail: "Current allowance information is unavailable.",
          },
          500,
        );
      }
      return json(route, { allowances: allowances(usage, isGuest) });
    }

    if (path.endsWith("/api/v1/me")) {
      return json(route, {
        user: {
          id: USER_ID,
          email: isGuest ? null : "alexandra.breakpoint@example.com",
          username: isGuest ? null : "alexandra-breakpoint",
          /* Long enough to truncate in a 390px profile row on purpose. */
          display_name: isGuest ? null : "Alexandra Featherstonehaugh",
          language,
          locale: isSpanish ? "es-419" : "en-US",
          onboarding: {
            completed: true,
            stage: "completed",
            language_confirmed: true,
            primary_goal: null,
          },
        },
        account_kind: isGuest ? "guest" : "registered",
        guest: isGuest
          ? {
              expires_at: "2026-08-14T12:00:00Z",
              workspace_id: "guest-workspace",
            }
          : null,
        capabilities: {
          can_create_additional_conversation: !isGuest,
          can_manage_conversation: !isGuest,
          can_save_decision: !isGuest,
          can_manage_account: !isGuest,
          can_use_omnisearch: true,
          can_search_current_workspace: true,
          can_use_grounded_discovery: true,
          can_submit_feedback: true,
        },
        public_account_access_enabled: false,
      });
    }

    if (/\/api\/v1\/conversations\/[^/]+\/activity$/.test(path)) {
      return json(route, IDLE_ACTIVITY);
    }

    if (/\/api\/v1\/conversations\/[^/]+\/messages$/.test(path)) {
      return json(route, {
        items: emptyChat ? [] : messages(language),
        next_cursor: null,
      });
    }

    if (path.endsWith("/api/v1/conversations")) {
      const items = isGuest ? [CONVERSATIONS[0]] : CONVERSATIONS;
      return json(route, {
        items: items.map((entry) =>
          conversation(
            entry.id,
            isSpanish ? SPANISH_TITLES[entry.id] : entry.title,
          ),
        ),
        next_cursor: null,
      });
    }

    if (/\/api\/v1\/conversations\/[^/]+$/.test(path)) {
      const id = path.split("/").pop()!;
      const entry = CONVERSATIONS.find((c) => c.id === id) ?? CONVERSATIONS[0];
      return json(
        route,
        conversation(entry.id, isSpanish ? SPANISH_TITLES[entry.id] : entry.title),
      );
    }

    if (path.endsWith("/api/v1/history")) {
      const items = (isGuest ? [CONVERSATIONS[0]] : CONVERSATIONS).map((entry) =>
        conversation(entry.id, isSpanish ? SPANISH_TITLES[entry.id] : entry.title),
      );
      return json(route, { items, next_cursor: null });
    }

    if (path.endsWith("/api/v1/search")) {
      const items = (isGuest ? [CONVERSATIONS[0]] : CONVERSATIONS).map((entry) =>
        searchRow(
          entry.id,
          isSpanish ? SPANISH_TITLES[entry.id] : entry.title,
          language,
        ),
      );
      return json(route, { items, next_cursor: null, ledger_groups: [] });
    }

    if (path.endsWith("/api/v1/memory/availability")) {
      return json(route, { available: false, reason: "disabled" });
    }

    if (path.endsWith("/starter-prompts")) {
      return json(route, { prompts: [] });
    }

    return json(route, {});
  });
}

/**
 * Chrome that is either dev-only or non-deterministic, and would otherwise make
 * every capture differ from the last one by a few bytes.
 */
export const FREEZE_CSS = `
  nextjs-portal { display: none !important; }
  /* DevModeBadge renders only under NEXT_PUBLIC_MOCK_AUTH, which is exactly how
     these captures run, so without this it floats over the transcript in every
     capture and sits inside every committed baseline while never shipping to a
     user. It carries no attribute of its own, so it is matched through the
     button it owns. */
  div:has(> button[aria-label="Show dev tools"]),
  div:has(> button[aria-label="Hide dev tools"]) { display: none !important; }
  *, *::before, *::after {
    animation: none !important;
    transition: none !important;
    animation-duration: 0s !important;
    transition-duration: 0s !important;
    scroll-behavior: auto !important;
  }
  /* The caret blink is native rather than a CSS animation, so the rule above
     does not stop it. */
  * { caret-color: transparent !important; }
`;
