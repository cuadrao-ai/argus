import { browserAuthGeneration, browserLogoutGeneration, invalidateBrowserAuth, requireBrowserAuthGeneration } from "./browser-auth-generation";
import { synchronizeBusinessAccount } from "./business-grant";
import { rememberReceiptFollowupClaim } from './receipt-followup-storage';
import { parseToolProgress, type ToolProgress, type ToolResultCard, type ToolScalar } from "./tool-result-card";
import { authenticatedRequestHeaders } from "./chat-auth-ownership";
import type { AccountRequestOptions } from "./argus-api-transport";
import { getSupabaseClient } from "./supabase-client";
import i18next from "i18next";
import { localizeArtifactFinalPayload } from "./artifact-response-transport";
import type { AssetClass, ConfirmationPeerSelection } from "./argus-types";
import type { ConversationPreview } from "./conversation-preview-display";
import type { ChatFinalResponsePayload } from "./chat-final-response-payload";
import type { SearchConversationItem as SearchConversationContract } from "./search-contract";
import type { DecisionState as RunDossierDecisionState } from "./run-dossier-contract";
import type {
  ChatActionOption,
  ChatMention,
  ToolJob,
  ExecutionCostEvidence,
  StrategyConfirmationPayload,
} from "@/components/chat/types";
import {
  normalizeEnabledLanguage,
  type ArgusLocale,
} from "./language-features";
import { isConversationMemoryOptOut } from "./memory-privacy";
import { currentViewportBand } from "./responsive-layout";
import {
  runActionIdempotencyKey,
  normalizeUsageAllowances,
  type RawUsageAllowanceResponse,
} from "./usage-allowance";
import type {
  DemonstratedInterest,
  MarketSessionPhase,
} from "@/components/chat/greetingPool";
import type { AvatarTheme } from "./avatar-theme";
import type { GuestPendingActionSummary } from "./guest-conversion";
import {
  displayResultActionLabel,
  displayResultMetricLabel,
  resultMetricDisplayOrder,
} from "./result-card-display";
import { acquirePasswordAuthCaptchaToken } from "./guest-captcha";
import { postPasswordAuth } from "./password-auth-request";
import { attributionBody } from "./landing-intent";
import { resultReadoutContentFromMetadata, type ResultReadoutContent } from "./result-readout-content";
import { resultReadoutFacts } from "./result-readout-facts";
import {
  ARGUS_API_BASE_URL,
  apiFetch,
  unauthenticatedApiFetch,
} from "./argus-api-transport";
import { appendSurface, surfaceQuery, type ConversationSurface } from "./conversation-surface-api";
import { requireConversationInShell } from "./conversation-surface-guard";

export { apiFetch, unauthenticatedApiFetch } from "./argus-api-transport";
export type { ConversationSurface } from "./conversation-surface-api";

// ─── Shared primitive types ──────────────────────────────────────────────────

export type { AssetClass, ConfirmationPeerIdentity, ConfirmationPeerSelection } from "./argus-types";
export type BacktestStatus = "queued" | "running" | "completed" | "failed";
export type BacktestJobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "canceled"
  | "expired";
export type TitleSource = "system_default" | "ai_generated" | "user_renamed";
export type HistoryItemType = "chat" | "strategy" | "collection" | "run";
export type ConversationOperationStatus =
  | "idle"
  | "queued"
  | "running"
  | "checking";
export type ConversationOperationKind = "chat_turn" | "backtest_job" | null;
export type ConversationOperation = {
  status: ConversationOperationStatus;
  kind?: ConversationOperationKind;
  updated_at?: string | null;
};
export type ConversationAttentionStatus =
  | "none"
  | "new_activity"
  | "manual_unread"
  | "needs_input"
  | "needs_attention";
export type ConversationAttention = {
  status: ConversationAttentionStatus;
  cursor?: string | null;
};
export type ConversationActivity = {
  operation: ConversationOperation;
  attention: ConversationAttention;
  latest_message_id?: string | null;
};
export type ConversationActivityPatch =
  | { action: "mark_unread" }
  | { action: "mark_read"; through_attention_cursor?: string | null };

// ─── Metric / result card types ──────────────────────────────────────────────

export type ApiMetricRow = {
  key: string;
  label: string;
  value: string;
};

export type ResultChartExplorationPolicy = {
  minimum_visible_observations?: number;
  minimum_meaningful_duration?: string | null;
};

export type ResultChartMarkerSummary = {
  total_groups: number;
  included_groups: number;
  sampled: boolean;
};

export type ResultChartPayload = {
  kind: "portfolio_equity";
  series: Array<{ time: string; value: number }>;
  markers?: Array<{
    time: string;
    type: "entry" | "exit";
    label: string;
    symbols?: string[];
  }>;
  currency?: string;
  base_value?: number | null;
  value_summary?: {
    peak_value?: number | null;
    lowest_value?: number | null;
    currency?: string | null;
    source?: "strategy_portfolio_equity_close" | string;
  } | null;
  value_extrema?: {
    peak?: { time: string; value: number } | null;
    lowest?: { time: string; value: number } | null;
  } | null;
  exploration_policy?: ResultChartExplorationPolicy | null;
  marker_summary?: ResultChartMarkerSummary | null;
  attribution?: string;
};

export type ConversationResultCard = {
  result_readout_content?: ResultReadoutContent | null;
  title: string;
  symbols?: string[];
  strategy_label?: string;
  asset_class?: AssetClass | null;
  idea_id?: string | null;
  idea_version_id?: string | null;
  evidence_artifact_id?: string | null;
  evidence_lifecycle?: ArtifactLifecycle | null;
  artifact_type?: "backtest" | string | null;
  decision_note_id?: string | null;
  decision_state?: DecisionState | null;
  date_range: {
    start: string;
    end: string;
    display: string;
  };
  status_label: string;
  rows: ApiMetricRow[];
  benchmark_note?: string | null;
  assumptions: string[];
  actions: ChatActionOption[];
  chart?: ResultChartPayload | null;
  execution_costs?: ExecutionCostEvidence | null;
  currency_fraction_digits?: number | null;
  profit?: number | null;
};

// ─── Domain objects ──────────────────────────────────────────────────────────

export type BacktestRun = {
  id: string;
  conversation_id?: string | null;
  strategy_id?: string | null;
  status: BacktestStatus;
  asset_class: AssetClass;
  symbols: string[];
  allocation_method: "equal_weight";
  benchmark_symbol: string;
  metrics: {
    aggregate: Record<string, unknown>;
    by_symbol: Record<string, unknown>;
  };
  config_snapshot: Record<string, unknown>;
  conversation_result_card: ConversationResultCard;
  chart?: ResultChartPayload | null;
  trades?: Record<string, unknown>[] | null;
  created_at: string;
  /** One-decimal display figures the backend derives from metrics on read. */
  figures?: Record<string, unknown> | null;
};

export type BacktestJob = {
  id: string;
  conversation_id: string;
  request_message_id?: string | null;
  confirmation_message_id?: string | null;
  // Absent on legacy rows; treat missing as a backtest job.
  operation_scope?: "chat.run_backtest" | "backtests.run" | "chat.research" | null;
  status: BacktestJobStatus;
  result_run_id?: string | null;
  failure_code?: string | null;
  failure_detail?: string | null;
  retryable: boolean;
  queued_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type BacktestJobResponse = {
  job: BacktestJob;
  run: BacktestRun | null;
  // A succeeded research job's answer, the way `run` is a backtest's result.
  result_message?: ApiMessage | null;
  /** Private source prose is never transported; retained slot for old clients. */
  result_readout?: null;
  result_readout_content?: ResultReadoutContent | null;
  result_readout_source?: string | null;
  next_experiments?: Record<string, unknown> | null;
  result_readout_fallback_used?: boolean | null;
  result_readout_failure_mode?: string | null;
};

export type Conversation = {
  id: string;
  title: string;
  title_source: TitleSource;
  pinned: boolean;
  archived: boolean;
  created_at: string;
  updated_at: string;
  last_message_preview?: string | null;
  preview?: ConversationPreview | null;
  language?: "en" | "es-419" | null;
  activity?: ConversationActivity | null;
  surface?: ConversationSurface;
};

type AuthSessionPayload = {
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
};

export type AuthResponsePayload = {
  session?: AuthSessionPayload | null;
  user?: Record<string, unknown> | null;
  guest_claim?: { conversation_id: string; pending_action: GuestPendingActionSummary | null } | null;
};

/** Backend message shape (distinct from the frontend chat Message type) */
export type ApiMessage = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  created_at: string;
  metadata?: (Record<string, unknown> & {
    /** Read-time API decision; clients must not infer it from attached facts. */
    artifact_presentation_kind?: "result" | "breakdown" | "assumptions" | "confirmation" | null;
  }) | null;
};

type HistoryItemBase = {
  type: HistoryItemType;
  id: string;
  title: string;
  /** Present on chat items; retained as optional for existing history consumers. */
  title_source?: TitleSource | null;
  subtitle: string;
  preview?: ConversationPreview | null;
  pinned: boolean;
  created_at: string;
  conversation_id?: string | null;
  expires_at?: string | null;
};

export type ChatHistoryItem = HistoryItemBase & {
  type: "chat";
  activity?: ConversationActivity | null;
};

export type NonChatHistoryItem = HistoryItemBase & {
  type: Exclude<HistoryItemType, "chat">;
  activity?: never;
};

export type HistoryItem = ChatHistoryItem | NonChatHistoryItem;

export type ArtifactLifecycle =
  | "captured"
  | "reviewed"
  | "saved"
  | "decided"
  | "archived"
  | "discarded";

export type DecisionState = RunDossierDecisionState;

export type EvidenceArtifact = {
  id: string;
  idea_id: string;
  idea_version_id: string;
  source_conversation_id?: string | null;
  source_run_id?: string | null;
  artifact_type: "backtest";
  lifecycle: ArtifactLifecycle;
  title: string;
  digest: string;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

// The decision contract owns this shape; a decision attaches to an evidence
// artifact or to a computed answer's message.
export type { DecisionNote } from "./decision-contract";
import type { DecisionNote } from "./decision-contract";

export type SearchConversationItem = SearchConversationContract;

export type SearchAssetRollupItem = {
  type: "asset_rollup";
  symbol: string;
  run_count: number;
  /** Every result involving the asset: runs plus computed answers; absent on older builds. */
  result_count?: number;
  decision_counts: Record<DecisionState, number>;
  last_touched_at: string;
};

export type SearchItem = SearchConversationItem | SearchAssetRollupItem;

export type SearchLedgerGroup = {
  decision_state: DecisionState;
  count: number;
};

export type SearchResponse = {
  items: SearchItem[];
  next_cursor: string | null;
  ledger_groups?: SearchLedgerGroup[] | null;
};

// ─── Chat stream event types ──────────────────────────────────────────────────

export type ChatStreamEvent =
  | { event: "token"; data: { text: string } }
  | { event: "title"; data: { conversation_id: string; title: string } }
  | { event: "status"; data: { status: string } }
  | { event: "stage_start"; data: { stage: string; detail?: string; tool_progress?: ToolProgress } }
  | { event: "stage_outcome"; data: { outcome: string } }
  | { event: "final"; data: ChatFinalPayload }
  | {
      event: "confirmation";
      data: { confirmation: StrategyConfirmationPayload };
    }
  | { event: "result"; data: { run: BacktestRun } }
  | {
      event: "error";
      data: {
        code?: string;
        detail: string;
        message_id?: string;
        recovery?: Record<string, unknown>;
        retry_last_turn?: Record<string, unknown>;
      };
    }
  | { event: "done"; data: { message_id: string | null } };

export type ChatFinalPayload = {
  result_readout_content?: ResultReadoutContent | null;
  code?: string;
  final_response_payload?: ChatFinalResponsePayload | null;
  stage_outcome?: string;
  assistant_response?: string | null;
  assistant_prompt?: string | null;
  response_intent?: Record<string, unknown> | null;
  confirmation?: StrategyConfirmationPayload | null;
  confirmation_cancelled?: { confirmation_id?: string | null } | null;
  confirmation_payload?: Record<string, unknown> | null;
  tool_result_cards?: ToolResultCard[];
  tool_jobs?: ToolJob[];
  pending_strategy?: {
    strategy: Record<string, unknown>;
    requested_field?: string | null;
    missing_required_fields?: string[];
    pending_resolution?: Record<string, unknown> | null;
  } | null;
  run?: BacktestRun | null;
  backtest_job?: BacktestJob | null;
  next_actions?: string[];
  message_id?: string | null;
  recovery?: Record<string, unknown> | null;
  retry_last_turn?: Record<string, unknown> | null;
};

export type ChatActionRequest = {
  type: NonNullable<ChatActionOption["type"]>;
  label?: string;
  labelKey?: string;
  payload?: Record<string, unknown>;
  presentation?: "confirmation" | "result";
};

export class ChatStreamError extends Error {
  constructor(
    message: string,
    public status: number,
    public code = "unknown",
    public requestId: string | null = null, public retryAfter: string | null = null,
  ) {
    super(message);
    this.name = "ChatStreamError";
  }
}
const CHAT_STREAM_INTERRUPTED_MESSAGE =
  "The connection ended before Argus finished responding. Please try again.";

export type DiscoveryItem = {
  id: string;
  type: "asset" | "indicator";
  label: string;
  symbol?: string | null;
  asset_class?: AssetClass | null;
  description?: string | null;
  insert_text: string;
  provider: string;
  // Optional: provider-backed discovery items carry it (the picker filters indicators
  // to "supported"); composer tokens reconstructed from the DOM do not need it.
  support_status?: "supported" | "draft_only" | "unavailable";
};

type DiscoveryResponsePayload = { items: DiscoveryItem[] };

// ─── Config ───────────────────────────────────────────────────────────────────

export type ApiLanguage = "en" | "es-419";

const DISCOVERY_SEARCH_CACHE_TTL_MS = 30_000;
const DISCOVERY_SEARCH_CACHE_MAX_ENTRIES = 80;
const discoverySearchCache = new Map<
  string,
  { expiresAt: number; promise: Promise<DiscoveryResponsePayload> }
>();

function discoverySearchCacheKey(
  kind: "assets" | "indicators",
  query: string,
  limit: number,
) {
  return `${kind}:${limit}:${query.trim().toLowerCase()}`;
}

function cachedDiscoverySearch(
  key: string,
  now: number,
): Promise<DiscoveryResponsePayload> | null {
  const cached = discoverySearchCache.get(key);
  if (!cached) return null;
  if (cached.expiresAt <= now) {
    discoverySearchCache.delete(key);
    return null;
  }
  discoverySearchCache.delete(key);
  discoverySearchCache.set(key, cached);
  return cached.promise;
}

function rememberDiscoverySearch(
  key: string,
  promise: Promise<DiscoveryResponsePayload>,
  expiresAt: number,
) {
  discoverySearchCache.delete(key);
  discoverySearchCache.set(key, { expiresAt, promise });
  while (discoverySearchCache.size > DISCOVERY_SEARCH_CACHE_MAX_ENTRIES) {
    const oldestKey = discoverySearchCache.keys().next().value;
    if (!oldestKey) break;
    discoverySearchCache.delete(oldestKey);
  }
}

// ─── Utilities ────────────────────────────────────────────────────────────────

export function resultCardFromConversationCard(
  card: ConversationResultCard,
  run?: Pick<BacktestRun, "id" | "strategy_id"> &
    Partial<
      Pick<BacktestRun, "asset_class" | "benchmark_symbol" | "config_snapshot" | "figures" | "metrics" | "symbols">
    >,
) {
  const rows = [...card.rows].sort(
    (a, b) => resultMetricDisplayOrder(a) - resultMetricDisplayOrder(b),
  );

  return {
    strategyName: card.title,
    strategyLabel: card.strategy_label,
    symbols: card.symbols,
    period: card.date_range.display,
    dateRange: card.date_range,
    statusLabel: card.status_label,
    metrics: rows.map((row) => ({
      key: row.key,
      label: displayResultMetricLabel(row, run?.benchmark_symbol),
      value: row.value,
    })),
    readoutContent: resultReadoutContentFromMetadata(card),
    readoutFacts: resultReadoutFacts({ ...run, symbols: run?.symbols ?? card.symbols, result_card: card }),
    assetClass: run?.asset_class ?? card.asset_class ?? undefined,
    configSnapshot: run?.config_snapshot,
    runId: run?.id,
    strategyId: run?.strategy_id ?? null,
    evidenceArtifactId: card.evidence_artifact_id ?? null,
    evidenceLifecycle: card.evidence_lifecycle ?? null,
    decisionNoteId: card.decision_note_id ?? null,
    decisionState: card.decision_state ?? null,
    actions: card.actions.map((action) => ({
      ...action,
      label: displayResultActionLabel(action),
    })),
    chart: card.chart ?? null,
    executionCosts: card.execution_costs ?? null,
    currencyFractionDigits: card.currency_fraction_digits ?? undefined,
    profit: card.profit ?? undefined,
  };
}

export function resultCardFromRun(run: BacktestRun) {
  return {
    ...resultCardFromConversationCard(run.conversation_result_card, run),
    symbols: run.symbols,
    template: String(run.config_snapshot?.template ?? ""),
    assetClass: run.asset_class,
    configSnapshot: run.config_snapshot,
  };
}

export function normalizeApiLanguage(language?: string | null): ApiLanguage {
  return normalizeEnabledLanguage(language);
}

/**
 * Formats an ISO timestamp as a human-readable relative date string.
 * Returns "today", "yesterday", or a short locale date string.
 */
export function formatRelativeDate(
  isoString: string,
  labels: { today: string; yesterday: string },
  locale: string = "en-US",
): string {
  const date = new Date(isoString);
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterdayStart = new Date(todayStart);
  yesterdayStart.setDate(yesterdayStart.getDate() - 1);

  if (date >= todayStart) return labels.today;
  if (date >= yesterdayStart) return labels.yesterday;

  return date.toLocaleDateString(locale, {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

export async function persistBrowserSession(payload: AuthResponsePayload) {
  const session = payload.session;
  if (!session?.access_token || !session.refresh_token) {
    return;
  }
  const supabase = getSupabaseClient();
  if (!supabase) {
    return;
  }
  const logoutGeneration = browserLogoutGeneration();
  const { data, error } = await supabase.auth.setSession({
    access_token: session.access_token,
    refresh_token: session.refresh_token,
  });
  if (error) {
    throw error;
  }
  if (logoutGeneration !== browserLogoutGeneration()) throw new Error("Browser session changed");
  synchronizeBusinessAccount(data?.session?.user.id ?? null);
  if (payload.guest_claim && data?.session?.user.id) {
    rememberReceiptFollowupClaim(data.session.user.id, payload.guest_claim.conversation_id);
  }
}

// ─── Profile ──────────────────────────────────────────────────────────────────

export type ProfilePatch = {
  language?: "en" | "es-419";
  locale?: ArgusLocale;
  display_name?: string;
  /** Empty clears it, which is how a user opts out of being addressed by name. */
  preferred_name?: string | null;
  avatar_theme?: AvatarTheme;
  /** ISO 3166-1 alpha-2; null clears it, and a user with none sends no location. */
  country?: string | null;
  /** ISO 4217; null goes back to the currency the country implies. */
  currency_override?: string | null;
};

export async function getMe(expectedUserId?: string) {
  return apiFetch<UserResponse>("/me", { expectedUserId });
}

export async function getUsageAllowances() {
  return normalizeUsageAllowances(
    await apiFetch<RawUsageAllowanceResponse>("/me/usage"),
  );
}

export type MarketSessionResponse = {
  session: {
    phase: MarketSessionPhase;
    is_market_day: boolean;
    as_of: string;
  } | null;
  interest: DemonstratedInterest | null;
};

/**
 * Which session US equities are in, resolved by the backend in Eastern time
 * against the real trading calendar, and what the caller's own records show
 * interest in. Either is null when unreadable, and callers say nothing about
 * the market rather than guessing.
 */
export async function getMarketSession(signal?: AbortSignal) {
  return apiFetch<MarketSessionResponse>("/market/session", { signal });
}

export async function patchMe(patch: ProfilePatch) {
  return apiFetch<UserResponse>("/me", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function getStarterPrompts() {
  const response = await apiFetch<{ prompts: string[] }>(
    "/chat/starter-prompts",
  );
  return response.prompts;
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export async function signupWithEmail(payload: {
  email: string;
  password: string;
  language: ApiLanguage;
  display_name?: string | null;
  username?: string | null;
  age_confirmed_at: string;
}) {
  if (!payload.age_confirmed_at) {
    throw Object.assign(new Error("age_confirmation_required"), {
      code: "age_confirmation_required",
    });
  }
  const generation = browserAuthGeneration();
  const captchaToken = await acquirePasswordAuthCaptchaToken();
  const response = await postPasswordAuth<AuthResponsePayload>("/auth/signup", {
    ...payload,
    captcha_token: captchaToken,
    ...attributionBody(),
  });
  requireBrowserAuthGeneration(generation);
  await persistBrowserSession(response);
  return { response, needsEmailConfirmation: !response.session };
}

export async function loginWithEmail(
  payload: {
    email: string;
    password: string;
  },
  options?: { requestTimeoutMs?: number },
) {
  const generation = browserAuthGeneration();
  const captchaToken = await acquirePasswordAuthCaptchaToken();
  const response = await postPasswordAuth<AuthResponsePayload>(
    "/auth/login",
    { ...payload, captcha_token: captchaToken },
    options?.requestTimeoutMs,
  );
  requireBrowserAuthGeneration(generation);
  await persistBrowserSession(response);
  return response;
}

export async function clearArgusSessionCookies() {
  return unauthenticatedApiFetch<{ success: boolean }>("/auth/logout", {
    method: "POST",
  });
}

export type CurrentBrowserLogoutResult = {
  revocation: "complete" | "failed";
  cookieSync: "cleared" | "failed";
};

export async function synchronizeCurrentBrowserLogout<T>(
  revokeCurrentSession: () => Promise<{ error: unknown | null }>,
  clearCookies: () => Promise<T>,
): Promise<CurrentBrowserLogoutResult> {
  const [revocation, cookieSync] = await Promise.allSettled([
    Promise.resolve().then(revokeCurrentSession),
    Promise.resolve().then(clearCookies),
  ]);
  return {
    revocation:
      revocation.status === "fulfilled" && !revocation.value.error
        ? "complete"
        : "failed",
    cookieSync: cookieSync.status === "fulfilled" ? "cleared" : "failed",
  };
}

export async function logoutFromApi() {
  invalidateBrowserAuth();
  synchronizeBusinessAccount(null);
  return synchronizeCurrentBrowserLogout(
    async () => {
      const supabase = getSupabaseClient();
      if (!supabase) return { error: null };
      return supabase.auth.signOut({ scope: "local" });
    },
    clearArgusSessionCookies,
  );
}

export async function createConversation(language?: string | null, options: AccountRequestOptions = {}, surface?: ConversationSurface) {
  const payload: { title: null; language?: ApiLanguage; surface?: "business" } = { title: null };
  if (language) {
    payload.language = normalizeApiLanguage(language);
  }
  if (surface === "business") payload.surface = surface;

  return apiFetch<{ conversation: Conversation }>("/conversations", {
    ...options,
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ─── Conversations ────────────────────────────────────────────────────────────

export async function listConversations(
  params: {
    limit?: number;
    cursor?: string;
    archived?: boolean;
    deleted?: boolean;
    surface?: ConversationSurface;
  } = {},
) {
  const { limit = 20, cursor, archived, deleted, surface } = params;
  const searchParams = new URLSearchParams({ limit: String(limit) });
  if (cursor) searchParams.append("cursor", cursor);
  if (archived !== undefined) searchParams.append("archived", String(archived));
  if (deleted !== undefined) searchParams.append("deleted", String(deleted));
  appendSurface(searchParams, surface);

  return apiFetch<{ items: Conversation[]; next_cursor: string | null }>(
    `/conversations?${searchParams.toString()}`,
  );
}

export async function getConversationMessages(
  conversationId: string,
  limit = 50,
  cursor?: string,
  options: Readonly<{
    signal?: AbortSignal;
    anchorMessageId?: string;
  }> = {},
) {
  const searchParams = new URLSearchParams({ limit: String(limit) });
  if (cursor) searchParams.append("cursor", cursor);
  if (options.anchorMessageId) {
    searchParams.append("anchor_message_id", options.anchorMessageId);
  }
  const page = await apiFetch<{ items: ApiMessage[]; next_cursor: string | null; surface?: ConversationSurface }>(
    `/conversations/${conversationId}/messages?${searchParams.toString()}`,
    { signal: options.signal },
  );
  requireConversationInShell(conversationId, page.surface);
  return page;
}

export async function addConfirmationPeerAssets(
  conversationId: string,
  confirmationId: string,
  selection: ConfirmationPeerSelection,
) {
  // Deterministic basket growth: no chat turn, no allowance spend. The
  // backend re-validates every symbol against the active turn's peer rows.
  const response = await apiFetch<{ message: ApiMessage }>(
    `/conversations/${conversationId}/confirmations/${confirmationId}/peer-assets`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(selection),
    },
  );
  return response.message;
}

export async function restoreConfirmationAssets(
  conversationId: string,
  confirmationId: string,
) {
  // Undo for a peer add: the backend re-materializes the exact previous
  // asset set from the card's own typed adjustment data.
  const response = await apiFetch<{ message: ApiMessage }>(
    `/conversations/${conversationId}/confirmations/${confirmationId}/peer-assets`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ restore_previous: true }),
    },
  );
  return response.message;
}

export async function recomputeToolResult(conversationId: string, messageId: string, card: ToolResultCard, changes: Record<string, ToolScalar>): Promise<ApiMessage> {
  const response = await apiFetch<{ message: ApiMessage }>(
    `/conversations/${encodeURIComponent(conversationId)}/tool-results/${encodeURIComponent(card.artifact_id)}/recompute`,
    { method: "POST", body: JSON.stringify({ message_id: messageId, input_revision: card.input_revision, arguments: changes }) },
  );
  return response.message;
}

export async function directEditConfirmation(
  conversationId: string,
  confirmationId: string,
  edit: {
    capital?: number;
    date_window?: { start: string; end: string };
  },
) {
  // Direct capital/date edit: no chat turn, no allowance spend, no backtest
  // row. The backend applies the typed values through the same edit contract
  // and validation chain as a conversational edit and returns the
  // superseding card message.
  const response = await apiFetch<{ message: ApiMessage }>(
    `/conversations/${conversationId}/confirmations/${confirmationId}/direct-edit`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(edit),
    },
  );
  return response.message;
}

export async function patchConversation(
  conversationId: string,
  patch: {
    title?: string;
    pinned?: boolean;
    archived?: boolean;
    deleted_at?: string | null;
  },
) {
  return apiFetch<{ conversation: Conversation }>(
    `/conversations/${conversationId}`,
    { method: "PATCH", body: JSON.stringify(patch) },
  );
}

export async function getConversationActivity(conversationId: string) {
  return apiFetch<ConversationActivity>(
    `/conversations/${conversationId}/activity`,
  );
}

export async function patchConversationActivity(
  conversationId: string,
  patch: ConversationActivityPatch,
  options: Readonly<{ signal?: AbortSignal }> = {},
) {
  return apiFetch<ConversationActivity>(
    `/conversations/${conversationId}/activity`,
    {
      method: "PATCH",
      body: JSON.stringify(patch),
      signal: options.signal,
    },
  );
}

export async function deleteConversation(conversationId: string) {
  return apiFetch<{ success: boolean }>(`/conversations/${conversationId}`, {
    method: "DELETE",
  });
}

export { listHistory, searchGlobal } from "./conversation-surface-api";

export async function createEvidenceDecision(
  artifactId: string,
  payload: { decision_state: DecisionState; note?: string | null },
) {
  return apiFetch<{
    decision: DecisionNote;
    evidence_artifact: EvidenceArtifact;
  }>(`/evidence-artifacts/${artifactId}/decision`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ─── Backtests ────────────────────────────────────────────────────────────────

export async function runBacktest(payload: {
  template?: string;
  asset_class?: AssetClass;
  symbols: string[];
  strategy_id?: string;
  conversation_id?: string;
  timeframe?: string;
  start_date?: string;
  end_date?: string;
  starting_capital?: number;
}) {
  return apiFetch<{ run: BacktestRun }>("/backtests/run", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": randomId(),
    },
    body: JSON.stringify(payload),
  });
}

export async function getBacktestRun(runId: string) {
  return apiFetch<{ run: BacktestRun }>(`/backtests/${runId}`);
}

export async function getBacktestJob(jobId: string) {
  return apiFetch<BacktestJobResponse>(`/backtest-jobs/${jobId}`);
}

// ─── Chat stream ──────────────────────────────────────────────────────────────

export type ChatStreamOptions = Readonly<{
  expectedUserId?: string;
  requestId?: string;
  signal?: AbortSignal;
  failedAssistantId?: string;
}>;

export async function streamChatMessage(
  conversationId: string,
  input: string | ChatActionRequest,
  language: string | null | undefined,
  onEvent: (event: ChatStreamEvent) => void,
  mentions: ChatMention[] = [],
  options: ChatStreamOptions = {},
) {
  const submittedRequestId = options.requestId ?? randomId();
  const authHeaders = await authenticatedRequestHeaders(options.expectedUserId);
  options.signal?.throwIfAborted();

  const response = await fetch(`${ARGUS_API_BASE_URL}/chat/stream`, {
    method: "POST",
    credentials: options.expectedUserId === undefined ? "include" : "omit",
    signal: options.signal,
    headers: {
      "Content-Type": "application/json",
      "X-Request-Id": submittedRequestId,
      "Idempotency-Key":
        (typeof input !== "string" && runActionIdempotencyKey(input)) ||
        randomId(),
      ...authHeaders,
    },
    body: JSON.stringify({
      conversation_id: conversationId,
      ...(options.failedAssistantId
        ? { failed_assistant_id: options.failedAssistantId }
        : {}),
      ...(typeof input === "string" ? { message: input } : { action: input }),
      // Forward caller-owned mentions, including discovery action identity.
      ...(mentions.length > 0 ? { mentions } : {}),
      language: normalizeApiLanguage(language),
      // Temporary chat narrows behavior; ordinary requests stay unchanged.
      ...(isConversationMemoryOptOut(conversationId)
        ? { memory_opt_out: true }
        : {}),
      // Width band, so a generated title is composed short rather than clipped.
      viewport: currentViewportBand(),
    }),
  }).catch(() => { throw new ChatStreamError(CHAT_STREAM_INTERRUPTED_MESSAGE, 0, "stream_interrupted", submittedRequestId); });
  const responseRequestId = response.headers.get("X-Request-Id")?.trim() || submittedRequestId;
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => ({}));
    const detail = (body as { detail?: unknown }).detail;
    const code = (body as { code?: unknown }).code;
    const message =
      typeof detail === "string"
        ? detail
        : typeof detail === "object" && detail !== null && "title" in detail
          ? String(
              (detail as { title?: unknown }).title ?? "Chat stream failed",
            )
          : "Chat stream failed";
    throw new ChatStreamError(
      message,
      response.status,
      typeof code === "string" ? code : "unknown", responseRequestId,
      response.headers.get("Retry-After"),
    );
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let receivedDone = false;
  const dispatchParsedFrame = (part: string) => {
    const parsed = parseChatStreamFrame(part);
    if (!parsed) return;
    onEvent(parsed.event === "final" ? {
      ...parsed,
      data: localizeArtifactFinalPayload(parsed.data, i18next.t.bind(i18next), i18next.resolvedLanguage ?? language ?? "en-US"),
    } : parsed);
    if (parsed.event === "done" || parsed.event === "error") {
      receivedDone = true;
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        dispatchParsedFrame(part);
      }
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      dispatchParsedFrame(buffer);
    }
  } catch (err) {
    if (err instanceof ChatStreamError) {
      throw err;
    }
    throw new ChatStreamError(
      CHAT_STREAM_INTERRUPTED_MESSAGE,
      0,
      "stream_interrupted",
      responseRequestId,
    );
  }

  if (!receivedDone) {
    throw new ChatStreamError(
      CHAT_STREAM_INTERRUPTED_MESSAGE,
      0,
      "stream_interrupted", responseRequestId,
    );
  }
}

export function parseChatStreamFrame(part: string): ChatStreamEvent | null {
  const lines = part.split("\n");
  const eventLine = lines.find((line) => line.startsWith("event: "));
  const dataLine = lines.find((line) => line.startsWith("data: "));
  if (!dataLine) return null;

  const raw = dataLine.replace("data: ", "").trim();
  if (raw === "[DONE]") {
    return { event: "done", data: { message_id: null } };
  }

  const payload = JSON.parse(raw) as Record<string, unknown>;
  if (eventLine) {
    return {
      event: eventLine.replace("event: ", "") as ChatStreamEvent["event"],
      data: payload,
    } as ChatStreamEvent;
  }

  const type = payload.type;
  if (type === "stage_start") {
    const progress = parseToolProgress(payload.tool_progress);
    return {
      event: "stage_start",
      data: {
        stage: String(payload.stage ?? ""),
        ...(progress ? { tool_progress: progress } : {}),
        ...(typeof payload.detail === "string" && payload.detail
          ? { detail: payload.detail }
          : {}),
      },
    };
  }
  if (type === "stage_outcome") {
    return {
      event: "stage_outcome",
      data: { outcome: String(payload.outcome ?? "") },
    };
  }
  if (type === "token") {
    return {
      event: "token",
      data: { text: String(payload.content ?? payload.text ?? "") },
    };
  }
  if (type === "final") {
    return {
      event: "final",
      data: (payload.payload ?? {}) as ChatFinalPayload,
    };
  }
  if (type === "title") {
    return {
      event: "title",
      data: {
        conversation_id: String(payload.conversation_id ?? ""),
        title: String(payload.title ?? ""),
      },
    };
  }
  if (type === "error") {
    return {
      event: "error",
      data: {
        code: typeof payload.code === "string" ? payload.code : undefined,
        detail: String(
          payload.message ?? payload.detail ?? "Chat stream failed",
        ),
        message_id:
          typeof payload.message_id === "string"
            ? payload.message_id
            : undefined,
        recovery: recordFromPayload(payload.recovery),
        retry_last_turn: recordFromPayload(payload.retry_last_turn),
      },
    };
  }
  return null;
}

function recordFromPayload(
  value: unknown,
): Record<string, unknown> | undefined {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return undefined;
  }
  return value as Record<string, unknown>;
}

export async function searchDiscovery(
  kind: "assets" | "indicators",
  query: string,
  limit = 8,
) {
  const cacheKey = discoverySearchCacheKey(kind, query, limit);
  const now = Date.now();
  const cached = cachedDiscoverySearch(cacheKey, now);
  if (cached) return cached;

  const searchParams = new URLSearchParams({ q: query, limit: String(limit) });
  const promise = apiFetch<DiscoveryResponsePayload>(
    `/discovery/${kind}?${searchParams.toString()}`,
  ).catch((error) => {
    if (discoverySearchCache.get(cacheKey)?.promise === promise) {
      discoverySearchCache.delete(cacheKey);
    }
    throw error;
  });
  rememberDiscoverySearch(
    cacheKey,
    promise,
    now + DISCOVERY_SEARCH_CACHE_TTL_MS,
  );
  return promise;
}

export async function postFeedback(payload: {
  type: "bug" | "feature" | "general" | "account_deletion_request";
  message: string;
  context?: Record<string, unknown>;
}) {
  return apiFetch<{ success: boolean }>("/feedback", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
import type { UserResponse } from "./guest-account";
import { randomId } from "./random-id";

export type {
  AccountCapabilities,
  ApiUser,
  GuestAccountSummary,
  UserResponse,
} from "./guest-account";
