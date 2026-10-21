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
import { primaryButtonClass, quietButtonClass } from "@/components/business-app/business-ui";
import { showToast } from "@/components/business-app/foundation/toasts";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { fieldClass, fieldErrorClass, fieldHintClass, fieldLabelClass } from "@/components/ui/form-field";
import {
  AlertCircle,
  Bug,
  Check,
  CircleCheck,
  ChevronDown,
  Lightbulb,
  MessageCircle,
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

const counterClass = "mt-1 text-right text-[13px] tabular-nums text-[#56635e] dark:text-white/55";

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
  const typeMenuId = useId();
  const formRef = useRef<HTMLFormElement>(null);
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
      // Business shows the one toast presenter; the older chat surface has none, so it confirms in the panel.
      if (isBusiness) {
        showToast({ kind: "success", text: t("feedback.success_detail", "Feedback submitted.") });
        onClose();
        return;
      }
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
        ? t("feedback.subheading.feature", "Request a feature for Cuadrao.")
        : isBusiness
          ? t("feedback.subheading.business_general", "Tell us how Cuadrao is working for you. We read every comment.")
          : t("feedback.subheading.general", "Share feedback about your Cuadrao experience.");

  return (
    <AdaptivePanel
      title={displayTitle}
      closeLabel={t("feedback.close", "Close feedback")}
      onClose={onClose}
      width="lg"
      initialFocusRef={isRating ? undefined : messageRef}
      footer={
        isSuccess ? null : (
          <div className="flex justify-end">
            <button
              type="submit"
              form={formId}
              disabled={!canSubmit() || isSubmitting}
              className={`${primaryButtonClass} max-tablet:w-full`}
            >
              {isSubmitting ? (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent motion-reduce:animate-none" aria-hidden="true" />
              ) : null}
              {t("feedback.submit", "Submit feedback")}
            </button>
          </div>
        )
      }
    >
      <p className={`px-5 pt-4 ${fieldHintClass}`}>
        {subheading}
      </p>
        <div className="argus-thin-scrollbar flex-1 overflow-y-auto p-5 sm:p-6">
          {isSuccess ? (
            <p role="status" className="flex items-start gap-2 rounded-item bg-[#e3ebe1] px-4 py-3 text-[16px] text-[#2f5a49] dark:bg-[#8fcbb0]/10 dark:text-[#8fcbb0]">
              <CircleCheck className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
              {t("feedback.success_detail", "Feedback submitted.")}
            </p>
          ) : (
            <form
              ref={formRef}
              id={formId}
              onSubmit={handleSubmit}
              noValidate
              className="flex flex-col gap-[21px]"
            >
              {!isRating && (
                <div className="relative">
                  <span id={`${typeMenuId}-label`} className={fieldLabelClass}>
                    {t("feedback.type_label", "Feedback type")}
                  </span>
                  <button
                    type="button"
                    aria-haspopup="listbox"
                    aria-expanded={dropdownOpen}
                    aria-controls={typeMenuId}
                    aria-labelledby={`${typeMenuId}-label ${typeMenuId}-value`}
                    onClick={() => setDropdownOpen((open) => !open)}
                    className={`${fieldClass} flex items-center justify-between gap-3 text-left`}
                  >
                    <span id={`${typeMenuId}-value`} className="flex items-center gap-3">
                      <span className="text-[#56635e] dark:text-white/60" aria-hidden="true">
                        {currentType.icon}
                      </span>
                      <span>{currentType.label}</span>
                    </span>
                    <ChevronDown
                      aria-hidden="true"
                      className={`h-4 w-4 shrink-0 text-[#56635e] transition-transform duration-200 ease-out dark:text-white/60 ${
                        dropdownOpen ? "rotate-180" : ""
                      }`}
                    />
                  </button>

                  {dropdownOpen && (
                    <div
                      id={typeMenuId}
                      role="listbox"
                      aria-labelledby={`${typeMenuId}-label`}
                      className="absolute left-0 top-[calc(100%+8px)] z-10 w-full origin-top rounded-surface border border-[#DCE0DA] bg-[var(--cuadrao-menu-surface)] p-1 dark:border-white/10"
                    >
                      {typeOptions.map((option) => (
                        <button
                          key={option.value}
                          type="button"
                          role="option"
                          aria-selected={type === option.value}
                          onClick={() => {
                            setType(option.value);
                            setDropdownOpen(false);
                          }}
                          className="flex min-h-11 w-full items-center gap-3 rounded-item px-3 text-left text-[16px] text-[#172b26] transition-colors hover:bg-[#F7F5EE] dark:text-white dark:hover:bg-white/[0.06]"
                        >
                          <span className="text-[#56635e] dark:text-white/60" aria-hidden="true">
                            {option.icon}
                          </span>
                          <span className="flex-1">{option.label}</span>
                          {type === option.value && (
                            <Check className="h-4 w-4 text-[var(--cuadrao-green)]" aria-hidden="true" />
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
                    <label htmlFor={`${formId}-bug-title`} className={fieldLabelClass}>
                      {t("feedback.bug.title_field", "Title")} *
                    </label>
                    <input
                      id={`${formId}-bug-title`}
                      value={bugTitle}
                      onChange={(event) => setBugTitle(event.target.value.slice(0, 100))}
                      placeholder={t("feedback.bug.title_placeholder", "Brief description of the issue")}
                      className={fieldClass}
                    />
                    <div className={counterClass}>
                      {bugTitle.length}/100
                    </div>
                  </div>

                  <div>
                    <label htmlFor={`${formId}-steps`} className={fieldLabelClass}>
                      {t("feedback.bug.steps_field", "Steps to reproduce")} *
                    </label>
                    <textarea
                      id={`${formId}-steps`}
                      value={steps}
                      onChange={(event) => setSteps(event.target.value.slice(0, 1000))}
                      placeholder={t(
                        "feedback.bug.steps_placeholder",
                        "1. Go to [Page/View]\n2. Click on [Button/Action]\n3. See [Error/Behavior]",
                      )}
                      className={`${fieldClass} min-h-[100px] resize-y`}
                    />
                    <div className={counterClass}>
                      {steps.length}/1000
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-[21px] md:grid-cols-2 md:gap-[13px]">
                    <div>
                      <label htmlFor={`${formId}-expected`} className={fieldLabelClass}>
                        {t("feedback.bug.expected_field", "Expected outcome")}
                      </label>
                      <textarea
                        id={`${formId}-expected`}
                        value={expected}
                        onChange={(event) => setExpected(event.target.value.slice(0, 500))}
                        className={`${fieldClass} min-h-[80px] resize-none`}
                      />
                    </div>
                    <div>
                      <label htmlFor={`${formId}-actual`} className={fieldLabelClass}>
                        {t("feedback.bug.actual_field", "Actual outcome")}
                      </label>
                      <textarea
                        id={`${formId}-actual`}
                        value={actual}
                        onChange={(event) => setActual(event.target.value.slice(0, 500))}
                        className={`${fieldClass} min-h-[80px] resize-none`}
                      />
                    </div>
                  </div>
                </>
              ) : (
                <div className={isRating ? "space-y-[21px]" : ""}>
                  {isRating && (
                    <fieldset>
                      <legend className={`mb-[13px] ${fieldLabelClass}`}>
                        {rating === "positive"
                          ? t("feedback.rating_positive_prompt", "What went well?")
                          : t("feedback.rating_negative_prompt", "What went wrong?")}
                      </legend>
                      <div className="flex flex-wrap gap-2">
                        {ratingTags.map((tag) => {
                          const selected = selectedTags.includes(tag.key);
                          return (
                            <button
                              key={tag.key}
                              type="button"
                              aria-pressed={selected}
                              onClick={() => toggleTag(tag.key)}
                              className={`inline-flex min-h-11 items-center gap-1.5 rounded-full border px-4 text-[15px] font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] ${
                                selected
                                  ? "border-[#2f5a49] bg-[#e3ebe1] text-[#2f5a49] dark:border-[#8fcbb0] dark:bg-[#8fcbb0]/10 dark:text-[#8fcbb0]"
                                  : "border-[#7d8a84]/60 bg-white text-[#172b26] hover:bg-[#F7F5EE] dark:border-white/20 dark:bg-transparent dark:text-white dark:hover:bg-white/[0.06]"
                              }`}
                            >
                              {selected && <Check className="h-4 w-4" aria-hidden="true" />}
                              {tag.label}
                            </button>
                          );
                        })}
                      </div>
                    </fieldset>
                  )}

                  <div>
                    <label htmlFor={`${formId}-message`} className={fieldLabelClass}>
                      {isRating
                        ? t("feedback.additional_details", "Additional details")
                        : `${t("feedback.details", "Details")} *`}
                    </label>
                    <textarea
                      id={`${formId}-message`}
                      ref={messageRef}
                      autoFocus={!isRating}
                      value={message}
                      onChange={(event) => setMessage(event.target.value.slice(0, 1000))}
                      placeholder={
                        isRating
                          ? t("feedback.rating_placeholder", "Tell us more about your experience...")
                          : t("feedback.details_placeholder", "What's on your mind?")
                      }
                      className={`${fieldClass} min-h-[140px] resize-y`}
                    />
                    <div className={counterClass}>
                      {message.length}/1000
                    </div>
                  </div>
                </div>
              )}

              {hasConversationContext && (
                <label className="flex min-h-11 cursor-pointer items-center gap-3">
                  <input
                    id="include-conversation-context"
                    type="checkbox"
                    checked={includeConversationContext}
                    onChange={(event) =>
                      setIncludeConversationContext(event.target.checked)
                    }
                    className="h-5 w-5 shrink-0 accent-[var(--cuadrao-green)]"
                  />
                  <span className="select-none text-[15px] leading-snug text-[#172b26] dark:text-white">
                    {t(
                      "feedback.include_conversation_context",
                      "Include approved context from this conversation",
                    )}
                  </span>
                </label>
              )}

              {error && (
                <div role="alert" className="rounded-item bg-[#f6dfe0] px-4 py-3 dark:bg-[#ec9aa0]/10">
                  <p className={`flex items-start gap-2 ${fieldErrorClass}`}>
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                    {error}
                  </p>
                  <button
                    type="button"
                    disabled={isSubmitting}
                    onClick={() => formRef.current?.requestSubmit()}
                    className={`${quietButtonClass} ml-6`}
                  >
                    {t("common.retry", "Retry")}
                  </button>
                </div>
              )}

              <p className={fieldHintClass}>
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
                  className="font-medium text-[var(--cuadrao-green)] underline underline-offset-2"
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
