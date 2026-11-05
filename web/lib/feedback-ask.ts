import type { Message } from "@/components/chat/types";
import { readStored, writeStored } from "./browser-storage";
import { feedbackContextForMessage } from "./chat-message-feedback-context";
import { isSettledStrategyResult } from "./chat-result-message";
import {
  feedbackContextForSubmission,
  type FeedbackRating,
} from "./feedback-context";

// Conversations whose ask has closed: answered, dismissed, or passed over by
// the next turn. The session set is truth; storage carries it across reloads.
const FEEDBACK_ASK_STORAGE_KEY = "argus:feedback-ask:v1" as const;
const closedThisSession = new Set<string>();

/** The one-tap answers, in the order the ask shows them. */
export const FEEDBACK_ASK_ANSWERS = [
  "negative",
  "neutral",
  "positive",
] as const satisfies readonly FeedbackRating[];

export const FEEDBACK_ASK_SOURCE = {
  source: "feedback_ask",
  surface: "chat",
} as const;

function readClosedIds(): Set<string> {
  try {
    const raw = readStored(FEEDBACK_ASK_STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return new Set();
    return new Set(
      parsed.filter((item): item is string => typeof item === "string"),
    );
  } catch {
    return new Set();
  }
}

export function hasAskedForFeedback(conversationId: string): boolean {
  return (
    closedThisSession.has(conversationId) ||
    readClosedIds().has(conversationId)
  );
}

export function markAskedForFeedback(conversationId: string): void {
  closedThisSession.add(conversationId);
  const ids = readClosedIds();
  ids.add(conversationId);
  writeStored(FEEDBACK_ASK_STORAGE_KEY, JSON.stringify([...ids].sort()));
}

function isLandedResult(message: Message): boolean {
  if (message.role !== "ai") return false;
  return (
    isSettledStrategyResult(message) ||
    (message.toolResultCards?.some(
      (card) => card.outcome.status === "succeeded",
    ) ??
      false)
  );
}

/** The result the ask follows: the latest one after the latest user message. */
export function landedResultThisTurn(
  messages: readonly Message[],
): Message | undefined {
  const latestUser = messages.findLastIndex((message) => message.role === "user");
  return messages.slice(latestUser + 1).findLast(isLandedResult);
}

/** The result's pointers, built the way message thumbs build them; never its text. */
export function feedbackAskPointers(result: Message, conversationId: string) {
  return feedbackContextForMessage(result, conversationId, FEEDBACK_ASK_SOURCE);
}

/** A tap saves its rating with the result's pointers, as a thumbs rating is saved. */
export function feedbackAskContext(
  pointers: Record<string, unknown>,
  rating: FeedbackRating,
) {
  return feedbackContextForSubmission(pointers, {
    includeConversationContext: true,
    rating,
    tags: [],
  });
}
