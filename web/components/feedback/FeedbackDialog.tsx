"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { useConversationSurface } from "@/components/chat/ChatWorkspace";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import {
  AlertCircle,
  Bug,
  Check,
  ChevronDown,
  Lightbulb,
  MessageCircle,
  Send,
} from "lucide-react";
import { postFeedback } from "@/lib/argus-api";
import { feedbackContextForSubmission } from "@/lib/feedback-context";

type FeedbackType = "bug" | "feature" | "general" | "rating";

interface FeedbackDialogProps {
  isOpen: boolean;
  onClose: () => void;
  type: FeedbackType;
  rating?: "positive" | "negative";
  context?: Record<string, unknown>;
}

type FeedbackTypeOption = {
  value: Exclude<FeedbackType, "rating">;
  label: string;
  icon: ReactNode;
};

export default function FeedbackDialog({
  isOpen,
  onClose,
  type: initialType,
  rating,
  context,
}: FeedbackDialogProps) {
  const { t } = useTranslation();
  const isBusiness = useConversationSurface() === "business";
  // The actions sit outside the form so they can stay pinned, so they submit
  // it by name instead of by containment.
  const formId = useId();
  const [type, setType] = useState<FeedbackType>(initialType);
  const [message, setMessage] = useState("");
  const [bugTitle, setBugTitle] = useState("");
  const [steps, setSteps] = useState("");
  const [expected, setExpected] = useState("");
  const [actual, setActual] = useState("");
  const [includeConversationContext, setIncludeConversationContext] =
    useState(false);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  /* Only for the types that open straight into writing. A rating opens on the
     stars, where taking focus to the notes field would skip the actual ask. */
  const messageRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    setType(initialType);
    setMessage("");
    setBugTitle("");
    setSteps("");
    setExpected("");
    setActual("");
    setIncludeConversationContext(false);
    setSelectedTags([]);
    setIsSubmitting(false);
    setIsSuccess(false);
    setError(null);
    setDropdownOpen(false);
  }, [initialType, isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const isRating = type === "rating";
  const isBug = type === "bug";
  const hasConversationContext =
    typeof context?.conversation_id === "string" && context.conversation_id.length > 0;

  const typeOptions: FeedbackTypeOption[] = [
    {
      value: "general",
      label: t("feedback.type.general", "General Feedback"),
      icon: <MessageCircle className="h-4 w-4" />,
    },
    {
      value: "bug",
      label: t("feedback.type.bug", "Report a Bug"),
      icon: <Bug className="h-4 w-4" />,
    },
    {
      value: "feature",
      label: t("feedback.type.feature", "Request a Feature"),
      icon: <Lightbulb className="h-4 w-4" />,
    },
  ];

  const currentType =
    typeOptions.find((option) => option.value === type) ?? typeOptions[0];

  const ratingTags =
    rating === "positive"
      ? [
          { key: "accurate", label: t("feedback.tags.positive.accurate", "Accurate") },
          { key: "exactly", label: t("feedback.tags.positive.exactly", "Exactly what I needed") },
          { key: "fast", label: t("feedback.tags.positive.fast", "Fast") },
          { key: "style", label: t("feedback.tags.positive.style", "Good format") },
          { key: "helpful", label: t("feedback.tags.positive.helpful", "Helpful") },
          { key: "other", label: t("feedback.tags.positive.other", "Other") },
        ]
      : [
          { key: "incorrect", label: t("feedback.tags.negative.incorrect", "Incorrect") },
          { key: "not_what_asked", label: t("feedback.tags.negative.not_what_asked", "Not what I asked") },
          { key: "slow", label: t("feedback.tags.negative.slow", "Too slow") },
          { key: "style", label: t("feedback.tags.negative.style", "Bad format") },
          { key: "safety", label: t("feedback.tags.negative.safety", "Safety concern") },
          { key: "other", label: t("feedback.tags.negative.other", "Other") },
        ];

  const canSubmit = () => {
    if (isRating) return selectedTags.length > 0 || message.trim().length > 0;
    if (isBug) return bugTitle.trim().length > 0 && steps.trim().length > 0;
    return message.trim().length > 0;
  };

  const toggleTag = (tagKey: string) => {
    setSelectedTags((current) =>
      current.includes(tagKey)
        ? current.filter((existing) => existing !== tagKey)
        : [...current, tagKey],
    );
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit()) return;

    setIsSubmitting(true);
    setError(null);

    const finalMessage = isBug
      ? [
          `${t("feedback.bug.message_title", "Title")}: ${bugTitle.trim()}`,
          `${t("feedback.bug.message_steps", "Steps to reproduce")}:\n${steps.trim()}`,
          `${t("feedback.bug.message_expected", "Expected outcome")}:\n${expected.trim()}`,
          `${t("feedback.bug.message_actual", "Actual outcome")}:\n${actual.trim()}`,
        ].join("\n\n")
      : message.trim();

    try {
      await postFeedback({
        type: isRating ? "general" : type,
        message:
          finalMessage ||
          (isRating ? t("feedback.rating_message_fallback", "{{rating}} rating with tags", { rating }) : ""),
        context: feedbackContextForSubmission(context, {
          includeConversationContext,
          rating,
          tags: selectedTags,
        }),
      });
      setIsSuccess(true);
      setTimeout(() => onClose(), 2000);
    } catch {
      setError(t("feedback.error", "We could not submit that yet. Please try again."));
    } finally {
      setIsSubmitting(false);
    }
  };

  const title = "Provide feedback";
  const displayTitle = t("feedback.title", title);

  const subheading = isRating
    ? rating === "positive"
      ? t("feedback.subheading.positive", "What worked well in this response?")
      : t("feedback.subheading.negative", "What should be improved in this response?")
    : type === "bug"
      ? t("feedback.subheading.bug", "File a bug report.")
      : type === "feature"
        ? t("feedback.subheading.feature", "Request a feature for Argus.")
        : isBusiness
          ? t("feedback.subheading.business_general", "Tell us how Cuadrao is working for you. We read every comment.")
          : t("feedback.subheading.general", "Share feedback about your Argus experience.");

  return (
    <AdaptivePanel
      title={displayTitle}
      closeLabel={t("feedback.close", "Close feedback")}
      onClose={onClose}
      width="lg"
      initialFocusRef={isRating ? undefined : messageRef}
      footer={
        <>
        {isSuccess ? null : (
          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="min-h-11 rounded-full border border-black/10 px-6 text-[14px] font-medium text-black transition-colors hover:bg-black/5 dark:border-white/10 dark:text-white dark:hover:bg-white/5"
            >
              {t("common.cancel", "Cancel")}
            </button>
            <button
              type="submit"
              form={formId}
              disabled={!canSubmit() || isSubmitting}
              className="flex min-h-11 items-center gap-2 rounded-full bg-black px-6 text-[14px] font-medium text-white transition-opacity hover:opacity-90 disabled:pointer-events-none disabled:opacity-40 dark:bg-white dark:text-black"
            >
              {isSubmitting ? (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
              ) : (
                t("feedback.submit", "Submit feedback")
              )}
            </button>
          </div>
        )}
        </>
      }
    >
      <p className="px-5 pt-4 text-[13px] leading-relaxed text-black/50 dark:text-white/50">
        {subheading}
      </p>
        <div className="argus-thin-scrollbar flex-1 overflow-y-auto p-5 sm:p-6">
          {isSuccess ? (
            <div className="py-12 text-center">
              <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-[#5ba897]/10">
                <Send className="h-7 w-7 text-[#5ba897]" />
              </div>
              <p className="font-display text-[18px] font-medium text-black dark:text-white">
                {t("feedback.success_detail", "Feedback submitted.")}
              </p>
            </div>
          ) : (
            <form
              id={formId}
              onSubmit={handleSubmit}
              className="flex flex-col gap-6"
            >
              {!isRating && (
                <div className="relative">
                  <label className="mb-2 block text-[13px] font-medium uppercase tracking-wide text-black/60 dark:text-white/60">
                    {t("feedback.type_label", "Feedback type")}
                  </label>
                  <button
                    type="button"
                    onClick={() => setDropdownOpen((open) => !open)}
                    className="flex w-full items-center justify-between rounded-xl border border-black/10 bg-white px-4 py-3 text-[14px] text-black transition-colors hover:border-black/20 dark:border-white/10 dark:bg-[#25282d] dark:text-white dark:hover:border-white/20"
                  >
                    <span className="flex items-center gap-3">
                      <span className="text-black/40 dark:text-white/40">
                        {currentType.icon}
                      </span>
                      <span className="font-medium">{currentType.label}</span>
                    </span>
                    <ChevronDown
                      className={`h-4 w-4 text-black/40 transition-transform dark:text-white/40 ${
                        dropdownOpen ? "rotate-180" : ""
                      }`}
                    />
                  </button>

                  {dropdownOpen && (
                    <div className="absolute left-0 top-[calc(100%+8px)] z-10 w-full overflow-hidden rounded-xl border border-black/10 bg-white py-1 dark:border-white/10 dark:bg-[#25282d]">
                      {typeOptions.map((option) => (
                        <button
                          key={option.value}
                          type="button"
                          onClick={() => {
                            setType(option.value);
                            setDropdownOpen(false);
                          }}
                          className="flex w-full items-center gap-3 px-4 py-3 text-left text-[14px] text-black transition-colors hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
                        >
                          <span className="text-black/40 dark:text-white/40">
                            {option.icon}
                          </span>
                          <span className="flex-1 font-medium">{option.label}</span>
                          {type === option.value && (
                            <Check className="h-4 w-4 text-[#4f55f1]" />
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {isBug && !isRating ? (
                <>
                  <div>
                    <label className="mb-2 block text-[13px] font-medium text-black/60 dark:text-white/60">
                      {t("feedback.bug.title_field", "Title")} *
                    </label>
                    <input
                      value={bugTitle}
                      onChange={(event) => setBugTitle(event.target.value.slice(0, 100))}
                      placeholder={t("feedback.bug.title_placeholder", "Brief description of the issue")}
                      className="w-full rounded-xl border border-black/10 bg-white px-4 py-3 text-[14px] text-black outline-none transition-colors placeholder:text-black/30 focus:border-[#4f55f1] dark:border-white/10 dark:bg-[#25282d] dark:text-white dark:placeholder:text-white/30"
                    />
                    <div className="mt-1 text-right text-[11px] text-black/30 dark:text-white/30">
                      {bugTitle.length}/100
                    </div>
                  </div>

                  <div>
                    <label className="mb-2 block text-[13px] font-medium text-black/60 dark:text-white/60">
                      {t("feedback.bug.steps_field", "Steps to reproduce")} *
                    </label>
                    <textarea
                      value={steps}
                      onChange={(event) => setSteps(event.target.value.slice(0, 1000))}
                      placeholder={t(
                        "feedback.bug.steps_placeholder",
                        "1. Go to [Page/View]\n2. Click on [Button/Action]\n3. See [Error/Behavior]",
                      )}
                      className="min-h-[100px] w-full resize-y rounded-xl border border-black/10 bg-white px-4 py-3 text-[14px] text-black outline-none transition-colors placeholder:text-black/30 focus:border-[#4f55f1] dark:border-white/10 dark:bg-[#25282d] dark:text-white dark:placeholder:text-white/30"
                    />
                    <div className="mt-1 text-right text-[11px] text-black/30 dark:text-white/30">
                      {steps.length}/1000
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div>
                      <label className="mb-2 block text-[13px] font-medium text-black/60 dark:text-white/60">
                        {t("feedback.bug.expected_field", "Expected outcome")}
                      </label>
                      <textarea
                        value={expected}
                        onChange={(event) => setExpected(event.target.value.slice(0, 500))}
                        className="min-h-[80px] w-full resize-none rounded-xl border border-black/10 bg-white px-4 py-3 text-[14px] text-black outline-none transition-colors focus:border-[#4f55f1] dark:border-white/10 dark:bg-[#25282d] dark:text-white"
                      />
                    </div>
                    <div>
                      <label className="mb-2 block text-[13px] font-medium text-black/60 dark:text-white/60">
                        {t("feedback.bug.actual_field", "Actual outcome")}
                      </label>
                      <textarea
                        value={actual}
                        onChange={(event) => setActual(event.target.value.slice(0, 500))}
                        className="min-h-[80px] w-full resize-none rounded-xl border border-black/10 bg-white px-4 py-3 text-[14px] text-black outline-none transition-colors focus:border-[#4f55f1] dark:border-white/10 dark:bg-[#25282d] dark:text-white"
                      />
                    </div>
                  </div>
                </>
              ) : (
                <div className={isRating ? "space-y-6" : ""}>
                  {isRating && (
                    <div>
                      <label className="mb-3 block text-[13px] font-medium text-black/60 dark:text-white/60">
                        {rating === "positive"
                          ? t("feedback.rating_positive_prompt", "What went well?")
                          : t("feedback.rating_negative_prompt", "What went wrong?")}
                      </label>
                      <div className="flex flex-wrap gap-2">
                        {ratingTags.map((tag) => (
                          <button
                            key={tag.key}
                            type="button"
                            onClick={() => toggleTag(tag.key)}
                            className={`rounded-full border px-4 py-2 text-[13px] font-medium transition-all ${
                              selectedTags.includes(tag.key)
                                ? "border-transparent bg-black text-white dark:bg-white dark:text-black"
                                : "border-black/10 bg-white text-black/70 hover:border-black/20 dark:border-white/10 dark:bg-[#25282d] dark:text-white/70 dark:hover:border-white/30"
                            }`}
                          >
                            {tag.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div>
                    <label className="mb-2 block text-[13px] font-medium text-black/60 dark:text-white/60">
                      {isRating
                        ? t("feedback.additional_details", "Additional details")
                        : `${t("feedback.details", "Details")} *`}
                    </label>
                    <textarea
                      ref={messageRef}
                      autoFocus={!isRating}
                      value={message}
                      onChange={(event) => setMessage(event.target.value.slice(0, 1000))}
                      placeholder={
                        isRating
                          ? t("feedback.rating_placeholder", "Tell us more about your experience...")
                          : t("feedback.details_placeholder", "What's on your mind?")
                      }
                      className="min-h-[140px] w-full resize-y rounded-xl border border-black/10 bg-white px-4 py-3 text-[14px] text-black outline-none transition-colors placeholder:text-black/30 focus:border-[#4f55f1] dark:border-white/10 dark:bg-[#25282d] dark:text-white dark:placeholder:text-white/30"
                    />
                    <div className="mt-1 text-right text-[11px] text-black/30 dark:text-white/30">
                      {message.length}/1000
                    </div>
                  </div>
                </div>
              )}

              {hasConversationContext && (
                <label className="mt-1 flex cursor-pointer items-start gap-3 max-tablet:min-h-11 max-tablet:items-center">
                  <input
                    id="include-conversation-context"
                    type="checkbox"
                    checked={includeConversationContext}
                    onChange={(event) =>
                      setIncludeConversationContext(event.target.checked)
                    }
                    className="mt-0.5 h-4 w-4 accent-[#4f55f1]"
                  />
                  <span
                    className="select-none text-[13px] leading-snug text-black/60 dark:text-white/60"
                  >
                    {t(
                      "feedback.include_conversation_context",
                      "Include approved context from this conversation",
                    )}
                  </span>
                </label>
              )}

              {error && (
                <p className="flex items-center gap-2 rounded-lg bg-[#d66d75]/10 px-4 py-2 text-[13px] font-medium text-[#d66d75]">
                  <AlertCircle className="h-4 w-4" />
                  {error}
                </p>
              )}

              <p className="text-[12px] leading-relaxed text-black/45 dark:text-white/45">
                {hasConversationContext && includeConversationContext
                  ? t(
                      "feedback.footer_note_conversation",
                      "Approved conversation identifiers will be included. The transcript is not attached.",
                    )
                  : t(
                      "feedback.footer_note",
                      "No conversation transcript or contact information is attached.",
                    )}{" "}
                {!isBusiness && (
                <button
                  type="button"
                  className="font-medium text-black underline underline-offset-2 hover:text-black/70 dark:text-white dark:hover:text-white/70"
                >
                  {t("common.learn_more", "Learn more")}
                </button>
                )}
              </p>

            </form>
          )}
        </div>

        {/*
          Pinned, not the last row of the form. A bug report is long enough to
          push Submit past the bottom of a phone, and nothing about the cut-off
          content said there was an action down there to scroll to.
        */}
    </AdaptivePanel>
  );
}
