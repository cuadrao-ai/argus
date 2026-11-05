"use client";

import { ArrowDown, Circle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { ConversationActivityIndicator } from "@/components/chat/ConversationActivityIndicator";
import type { ConversationActivityPresentation } from "@/lib/conversation-activity-state";

type ConversationActivityJumpLabels = Readonly<{
  latest: string;
  working: string;
  unread: string;
  needsInput: string;
  needsAttention: string;
}>;

type ConversationActivityJumpButtonProps = Readonly<{
  presentation: ConversationActivityPresentation;
  onJump: () => void;
  labels?: ConversationActivityJumpLabels;
}>;

export function ConversationActivityJumpButton({
  presentation,
  onJump,
  labels,
}: ConversationActivityJumpButtonProps) {
  const { t } = useTranslation();
  const resolvedLabels = labels ?? {
    latest: t("chat.jump_to_latest", "Jump to latest"),
    working: t(
      "chat.activity.jump_working",
      "Jump to latest; Cuadrao is working below",
    ),
    unread: t("chat.activity.jump_new", "Jump to new activity"),
    needsInput: t(
      "chat.activity.jump_needs_input",
      "Jump to the latest question",
    ),
    needsAttention: t(
      "chat.activity.jump_needs_attention",
      "Jump to the latest recovery",
    ),
  };
  const ariaLabel =
    presentation === "working"
      ? resolvedLabels.working
      : presentation === "needs_input"
        ? resolvedLabels.needsInput
        : presentation === "needs_attention"
          ? resolvedLabels.needsAttention
          : presentation === "new_activity" || presentation === "manual_unread"
            ? resolvedLabels.unread
            : resolvedLabels.latest;

  return (
    <button
      type="button"
      aria-label={ariaLabel}
      onClick={onJump}
      className="relative flex h-11 w-11 items-center justify-center rounded-full border border-black/10 bg-white/90 text-black transition-colors hover:bg-black/5 dark:border-white/10 dark:bg-[#1d2023]/95 dark:text-white dark:hover:bg-white/6"
    >
      {presentation === "working" ? (
        <span aria-hidden="true" className="flex items-center gap-1">
          {[0, 1, 2].map((index) => (
            <Circle
              key={index}
              data-working-dot={index + 1}
              className="h-1.5 w-1.5 animate-bounce fill-current stroke-0 text-black/45 [animation-duration:1.35s] motion-reduce:animate-none dark:text-white/55"
              style={{ animationDelay: `${index * 120}ms` }}
            />
          ))}
        </span>
      ) : (
        <span aria-hidden="true" className="relative inline-flex">
          <ArrowDown className="h-4 w-4" />
          {presentation !== "none" ? (
            <ConversationActivityIndicator
              presentation={presentation}
              compact
              className="absolute -right-2 -top-2"
            />
          ) : null}
        </span>
      )}
    </button>
  );
}
