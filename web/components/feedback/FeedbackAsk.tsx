"use client";

import { useEffect, useReducer, useRef, useState } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ChatToastVariant } from "@/components/chat/ChatToast";
import type { Message } from "@/components/chat/types";
import { postFeedback } from "@/lib/argus-api";
import {
  FEEDBACK_ASK_ANSWERS,
  feedbackAskContext,
  feedbackAskPointers,
  hasAskedForFeedback,
  landedResultThisTurn,
  markAskedForFeedback,
} from "@/lib/feedback-ask";
import type { FeedbackRating } from "@/lib/feedback-context";

type FeedbackAskProps = {
  conversationId: string | null;
  messages: readonly Message[];
  /** A reply is arriving; the ask never shows over one. */
  answerArriving: boolean;
  /** The account's feedback capability. */
  enabled: boolean;
  /**
   * Opens the feedback dialog with the result's pointers, which its checkbox
   * attaches or not. The tap's saved row alone carries the rating.
   */
  onTellUsMore: (context: Record<string, unknown>) => void;
  onToast: (message: string, variant?: ChatToastVariant) => void;
};

const choiceClass =
  "min-h-11 rounded-full border border-black/10 bg-white px-4 text-[13px] font-medium text-black/75 transition-colors hover:border-black/25 disabled:pointer-events-none disabled:opacity-50 dark:border-white/10 dark:bg-[#25282d] dark:text-white/75 dark:hover:border-white/30";

export default function FeedbackAsk({
  conversationId,
  messages,
  answerArriving,
  enabled,
  onTellUsMore,
  onToast,
}: FeedbackAskProps) {
  const { t } = useTranslation();
  const [thankedIn, setThankedIn] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [, rerender] = useReducer((count: number) => count + 1, 0);
  const shownFor = useRef<string | null>(null);
  const tellUsMore = useRef<HTMLButtonElement>(null);
  const focusTellUsMore = useRef(false);

  const landedResult = landedResultThisTurn(messages);
  const thanked = conversationId !== null && thankedIn === conversationId;
  const asking =
    landedResult !== undefined &&
    enabled &&
    conversationId !== null &&
    !answerArriving &&
    !thanked &&
    !hasAskedForFeedback(conversationId);
  const visible =
    asking || (landedResult !== undefined && thanked && !answerArriving);

  // Sending the next turn closes an unanswered ask too, so it asks once.
  useEffect(() => {
    if (visible) {
      shownFor.current = conversationId;
    } else if (
      answerArriving &&
      conversationId !== null &&
      shownFor.current === conversationId
    ) {
      shownFor.current = null;
      markAskedForFeedback(conversationId);
      setThankedIn(null);
    }
  }, [answerArriving, conversationId, visible]);

  // A tap removes the answer buttons, so keyboard focus moves to the next step.
  useEffect(() => {
    if (!thanked || !focusTellUsMore.current) return;
    focusTellUsMore.current = false;
    tellUsMore.current?.focus();
  }, [thanked]);

  if (!visible || conversationId === null || landedResult === undefined) {
    return null;
  }
  const askedIn = conversationId;
  const pointers = feedbackAskPointers(landedResult, askedIn);

  const close = () => {
    markAskedForFeedback(askedIn);
    setThankedIn(null);
    rerender();
  };

  const answer = async (rating: FeedbackRating) => {
    if (saving) return;
    setSaving(true);
    try {
      await postFeedback({
        type: "general",
        message: t("feedback.rating_message_fallback", { rating }),
        context: feedbackAskContext(pointers, rating),
      });
      markAskedForFeedback(askedIn);
      focusTellUsMore.current = true;
      setThankedIn(askedIn);
    } catch {
      onToast(
        t("feedback.error", "We could not submit that yet. Please try again."),
        "error",
      );
    } finally {
      setSaving(false);
    }
  };

  const question = t("feedback.ask.question", "How is Cuadrao doing?");

  return (
    <div
      role="group"
      aria-label={question}
      data-testid="feedback-ask"
      className="flex w-full max-w-[min(100%,660px)] flex-wrap items-center gap-x-3 gap-y-2 rounded-[14px] border border-black/10 bg-black/[0.02] py-1.5 pl-4 pr-1.5 text-[13px] text-black/70 dark:border-white/10 dark:bg-white/[0.03] dark:text-white/70"
    >
      <p aria-live="polite" className="flex-1 leading-[1.45]">
        {thanked ? t("feedback.ask.thanks", "Thanks for telling us.") : question}
      </p>
      {thanked ? (
        <button
          ref={tellUsMore}
          type="button"
          onClick={() => {
            close();
            onTellUsMore(pointers);
          }}
          className={choiceClass}
        >
          {t("feedback.ask.tell_more", "Tell us more")}
        </button>
      ) : (
        <div className="flex flex-wrap gap-2">
          {FEEDBACK_ASK_ANSWERS.map((rating) => (
            <button
              key={rating}
              type="button"
              disabled={saving}
              onClick={() => void answer(rating)}
              className={choiceClass}
            >
              {t(`feedback.ask.answers.${rating}`)}
            </button>
          ))}
        </div>
      )}
      <button
        type="button"
        onClick={close}
        aria-label={t("feedback.ask.dismiss", "Don't ask again in this chat")}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-current/60 transition-colors hover:bg-black/5 hover:text-current focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-current/25 dark:hover:bg-white/5"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
}
