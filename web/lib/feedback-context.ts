const BASE_KEYS = ["source", "surface"] as const;
const CONVERSATION_KEYS = [
  "conversation_id",
  "message_id",
  "message_kind",
  "artifact_id",
  "artifact_type",
  "artifact_status",
  "evidence_artifact_id",
  "result_run_id",
  "strategy_id",
  "saved_strategy_id",
  "confirmation_id",
  "confirmation_state",
  "confirmation_status",
  "backtest_job_id",
  "backtest_job_status",
  "failure_code",
  "retryable",
] as const;

export type FeedbackRating = "positive" | "neutral" | "negative";

type FeedbackContextOptions = {
  includeConversationContext: boolean;
  rating?: FeedbackRating;
  tags: string[];
};

function copyScalar(
  result: Record<string, unknown>,
  source: Record<string, unknown>,
  key: string,
) {
  const value = source[key];
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    result[key] = value;
  }
}

export function feedbackContextForSubmission(
  source: Record<string, unknown> | undefined,
  options: FeedbackContextOptions,
) {
  const input = source ?? {};
  const result: Record<string, unknown> = {};
  for (const key of BASE_KEYS) copyScalar(result, input, key);
  if (options.includeConversationContext) {
    for (const key of CONVERSATION_KEYS) copyScalar(result, input, key);
  }
  if (options.rating) result.rating = options.rating;
  result.tags = options.tags;
  return result;
}
