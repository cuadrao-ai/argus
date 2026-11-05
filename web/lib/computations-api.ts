import { apiFetch } from "./argus-api-transport";
import type {
  ComputationComparison,
  ComputationRefresh,
  ComputedAnswerRef,
  ComputedAnswerSummary,
  ContinuedResult,
} from "./computation-contract";
import { appendSurface, type ConversationSurface } from "./conversation-surface-api";

const answerPath = (ref: ComputedAnswerRef) =>
  `/conversations/${encodeURIComponent(ref.conversation_id)}/messages/${encodeURIComponent(ref.message_id)}`;

/** The owner's other computed answers of one kind on one side, newest first, for a comparison. */
export function listComputedAnswers(kind: string, excludeMessageId?: string, surface?: ConversationSurface): Promise<{ items: ComputedAnswerSummary[] }> {
  const params = new URLSearchParams({ kind });
  if (excludeMessageId) params.set("exclude_message_id", excludeMessageId);
  appendSurface(params, surface);
  return apiFetch(`/computations/answers?${params.toString()}`);
}

/** Two owned answers of one kind side by side; the differences are the backend's. */
export function compareComputedAnswers(left: ComputedAnswerRef, right: ComputedAnswerRef): Promise<ComputationComparison> {
  return apiFetch("/computations/compare", { method: "POST", body: JSON.stringify({ left, right }) });
}

/** A new chat carrying only this result, linked to its unchanged source. */
export function continueComputedAnswer(ref: ComputedAnswerRef): Promise<ContinuedResult> {
  return apiFetch(`${answerPath(ref)}/continue`, { method: "POST" });
}

/** A paid retrieval of the answer's cited inputs, computed beside the stored answer. */
export function refreshComputedAnswer(ref: ComputedAnswerRef): Promise<ComputationRefresh> {
  return apiFetch(`${answerPath(ref)}/computation/refresh`, { method: "POST" });
}
