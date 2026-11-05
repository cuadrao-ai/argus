import type { AssetClass } from "@/lib/argus-types";
import type {
  ArtifactLifecycle,
  BacktestJob,
  DecisionState,
} from "@/lib/argus-api";
import type { ConfirmationDisplayFacts } from "@/lib/confirmation-assumptions-display";
import type { RecoveryDisplay } from "@/lib/chat-recovery-display";
import type { MemoryRecallItem } from "@/lib/memory-recalls";
import type { ResultReadoutContent } from "@/lib/result-readout-content";
import type { ResultReadoutFacts } from "@/lib/result-readout-facts";

export type StrategyResultMetric = {
  /** The card row's stable key, e.g. total_return_pct or contribution_return_pct. */
  key?: string;
  label: string;
  value: string;
};

export type ResultChartPoint = {
  time: string;
  value: number;
};

export type ResultChartMarker = {
  time: string;
  type: "entry" | "exit";
  label: string;
  symbols?: string[];
};

export type ResultChartValueSummary = {
  peak_value?: number | null;
  lowest_value?: number | null;
  currency?: string | null;
  source?: "strategy_portfolio_equity_close" | string;
};

export type ResultChartValuePoint = {
  time: string;
  value: number;
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
  series: ResultChartPoint[];
  markers?: ResultChartMarker[];
  currency?: string;
  base_value?: number | null;
  value_summary?: ResultChartValueSummary | null;
  value_extrema?: {
    peak?: ResultChartValuePoint | null;
    lowest?: ResultChartValuePoint | null;
  } | null;
  exploration_policy?: ResultChartExplorationPolicy | null;
  marker_summary?: ResultChartMarkerSummary | null;
  attribution?: string;
};

export type ArtifactType =
  | "strategy_draft"
  | "confirmation"
  | "backtest_job"
  | "backtest_run"
  | "result_review"
  | "failed_action"
  | "saved_strategy";

export type ChatActionOption = {
  id?: string;
  label: string;
  labelKey?: string;
  value?: string;
  type?:
    | "run_backtest"
    | "change_dates"
    | "change_asset"
    | "adjust_assumptions"
    | "cancel_confirmation"
    | "show_breakdown"
    | "refine_strategy"
    | "save_strategy"
    | "retry_failed_action"
    | "select_response_option"
    | "select_discovery_candidate"
    | "retry_last_turn"
    | "retry_load_conversation"
    | "retest_run"
    | "add_confirmation_peer"
    | "calculation_offer";
  presentation?: "confirmation" | "result";
  payload?: Record<string, unknown>;
  artifactId?: string;
  artifactType?: ArtifactType;
  artifactStatus?: string;
  savedStrategyId?: string | null;
  /** Client-owned: hide the retry control until this instant. */
  availableAtMs?: number;
};

export type ChatMention = {
  id: string;
  type: "asset" | "indicator";
  label: string;
  symbol?: string | null;
  asset_class?: AssetClass | null;
  description?: string | null;
  insert_text: string;
  provider?: string | null;
  message_range?: {
    start: number;
    end: number;
  };
};

export type StrategyResultPayload = {
  readoutFacts?: ResultReadoutFacts | null;
  readoutContent?: ResultReadoutContent | null;
  strategyName: string;
  strategyLabel?: string;
  symbols?: string[];
  template?: string;
  assetClass?: AssetClass;
  configSnapshot?: Record<string, unknown>;
  period: string;
  dateRange?: {
    start: string;
    end: string;
    display?: string;
  };
  benchmarkNote?: string;
  statusLabel?: string;
  metrics: StrategyResultMetric[];
  assumptions?: string[];
  runId?: string;
  strategyId?: string | null;
  evidenceArtifactId?: string | null;
  evidenceLifecycle?: ArtifactLifecycle | null;
  decisionNoteId?: string | null;
  decisionState?: DecisionState | null;
  artifactId?: string;
  artifactType?: ArtifactType;
  artifactStatus?: string;
  savedStrategyId?: string | null;
  savingStrategy?: boolean;
  actions?: ChatActionOption[];
  chart?: ResultChartPayload | null;
  executionCosts?: ExecutionCostEvidence | null;
  /** Money precision the backend stored on the result card. */
  currencyFractionDigits?: number;
  /** Run profit rounded by the backend at the card's stored precision. */
  profit?: number;
};

export type ExecutionCostEvidence = {
  fee_bps?: number | null;
  slippage_bps?: number | null;
  gross_total_return_pct?: number | null;
  net_total_return_pct?: number | null;
  return_drag_pct?: number | null;
  benchmark_treatment?: string | null;
};

export type StrategyConfirmationRowKey =
  | "strategy"
  | "assets"
  | "period"
  | "buy_rule"
  | "exit_rule"
  | "starting_capital"
  | "contribution";

export type StrategyConfirmationStatus =
  | "ready_to_run"
  | "needs_change"
  | "running"
  | "request_sent"
  | "run_complete"
  | "could_not_run"
  | "not_completed"
  | "editing"
  | "draft_canceled"
  | "updated";

export type StrategyConfirmationRow = {
  key?: StrategyConfirmationRowKey;
  label: string;
  labelKey?: string;
  value: string;
};

export type StrategyConfirmationDateRange = {
  start: string;
  end: string;
  display?: string;
};

export type StrategyConfirmationPeriodAdjustment = {
  code: string;
  requested_date_range: StrategyConfirmationDateRange;
  effective_date_range: StrategyConfirmationDateRange;
  limited_by?: { symbol: string; first_available: string };
};

export type StrategyConfirmationBenchmarkAdjustment = {
  code: string;
  requested_target: string;
  effective_benchmark: string;
};

/** §3.2: requested changes the edit turn could not apply, with reasons. */
export type StrategyConfirmationEditDisclosure =
  import("@/lib/artifact-edit-disclosure").ArtifactEditDisclosure;

export type StrategyConfirmationPayload = {
  /** Legacy wire cards may omit kind; the shared boundary normalizes them. */
  kind?: "backtest";
  confirmation_id?: string;
  confirmation_state?: "active" | "superseded" | "cancelled";
  asset_class?: AssetClass | null;
  artifactId?: string;
  artifactType?: ArtifactType;
  artifactStatus?: string;
  savedStrategyId?: string | null;
  title: string;
  status?: StrategyConfirmationStatus;
  statusLabel: string;
  strategy_type?: string;
  display_facts?: ConfirmationDisplayFacts;
  capabilities?: StrategyConfirmationCapabilities;
  date_range?: StrategyConfirmationDateRange;
  retest_period?: import("@/lib/chat-retest").RetestPeriodPayload | null;
  period_adjustment?: StrategyConfirmationPeriodAdjustment;
  benchmark_adjustment?: StrategyConfirmationBenchmarkAdjustment;
  assets_adjustment?: StrategyConfirmationAssetsAdjustment;
  edit_disclosure?: StrategyConfirmationEditDisclosure;
  rows: StrategyConfirmationRow[];
  assumptions?: string[];
  actions?: ChatActionOption[];
};

export type StrategyConfirmationAssetsAdjustment = {
  code: string;
  added: { symbol: string; name: string }[];
  previous_symbols: string[];
  symbols: string[];
  /* The one consequence a basket change can produce: the shared history
   * window clamps. Disclosed inline next to the period field. */
  period_change?: {
    from: { start: string; end: string };
    to: { start: string; end: string };
  } | null;
};

export type StrategyConfirmationCapabilities = {
  execution_costs_editable?: boolean;
  /** Direct no-turn edits the typed endpoint accepts for this card. */
  direct_edits?: ("capital" | "dates" | "costs")[];
  /** The accepted-value envelope for this card's edits: the engine's own
   * bounds, advertised so the client renders backend truth without owning
   * it. Rates are decimals; dates are ISO. */
  edit_constraints?: {
    capital?: { min?: number; max?: number };
    /** A recurring plan's two money roles, named so neither can stand in for
     * the other. `periods` lists only the contribution periods that fit this
     * card's window at least once. */
    starting_capital?: { min?: number; max?: number };
    contribution?: { min?: number; max?: number; periods?: string[] };
    fees?: { min?: number; max?: number };
    slippage?: { min?: number; max?: number };
    date_window?: { min_start?: string; max_end?: string };
  };
};

/** Typed values the direct-edit endpoint accepts; at least one is present.
 * Costs are decimal rates, converted from the editor's percent inputs. */
export type ConfirmationDirectEditPayload = {
  capital?: number;
  starting_capital?: number;
  recurring_contribution?: number;
  contribution_period?: string;
  date_window?: { start: string; end: string };
  fee_rate?: number;
  slippage?: number;
};

export type StrategyPathContext = {
  kind: "clarification" | "confirmation";
  requestedField?: string | null;
  strategy: Record<string, unknown>;
  sourceResultRunId?: string | null;
  strategyPathId?: string | null;
  optionalParameters?: Record<string, unknown> | null;
};

export type ToolJob = {
  call_id: string; tool_name: string; artifact_id: string; job: BacktestJob; resultMessageId?: string;
};

export type Message = {
  sharedConversation?: import("@/lib/shared-conversation").SharedConversation;
  id: string;
  /** Hidden durable message ids that should focus this projected transcript row. */
  transcriptAnchorIds?: string[];
  role: "user" | "ai";
  kind?:
    | "text"
    | "strategy_result"
    | "strategy_confirmation"
    | "backtest_job"
    | "action";
  contentPresentation?:
    | "result_readout"
    | "result_breakdown"
    | "conversation_load_failure"
    | "superseded_runtime_failure";
  content?: string;
  /** Read-time projection of a durable, unfinished show_breakdown request. */
  pendingBreakdown?: { turnId: string; requestId: string; conversationId: string };
  mentions?: ChatMention[];
  selectedAction?: ChatActionOption;
  result?: StrategyResultPayload;
  toolResultCards?: import("@/lib/tool-result-card").ToolResultCard[];
  /** Assumed inputs the backend says the prose never names, each on one of these cards. */
  answerAssumptions?: import("@/lib/tool-result-card").AnswerAssumption[] | null;
  hasUnavailableToolResults?: boolean;
  toolJobs?: ToolJob[];
  resultReadoutFacts?: ResultReadoutFacts | null;
  resultReadoutContent?: ResultReadoutContent | null;
  confirmation?: StrategyConfirmationPayload;
  backtestJob?: BacktestJob;
  // The message a terminal research job produced, once it is in the view;
  // until then the card keeps polling for it.
  researchResultMessageId?: string;
  resultBreakdownJobId?: string;
  isLoadingResult?: boolean;
  actions?: ChatActionOption[];
  artifactId?: string;
  artifactType?: ArtifactType;
  artifactStatus?: string;
  savedStrategyId?: string | null;
  /** Typed degraded/offline recovery display rendered through web i18n. */
  recoveryDisplay?: RecoveryDisplay | null;
  /** Existing backend-owned strategy facts used to prove turn continuity. */
  strategyPathContext?: StrategyPathContext | null;
  assistantRecoveryCode?: string | null;
  /** Backend-provided grounded-discovery sidecar (argus_discovery/v1). */
  discovery?: DiscoverySidecar | null;
  /** Typed sources from a research turn; the one surface every shape uses. */
  researchSources?: DiscoverySource[] | null;
  /**
   * The research sidecar's typed degraded code. Sources under it are the
   * pages Argus read and could not verify the answer with: where Argus
   * looked, never the sources of an answer.
   */
  researchDegradedCode?: string | null;
  /** Backend post-turn saved-decision recalls; rendered as context only. */
  memoryRecalls?: MemoryRecallItem[] | null;
  /** Backend-declared computation behind a computed answer; it offers a decision. */
  computation?: import("@/lib/decision-contract").DecisionComputation | null;
  /** A result continued from another chat; the source is linked and never changed. */
  continuedFrom?: import("@/lib/computation-contract").ContinuedFrom | null;
  /** Current decision stamped on a computed answer by the backend. */
  decisionNoteId?: string | null;
  decisionState?: DecisionState | null;
  /** Backend-owned structured context for a retest receipt turn. */
  retestReceipt?: import("@/lib/chat-retest").RetestReceipt | null;
  /** Ephemeral optimistic presentation; never hydrated or persisted. */
  retestReceiptPending?: boolean;
  nextExperiments?: import("@/lib/chat-next-experiments").NextExperimentRow[];
  /** The rows' run when the message carries no result card; continuity rows anchor on it. */
  nextExperimentsSourceRunId?: string | null;
  /** One ordered list of tests and questions under an answer about a result. */
  nextSteps?: import("@/lib/chat-next-steps").NextStep[] | null;
};

export type DiscoverySource = {
  title: string;
  domain: string;
  url: string;
  source_date?: string | null;
};

export type DiscoveryCandidate = {
  symbol: string;
  name: string;
  asset_class: AssetClass;
  reason_text: string;
  source_indices?: number[];
};

export type DiscoverySidecar = {
  schema_version: string;
  kind: "asset_discovery";
  relationship: "category" | "peer" | "comparison";
  query_summary: string;
  retrieved_at: string;
  sources: DiscoverySource[];
  candidates: DiscoveryCandidate[];
  unverified_names: string[];
  /** Backend-owned: the "search current results" escalation may render only
   * when true, so the row can never outlive the allowance. */
  can_request_search?: boolean;
};
