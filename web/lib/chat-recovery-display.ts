import i18next, { type TFunction } from "i18next";
import type { ChatActionOption } from "@/components/chat/types";
import { visibleComposerActions } from "@/lib/chat-action-ownership";
import { isRetryAction } from "@/lib/chat-retry-actions";
import { artifactAssumptionsFacts, artifactAssumptionsText, type ArtifactAssumptionsFacts } from "./artifact-assumptions-display";
import { resultReadoutFacts, type ResultReadoutFacts } from "./result-readout-facts";
import { resultBreakdownText } from "./result-readout-display";
import { DAILY_CAP_RECOVERY_CODE, formatDailyCapResetTime } from "./daily-cap-reset-time";

const UNSUPPORTED_STRATEGY_ACTION_ID_PREFIX = "unsupported-strategy-";
const NO_PROGRESS_ACTION_ID_PREFIX = "no-progress-";

/**
 * Reason codes whose localized sentence is complete without a list of options.
 * Mirrors SELF_SUFFICIENT_UNSUPPORTED_REASON_CODES in the backend contract: the
 * backend emits a typed contract for exactly these without options, so refusing
 * to render one here would drop the reader back onto the persisted English.
 */
const SELF_SUFFICIENT_UNSUPPORTED_REASON_CODES = new Set([
  "future_performance",
  "unsupported_time_granularity",
  "unsupported_starting_capital",
]);

function unsupportedRecoveryIsRenderable(
  reasonCode: string | undefined,
  optionCount: number,
): boolean {
  return (
    optionCount > 0 ||
    (reasonCode !== undefined &&
      SELF_SUFFICIENT_UNSUPPORTED_REASON_CODES.has(reasonCode))
  );
}

export type RecoveryDisplay =
  | { kind: "artifact_assumptions"; facts: ArtifactAssumptionsFacts }
  | { kind: "result_breakdown"; facts: ResultReadoutFacts | null }
  | {
      kind: "recovery_code";
      code: string;
      values?: Record<string, string>;
      /** The reply's content is an answer and this recovery its notice. */
      underAnswer?: boolean;
    }
  | {
      kind: "coverage_recovery";
      code: string;
    }
  | {
      kind: "unsupported_recovery";
      values: {
        reasonCode?: string;
        rawValue?: string;
        symbol?: string;
        minimum?: number;
        maximum?: number;
        options: Array<{
          label?: string;
          replacementValues?: Record<string, unknown> | null;
        }>;
      };
    }
  | {
      kind: "clarification";
      reasonCode?: string;
      requestedField?: string;
      semanticNeeds: string[];
      values?: Record<string, string>;
    }
  | {
      kind: "artifact_action_recovery";
      status: string;
      values?: Record<string, string>;
    }
  | {
      kind: "calculation_inputs";
      inputs: Array<{ name: string; labelKey: string; values: Record<string, string> }>;
    };

function recordOrNull(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function stringArrayOrNull(value: unknown): string[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const values = value.map((item) => String(item ?? "").trim()).filter(Boolean);
  return values.length > 0 ? values : null;
}

function finiteNumberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function recoveryDisplayFromMetadata(
  metadata: Record<string, unknown>,
): RecoveryDisplay | null {
  const artifactDisplay = recoveryDisplayFromResponseIntent(metadata.response_intent);
  if (artifactDisplay?.kind === "artifact_assumptions" || artifactDisplay?.kind === "result_breakdown") {
    return artifactDisplay;
  }
  const recoveryState = recoveryDisplayFromRecoveryState(metadata.recovery);
  if (recoveryState) {
    return recoveryState;
  }
  const clarification = recordOrNull(metadata.clarification);
  if (stringOrNull(clarification?.prompt_source) === "llm_generated") {
    return null;
  }
  return (
    recoveryDisplayFromClarification(clarification) ??
    recoveryDisplayFromResponseIntent(metadata.response_intent) ??
    recoveryDisplayFromResponseIntent(
      recordOrNull(metadata.pending_strategy)?.response_intent,
    )
  );
}

/**
 * A retryable recovery code marks transient infrastructure failure; the
 * assistant message wearing it renders as visibly-a-failure, never as a
 * normal answer (issue #249).
 */
export function retryableAssistantRecoveryCode(value: unknown): string | null {
  const recovery = recordOrNull(value);
  const code = stringOrNull(recovery?.code);
  if (!code) return null;
  return recovery?.retryable === true ? code : null;
}

/**
 * Codes whose recovery replaced the answer and cannot be retried: the reply is
 * a failure statement, so it wears the quiet notice. Every other non-retryable
 * code keeps its treatment; the amber notice stays gated on retryable alone.
 */
const QUIET_NOTICE_RECOVERY_CODES = new Set([
  "research_lookup_unavailable",
]);

/** Whether a reply renders as the quiet failure notice (failure-treatment.ts). */
export function wearsQuietFailureNotice(
  display: RecoveryDisplay | null | undefined,
): boolean {
  if (display?.kind === "artifact_action_recovery") return true;
  return (
    display?.kind === "recovery_code" && QUIET_NOTICE_RECOVERY_CODES.has(display.code)
  );
}

/**
 * Whether the backend marked the reply's content as an answer with this
 * recovery's notice under it (`recovery.under_answer`), rather than
 * compatibility text standing in for the notice.
 */
export function recoveryNoticeUnderAnswer(
  display: RecoveryDisplay | null | undefined,
): boolean {
  return display?.kind === "recovery_code" && display.underAnswer === true;
}

export function recoveryDisplayFromRecoveryState(
  value: unknown,
): RecoveryDisplay | null {
  const recovery = recordOrNull(value);
  const code = stringOrNull(recovery?.code);
  if (!code) {
    return null;
  }
  // llm_generated means the persisted assistant prose owns the display; the
  // typed code stays in metadata for hydration and analytics only.
  if (stringOrNull(recovery?.prompt_source) === "llm_generated") {
    return null;
  }
  const params = recordOrNull(recovery?.params);
  return {
    kind: "recovery_code",
    code,
    values: stringValues(params),
    ...(recovery?.under_answer === true ? { underAnswer: true } : {}),
  };
}

// A result fact the run does not store. Its answer is the message text; the
// unsupported-recovery copy belongs to rules Argus cannot run.
const RESULT_FACT_LIMITATION_CODE = "latest_result_metric_unavailable";

export function recoveryDisplayFromResponseIntent(
  value: unknown,
): RecoveryDisplay | null {
  const intent = recordOrNull(value);
  const kind = stringOrNull(intent?.kind);
  if (!intent || !kind) {
    return null;
  }
  if (kind === "artifact_assumptions") {
    return { kind, facts: artifactAssumptionsFacts(intent.facts) };
  }
  if (kind === "result_breakdown") {
    return { kind, facts: resultReadoutFacts(recordOrNull(intent.facts)?.result_fact_bank) };
  }
  if (kind === "unsupported_recovery") {
    if (
      stringOrNull(recordOrNull(intent.facts)?.limitation_code) ===
      RESULT_FACT_LIMITATION_CODE
    ) {
      return null;
    }
    return unsupportedRecoveryDisplay(intent);
  }
  if (kind === "artifact_action_recovery") {
    const facts = recordOrNull(intent.facts);
    const status = stringOrNull(facts?.status) ?? "invalid_state";
    const userSafeMessage = stringOrNull(facts?.user_safe_message);
    return {
      kind: "artifact_action_recovery",
      status,
      values: userSafeMessage ? { userSafeMessage } : undefined,
    };
  }
  return null;
}

export function recoveryDisplayText(
  display: RecoveryDisplay | null | undefined,
  t: TFunction,
  locale: string = i18next.resolvedLanguage ?? i18next.language ?? "en-US",
): string {
  if (!display) {
    return "";
  }
  if (display.kind === "artifact_assumptions") {
    return artifactAssumptionsText(display.facts, t, locale);
  }
  if (display.kind === "result_breakdown") {
    return resultBreakdownText(display.facts, t, locale);
  }
  if (display.kind === "recovery_code") {
    return t(`chat.recovery.${display.code}`, recoveryCodeValues(display, t, locale));
  }
  if (display.kind === "coverage_recovery") {
    return t(`chat.coverage_recovery.${display.code}`);
  }
  if (display.kind === "unsupported_recovery") {
    if (display.values.reasonCode === "data_window_unavailable") {
      return t("chat.clarification.data_window_unavailable");
    }
    if (display.values.reasonCode === "unsupported_time_granularity") {
      return display.values.rawValue
        ? t("chat.clarification.unsupported_timeframe_with_raw_value", {
            rawValue: display.values.rawValue,
          })
        : t("chat.clarification.unsupported_timeframe");
    }
    if (display.values.reasonCode === "future_performance") {
      const optionsText = joinLocalizedOptions(
        display.values.options.map((option) =>
          optionDisplayText(option, t, display.values.reasonCode),
        ),
        t,
      );
      return optionsText
        ? t("chat.clarification.future_performance_with_options", {
            options: optionsText,
          })
        : t("chat.clarification.future_performance");
    }
    if (display.values.reasonCode === "unsupported_starting_capital") {
      const minimum = display.values.minimum;
      const maximum = display.values.maximum;
      if (
        minimum !== undefined &&
        maximum !== undefined &&
        minimum <= maximum
      ) {
        return t("chat.clarification.starting_capital_range", {
          minimum: formatUsdAmount(minimum),
          maximum: formatUsdAmount(maximum),
        });
      }
      if (minimum !== undefined) {
        return t("chat.clarification.starting_capital_floor", {
          minimum: formatUsdAmount(minimum),
        });
      }
      return t("chat.clarification.starting_capital_unavailable_bounds");
    }
    const optionsText = joinLocalizedOptions(
      display.values.options.map((option) =>
        optionDisplayText(option, t, display.values.reasonCode),
      ),
      t,
    );
    if (!optionsText) {
      return "";
    }
    const symbol = display.values.symbol;
    const reasonCode = display.values.reasonCode;
    // No category: nothing was recognized as a rule, so ask for one.
    const ruleMissing = !reasonCode || reasonCode === "unsupported_constraint";
    const key = ruleMissing
      ? symbol
        ? "chat.clarification.unsupported_recovery_incomplete_for_asset"
        : "chat.clarification.unsupported_recovery_incomplete"
      : symbol
        ? "chat.clarification.unsupported_recovery_for_asset"
        : "chat.clarification.unsupported_recovery";
    return t(key, {
      symbol,
      options: optionsText,
    });
  }
  if (display.kind === "clarification") {
    return clarificationDisplayText(display, t);
  }
  if (display.kind === "calculation_inputs") {
    return calculationInputsText(display, t, locale);
  }
  const statusKey = artifactActionStatusKey(display.status);
  return t(`chat.recovery.${statusKey}`, artifactActionValues(display));
}

export function recoveryDisplayCopyText(
  display: RecoveryDisplay | null | undefined,
  t: TFunction,
  locale?: string,
): string | null {
  const localized = recoveryDisplayText(display, t, locale).trim();
  return localized || null;
}

function recoveryCodeValues(
  display: Extract<RecoveryDisplay, { kind: "recovery_code" }>,
  t: TFunction,
  locale: string,
): Record<string, string> {
  const values = display.values ?? {};
  if (display.code === DAILY_CAP_RECOVERY_CODE) {
    const time = formatDailyCapResetTime(Date.parse(values.resetAt), locale);
    return { ...values, time };
  }
  if (display.code === "execution_data_unavailable") {
    const dataKind = values.data_kind;
    const dataLabel =
      dataKind === "benchmark"
        ? t("chat.recovery.data_kind.benchmark")
        : t("chat.recovery.data_kind.market");
    return { ...values, dataLabel };
  }
  return values;
}

function unsupportedRecoveryDisplay(
  intent: Record<string, unknown>,
): RecoveryDisplay | null {
  const options = Array.isArray(intent.options)
    ? intent.options
        .map((option) => recordOrNull(option))
        .filter((option): option is Record<string, unknown> => Boolean(option))
        .map((option) => ({
          label: stringOrNull(option.label) ?? undefined,
          replacementValues: recordOrNull(option.replacement_values),
        }))
        .slice(0, 3)
    : [];
  const facts = recordOrNull(intent.facts);
  const reasonCode = unsupportedReasonCode(facts);
  if (!unsupportedRecoveryIsRenderable(reasonCode, options.length)) {
    return null;
  }
  const bounds = unsupportedNumericBounds(facts, reasonCode);
  return {
    kind: "unsupported_recovery",
    values: {
      reasonCode,
      rawValue: unsupportedRawValue(facts),
      symbol: primarySymbol(recordOrNull(facts?.strategy)),
      ...bounds,
      options,
    },
  };
}

function recoveryDisplayFromClarification(value: unknown): RecoveryDisplay | null {
  const clarification = recordOrNull(value);
  const kind = stringOrNull(clarification?.kind);
  if (!clarification || !kind) {
    return null;
  }
  const promptSource = stringOrNull(clarification.prompt_source);
  if (promptSource && promptSource !== "degraded_fallback") {
    return null;
  }
  if (kind === "coverage_recovery") {
    const code = stringOrNull(clarification.reason_code);
    return code ? { kind: "coverage_recovery", code } : null;
  }
  if (kind === "unsupported_recovery") {
    return unsupportedRecoveryDisplayFromClarification(clarification);
  }
  if (kind !== "clarification") {
    return null;
  }
  const missingInputs = missingInputsOrNull(clarification.missing_inputs);
  if (missingInputs) {
    return { kind: "calculation_inputs", inputs: missingInputs };
  }
  const payload = recordOrNull(clarification.payload);
  const semanticNeeds = stringArrayOrNull(clarification.semantic_needs) ?? [];
  return {
    kind: "clarification",
    reasonCode: stringOrNull(clarification.reason_code) ?? undefined,
    requestedField: stringOrNull(clarification.requested_field) ?? undefined,
    semanticNeeds,
    values: strategyValues(payload?.strategy),
  };
}

export function coverageRecoveryActionsFromMetadata(
  metadata: Record<string, unknown>,
  sourceAssistantId: string,
): ChatActionOption[] {
  if (!stringOrNull(sourceAssistantId)) {
    return [];
  }
  const clarification = recordOrNull(metadata.clarification);
  if (stringOrNull(clarification?.kind) !== "coverage_recovery") {
    return [];
  }
  const options = Array.isArray(clarification?.options)
    ? clarification.options
    : [];
  const allowed = new Map([
    ["change_dates", { field: "date_range", label: "Change dates" }],
    ["change_asset", { field: "asset_universe", label: "Change asset" }],
    [
      "change_benchmark",
      { field: "comparison_baseline", label: "Change benchmark" },
    ],
  ]);
  return options.flatMap((rawOption): ChatActionOption[] => {
    const option = recordOrNull(rawOption);
    const id = stringOrNull(option?.id);
    const definition = id ? allowed.get(id) : undefined;
    const replacementValues = recordOrNull(option?.replacement_values);
    if (
      !id ||
      !definition ||
      stringOrNull(replacementValues?.requested_field) !== definition.field
    ) {
      return [];
    }
    return [
      {
        id: `coverage-${id.replaceAll("_", "-")}`,
        label: definition.label,
        labelKey: `chat.coverage_recovery.actions.${id}`,
        type: "select_response_option",
        payload: {
          source_assistant_id: sourceAssistantId,
          option_id: id,
          replacement_values: { requested_field: definition.field },
        },
      },
    ];
  });
}

export function noProgressActionsFromMetadata(
  metadata: Record<string, unknown>,
  sourceAssistantId: string,
): ChatActionOption[] {
  if (!stringOrNull(sourceAssistantId)) {
    return [];
  }
  const rootIntent = recordOrNull(metadata.response_intent);
  const pendingIntent = recordOrNull(
    recordOrNull(metadata.pending_strategy)?.response_intent,
  );
  if (
    rootIntent &&
    pendingIntent &&
    canonicalJson(rootIntent) !== canonicalJson(pendingIntent)
  ) {
    return [];
  }
  const intent = rootIntent ?? pendingIntent;
  const facts = recordOrNull(intent?.facts);
  if (
    stringOrNull(intent?.kind) !== "clarification" ||
    stringOrNull(facts?.progress_outcome) !== "no_progress"
  ) {
    return [];
  }
  const requestedFields = new Set(stringArrayOrNull(intent?.requested_fields) ?? []);
  const options = Array.isArray(intent?.options) ? intent.options : [];
  const seen = new Set<string>();
  return options.flatMap((rawOption): ChatActionOption[] => {
    const option = recordOrNull(rawOption);
    const optionId = stringOrNull(option?.id);
    const label = stringOrNull(option?.label);
    const replacementValues = recordOrNull(option?.replacement_values);
    if (
      !optionId ||
      !label ||
      !replacementValues ||
      seen.has(optionId) ||
      !isAllowedNoProgressReplacement(
        optionId,
        replacementValues,
        requestedFields,
      )
    ) {
      return [];
    }
    seen.add(optionId);
    return [
      {
        id: `no-progress-${optionId.replaceAll("_", "-")}`,
        label,
        labelKey: `chat.clarification.no_progress_actions.${optionId}`,
        type: "select_response_option",
        payload: {
          source_assistant_id: sourceAssistantId,
          option_id: optionId,
          replacement_values: replacementValues,
        },
      },
    ];
  });
}

export function unsupportedTimeframeActionsFromMetadata(
  metadata: Record<string, unknown>,
  sourceAssistantId: string,
): ChatActionOption[] {
  if (!stringOrNull(sourceAssistantId)) {
    return [];
  }
  const clarification = recordOrNull(metadata.clarification);
  if (
    stringOrNull(clarification?.kind) !== "unsupported_recovery" ||
    stringOrNull(clarification?.reason_code) !== "unsupported_time_granularity"
  ) {
    return [];
  }
  const options = Array.isArray(clarification?.options)
    ? clarification.options
    : [];
  const allowedTimeframes = new Map([
    [
      "1D",
      {
        label: "Retry with daily bars",
        labelKey: "chat.clarification.timeframe_actions.daily",
      },
    ],
    [
      "1h",
      {
        label: "Retry with 1-hour bars",
        labelKey: "chat.clarification.timeframe_actions.hour_1",
      },
    ],
  ]);
  return options.flatMap((rawOption): ChatActionOption[] => {
    const option = recordOrNull(rawOption);
    const optionId = stringOrNull(option?.id);
    const replacementValues = recordOrNull(option?.replacement_values);
    if (
      !optionId ||
      !replacementValues ||
      Object.keys(replacementValues).length !== 1
    ) {
      return [];
    }
    const timeframe = stringOrNull(replacementValues.timeframe);
    const allowed = timeframe ? allowedTimeframes.get(timeframe) : undefined;
    if (!timeframe || !allowed) {
      return [];
    }
    return [
      {
        id: `unsupported-timeframe-${optionId.replaceAll("_", "-")}`,
        label: stringOrNull(option?.compatibility_label) ?? allowed.label,
        labelKey: allowed.labelKey,
        type: "select_response_option",
        payload: {
          source_assistant_id: sourceAssistantId,
          option_id: optionId,
          replacement_values: { timeframe },
        },
      },
    ];
  });
}

export function unsupportedStrategyActionsFromMetadata(
  metadata: Record<string, unknown>,
  sourceAssistantId: string,
): ChatActionOption[] {
  if (!stringOrNull(sourceAssistantId)) {
    return [];
  }
  const clarification = recordOrNull(metadata.clarification);
  if (
    stringOrNull(clarification?.kind) !== "unsupported_recovery" ||
    stringOrNull(clarification?.reason_code) !== "unsupported_strategy_logic"
  ) {
    return [];
  }
  const options = Array.isArray(clarification?.options)
    ? clarification.options
    : [];
  const allowedLabels = new Map([
    [
      "rsi_threshold",
      "Use a supported RSI threshold rule",
    ],
    ["buy_and_hold", "Compare with buy and hold"],
    [
      "moving_average_crossover",
      "Use a supported moving-average crossover",
    ],
  ]);
  return options.flatMap((rawOption): ChatActionOption[] => {
    const option = recordOrNull(rawOption);
    const optionId = stringOrNull(option?.id);
    const replacementValues = recordOrNull(option?.replacement_values);
    const label = optionId ? allowedLabels.get(optionId) : undefined;
    if (
      !optionId ||
      !replacementValues ||
      !label ||
      simplificationOptionKey(replacementValues) !== optionId
    ) {
      return [];
    }
    return [
      {
        id: `unsupported-strategy-${optionId.replaceAll("_", "-")}`,
        label,
        labelKey: `chat.simplification_options.${optionId}`,
        type: "select_response_option",
        payload: {
          source_assistant_id: sourceAssistantId,
          option_id: optionId,
          replacement_values: replacementValues,
        },
      },
    ];
  });
}

export function recoveryActionsFromMetadata(
  metadata: Record<string, unknown>,
  sourceAssistantId: string,
): ChatActionOption[] {
  return [
    ...coverageRecoveryActionsFromMetadata(metadata, sourceAssistantId),
    ...noProgressActionsFromMetadata(metadata, sourceAssistantId),
    ...unsupportedTimeframeActionsFromMetadata(metadata, sourceAssistantId),
    ...unsupportedStrategyActionsFromMetadata(metadata, sourceAssistantId),
  ];
}

function isUnsupportedStrategyResponseAction(action: ChatActionOption): boolean {
  return (
    action.type === "select_response_option" &&
    Boolean(action.id?.startsWith(UNSUPPORTED_STRATEGY_ACTION_ID_PREFIX))
  );
}

function isNoProgressResponseAction(action: ChatActionOption): boolean {
  return (
    action.type === "select_response_option" &&
    Boolean(action.id?.startsWith(NO_PROGRESS_ACTION_ID_PREFIX))
  );
}

export function visibleComposerResponseActions(
  actions: ChatActionOption[],
): ChatActionOption[] {
  return visibleComposerActions(actions).filter(
    (action) =>
      !isRetryAction(action) &&
      !isUnsupportedStrategyResponseAction(action) &&
      !isNoProgressResponseAction(action),
  );
}

function unsupportedRecoveryDisplayFromClarification(
  clarification: Record<string, unknown>,
): RecoveryDisplay | null {
  const options = Array.isArray(clarification.options)
    ? clarification.options
        .map((option) => recordOrNull(option))
        .filter((option): option is Record<string, unknown> => Boolean(option))
        .map((option) => ({
          label:
            stringOrNull(option.compatibility_label) ??
            stringOrNull(option.label) ??
            undefined,
          replacementValues: recordOrNull(option.replacement_values),
        }))
        .slice(0, 3)
    : [];
  const payload = recordOrNull(clarification.payload);
  const rawValue = stringOrNull(payload?.raw_value);
  const reasonCode = stringOrNull(clarification.reason_code) ?? undefined;
  if (!unsupportedRecoveryIsRenderable(reasonCode, options.length)) {
    return null;
  }
  const bounds = unsupportedNumericBounds(payload, reasonCode, true);
  return {
    kind: "unsupported_recovery",
    values: {
      reasonCode,
      rawValue:
        rawValue && !looksLikeInternalCode(rawValue) ? rawValue : undefined,
      symbol: primarySymbol(recordOrNull(payload?.strategy)),
      ...bounds,
      options,
    },
  };
}

function unsupportedReasonCode(
  facts: Record<string, unknown> | null,
): string | undefined {
  const constraints = Array.isArray(facts?.unsupported_constraints)
    ? facts.unsupported_constraints
    : [];
  for (const rawConstraint of constraints) {
    const category = stringOrNull(recordOrNull(rawConstraint)?.category);
    if (category) {
      return category;
    }
  }
  return undefined;
}

function unsupportedNumericBounds(
  source: Record<string, unknown> | null,
  reasonCode: string | undefined,
  direct = false,
): { minimum?: number; maximum?: number } {
  if (reasonCode !== "unsupported_starting_capital" || !source) {
    return {};
  }
  let boundsSource = source;
  if (!direct) {
    const constraints = Array.isArray(source.unsupported_constraints)
      ? source.unsupported_constraints
      : [];
    const constraint = constraints
      .map((item) => recordOrNull(item))
      .find(
        (item) =>
          stringOrNull(item?.category) === "unsupported_starting_capital",
      );
    if (!constraint) {
      return {};
    }
    boundsSource = constraint;
  }
  const minimum = finiteNumberOrNull(boundsSource.minimum);
  if (minimum === null) {
    return {};
  }
  if (!Object.hasOwn(boundsSource, "maximum")) {
    return { minimum };
  }
  const maximum = finiteNumberOrNull(boundsSource.maximum);
  if (maximum === null || minimum > maximum) {
    return {};
  }
  return {
    minimum,
    maximum,
  };
}

function strategyValues(value: unknown): Record<string, string> | undefined {
  const strategy = recordOrNull(value);
  const symbol = primarySymbol(strategy);
  const assets = stringArrayOrNull(strategy?.asset_universe);
  const assetText = assets?.join(", ");
  return {
    ...(symbol ? { symbol } : {}),
    ...(assetText ? { assetText } : {}),
  };
}

/** The figures a calculation still needs, named by their declaration label keys. */
function missingInputsOrNull(
  value: unknown,
): Extract<RecoveryDisplay, { kind: "calculation_inputs" }>["inputs"] | null {
  if (!Array.isArray(value)) return null;
  const inputs = value.flatMap((item) => {
    const raw = recordOrNull(item);
    const label = recordOrNull(raw?.label);
    const name = stringOrNull(raw?.name);
    const labelKey = stringOrNull(label?.locale_key);
    if (!name || !labelKey) return [];
    const args = recordOrNull(label?.interpolation_args) ?? {};
    const values = Object.fromEntries(
      Object.entries(args).map(([key, arg]) => [key, String(arg)]),
    );
    return [{ name, labelKey, values }];
  });
  return inputs.length > 0 ? inputs : null;
}

function calculationInputsText(
  display: Extract<RecoveryDisplay, { kind: "calculation_inputs" }>,
  t: TFunction,
  locale: string,
): string {
  const labels = display.inputs.flatMap((input) => {
    const label = t(input.labelKey, input.values).trim();
    if (!label || label === input.labelKey) return [];
    return [label.charAt(0).toLocaleLowerCase(locale) + label.slice(1)];
  });
  if (labels.length === 0) return "";
  const inputs = new Intl.ListFormat(locale, { style: "long", type: "conjunction" }).format(labels);
  return t("tools.calc.missing_inputs.ask", { inputs });
}

function clarificationDisplayText(
  display: Extract<RecoveryDisplay, { kind: "clarification" }>,
  t: TFunction,
): string {
  const key = clarificationKey(display);
  return key ? t(key, display.values ?? {}) : "";
}

function clarificationKey(
  display: Extract<RecoveryDisplay, { kind: "clarification" }>,
): string | null {
  const semanticNeeds = new Set(display.semanticNeeds);
  const requestedField = fieldBase(display.requestedField);
  const symbol = display.values?.symbol;
  const assetText = display.values?.assetText;
  if (requestedField === "date_range" || semanticNeeds.has("period")) {
    return symbol ? "chat.clarification.period_for_asset" : "chat.clarification.period";
  }
  if (requestedField === "asset_universe" || semanticNeeds.has("asset_target")) {
    return "chat.clarification.asset_target";
  }
  if (requestedField === "assumption" || semanticNeeds.has("assumption")) {
    return symbol
      ? "chat.clarification.assumption_for_asset"
      : "chat.clarification.assumption";
  }
  if (semanticNeeds.has("sizing_amount") && semanticNeeds.has("schedule")) {
    return "chat.clarification.sizing_amount_schedule";
  }
  if (requestedField === "capital_amount" || semanticNeeds.has("sizing_amount")) {
    return "chat.clarification.sizing_amount";
  }
  if (requestedField === "cadence" || semanticNeeds.has("schedule")) {
    return "chat.clarification.schedule";
  }
  if (
    requestedField === "entry_logic" ||
    requestedField === "exit_logic" ||
    semanticNeeds.has("rule_definition")
  ) {
    return "chat.clarification.rule_definition";
  }
  if (requestedField === "refinement" || semanticNeeds.has("refinement")) {
    return assetText
      ? "chat.clarification.refinement_for_asset"
      : "chat.clarification.refinement";
  }
  return null;
}

function fieldBase(value: string | undefined): string | null {
  return value ? value.split("[", 1)[0] : null;
}

function primarySymbol(strategy: Record<string, unknown> | null): string | undefined {
  const assets = stringArrayOrNull(strategy?.asset_universe);
  return assets?.[0]?.toUpperCase();
}

function unsupportedRawValue(
  facts: Record<string, unknown> | null,
): string | undefined {
  const constraints = Array.isArray(facts?.unsupported_constraints)
    ? facts?.unsupported_constraints
    : [];
  for (const item of constraints) {
    const constraint = recordOrNull(item);
    const value = stringOrNull(constraint?.raw_value);
    if (value && !looksLikeInternalCode(value)) {
      return value;
    }
  }
  return undefined;
}

function looksLikeInternalCode(value: string): boolean {
  if (
    value.includes("_") &&
    value === value.toLowerCase() &&
    !/\s/.test(value)
  ) {
    return true;
  }
  // Sentence punctuation marks an explanation, not a name (mirrors backend).
  return value.trimEnd().endsWith(".") || value.includes(". ");
}

function formatUsdAmount(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  const record = recordOrNull(value);
  if (record) {
    return `{${Object.keys(record)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function isAllowedNoProgressReplacement(
  optionId: string,
  values: Record<string, unknown>,
  requestedFields: ReadonlySet<string>,
): boolean {
  const keys = Object.keys(values);
  if (optionId === "supply_missing_value") {
    const requestedField = stringOrNull(values.requested_field);
    return (
      keys.length === 1 &&
      Boolean(requestedField && requestedFields.has(requestedField))
    );
  }
  if (optionId === "keep_unchanged" || optionId === "cancel") {
    return (
      keys.length === 1 &&
      stringOrNull(values.no_progress_action) === optionId
    );
  }
  return false;
}

function optionDisplayText(
  option: { label?: string; replacementValues?: Record<string, unknown> | null },
  t: TFunction,
  reasonCode?: string,
): string {
  const key = simplificationOptionKey(option.replacementValues, reasonCode);
  if (key) {
    return t(`chat.simplification_options.${key}`);
  }
  return option.label ?? "";
}

function simplificationOptionKey(
  values: Record<string, unknown> | null | undefined,
  reasonCode?: string,
): string | null {
  // The unsupported-symbol option is advisory — it carries no replacement
  // payload to key on, so the reason code is its localizable identity.
  if (
    reasonCode === "unsupported_symbol" &&
    (!values || Object.keys(values).length === 0)
  ) {
    return "supported_symbol";
  }
  if (!values) {
    return null;
  }
  if (values.simplify_logic === "rsi_only") {
    return "rsi_threshold";
  }
  if (ruleType(values.entry_rule) === "rsi_threshold") {
    return "rsi_threshold";
  }
  if (ruleType(values.exit_rule) === "rsi_threshold") {
    return "rsi_threshold";
  }
  const strategyTypeToken = canonicalStrategyTypeToken(values.strategy_type);
  if (
    ruleType(values.entry_rule) === "moving_average_crossover" ||
    ruleType(values.exit_rule) === "moving_average_crossover" ||
    values.rule_family === "moving_average_crossover" ||
    strategyTypeToken === "moving_average_crossover"
  ) {
    return "moving_average_crossover";
  }
  if (strategyTypeToken === "buy_and_hold") {
    return values.initial_capital !== undefined && values.initial_capital !== null
      ? "buy_and_hold_with_starting_capital"
      : "buy_and_hold";
  }
  // The DCA ceiling recovery's money-role options, keyed like the backend's
  // typed kinds so a Spanish reader never sees the English fallback labels.
  if (values.ignore_initial_capital === true) {
    return "recurring_only";
  }
  if (values.initial_capital !== undefined && values.initial_capital !== null) {
    return "use_as_starting_capital";
  }
  // The historical-period label belongs to future_performance recovery only;
  // ordinary date repair keeps its distinct backend-provided labels.
  if (
    values.requested_field === "date_range" &&
    reasonCode === "future_performance"
  ) {
    return "historical_period";
  }
  return null;
}

function ruleType(value: unknown): string | null {
  return stringOrNull(recordOrNull(value)?.type);
}

// The backend derives kinds from canonical_strategy_type, which lowercases
// and joins alphanumeric runs with underscores; this twin must not match
// narrower than that or a payload the backend keys ("Buy and Hold") falls
// back to the English compatibility label.
function canonicalStrategyTypeToken(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const token = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return token || null;
}

function joinLocalizedOptions(values: string[], t: TFunction): string {
  const options = values.map((value) => value.trim()).filter(Boolean);
  if (options.length <= 1) {
    return options[0] ?? "";
  }
  const orText = t("common.or");
  if (options.length === 2) {
    return `${options[0]} ${orText} ${options[1]}`;
  }
  return `${options.slice(0, -1).join(", ")}, ${orText} ${
    options[options.length - 1]
  }`;
}

function artifactActionStatusKey(status: string): string {
  if (status === "stale") {
    return "artifact_action_retry_stale";
  }
  if (status === "missing_artifact_id") {
    return "artifact_action_retry_missing_artifact_id";
  }
  if (status === "missing_payload") {
    return "artifact_action_retry_missing_payload";
  }
  if (status === "non_retryable") {
    return "artifact_action_retry_non_retryable";
  }
  if (status === "rebuilt_confirmation") {
    return "artifact_action_retry_rebuilt_confirmation";
  }
  if (status === "invalid_state") {
    return "artifact_action_invalid_state";
  }
  return "artifact_action_retry_inactive";
}

function artifactActionValues(
  display: Extract<RecoveryDisplay, { kind: "artifact_action_recovery" }>,
): Record<string, string> {
  const values = display.values ?? {};
  if (display.status !== "non_retryable") {
    return values;
  }
  const userSafeMessage = values.userSafeMessage?.trim();
  return {
    ...values,
    blockerSuffix: userSafeMessage ? `: ${userSafeMessage}` : "",
  };
}

function stringValues(
  value: Record<string, unknown> | null,
): Record<string, string> | undefined {
  if (!value) {
    return undefined;
  }
  const entries = Object.entries(value)
    .map(([key, item]) => [key, stringOrNull(item)] as const)
    .filter((entry): entry is readonly [string, string] => Boolean(entry[1]));
  return entries.length > 0 ? Object.fromEntries(entries) : undefined;
}
