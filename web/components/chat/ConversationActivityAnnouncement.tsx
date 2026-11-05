"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { UseConversationActivityResult } from "@/components/chat/useConversationActivity";
import type {
  ConversationActivityAnnouncement as ActivityTransition,
  ConversationActivityPresentation,
} from "@/lib/conversation-activity-state";

type ActivityAnnouncementDescriptor = Readonly<{
  key: string;
  defaultValue: string;
  title: string;
}>;

type ActivityTranslation = (
  key: string,
  options: Readonly<{ defaultValue: string; title: string }>,
) => string;

type ActivityAnnouncementOwner = Pick<
  UseConversationActivityResult,
  "acknowledgeAnnouncement" | "getAnnouncement" | "selectPresentation"
>;

type AnnouncedPresentation = Exclude<
  ConversationActivityPresentation,
  "manual_unread" | "none"
>;

type ConsumedActivityAnnouncement = Readonly<{
  conversationId: string;
  key: string;
  presentation: AnnouncedPresentation;
}>;

const ANNOUNCEMENT_COPY: Record<
  AnnouncedPresentation,
  Readonly<{ key: string; defaultValue: string }>
> = {
  working: {
    key: "chat.activity.announce_working",
    defaultValue: "Cuadrao is working on {{title}}.",
  },
  needs_attention: {
    key: "chat.activity.announce_needs_attention",
    defaultValue: "{{title}} needs attention.",
  },
  needs_input: {
    key: "chat.activity.announce_needs_input",
    defaultValue: "{{title}} needs your input.",
  },
  new_activity: {
    key: "chat.activity.announce_new_activity",
    defaultValue: "{{title}} is ready.",
  },
};

export const conversationActivityAnnouncementDescriptor = (
  presentation: ActivityTransition["presentation"],
  title: string,
): ActivityAnnouncementDescriptor | null => {
  if (presentation === "manual_unread") return null;
  return { ...ANNOUNCEMENT_COPY[presentation], title };
};

export const consumeConversationActivityAnnouncement = ({
  activity,
  conversationId,
  transition,
  title,
}: Readonly<{
  activity: Pick<
    ActivityAnnouncementOwner,
    "acknowledgeAnnouncement"
  >;
  conversationId: string;
  transition: ActivityTransition;
  title: string | null;
}>): ConsumedActivityAnnouncement | null => {
  if (!title) return null;
  activity.acknowledgeAnnouncement(conversationId, transition.key);
  if (transition.presentation === "manual_unread") return null;
  return {
    conversationId,
    key: transition.key,
    presentation: transition.presentation,
  };
};

// The sentence reads the current title, so a real title replaces a placeholder
// that was showing when the announcement was consumed.
export const conversationActivityAnnouncementMessage = (
  consumed: Pick<ConsumedActivityAnnouncement, "presentation"> | null,
  title: string | null,
  translate: ActivityTranslation,
): string => {
  if (!consumed || !title) return "";
  const descriptor = conversationActivityAnnouncementDescriptor(
    consumed.presentation,
    title,
  );
  return descriptor ? translate(descriptor.key, descriptor) : "";
};

export function ConversationActivityLiveRegion({
  announcementKey,
  message,
}: Readonly<{ announcementKey: string; message: string }>) {
  return (
    <span
      data-testid="conversation-activity-announcement"
      className="sr-only"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <span key={announcementKey}>{message}</span>
    </span>
  );
}

export default function ConversationActivityAnnouncement({
  activity,
  conversationId,
  title,
  enabled = true,
}: Readonly<{
  activity: ActivityAnnouncementOwner;
  conversationId: string | null;
  title: string | null;
  enabled?: boolean;
}>) {
  const { t } = useTranslation();
  const [consumed, setConsumed] =
    useState<ConsumedActivityAnnouncement | null>(null);
  const transition = enabled && title
    ? activity.getAnnouncement(conversationId)
    : null;
  const presentation = enabled
    ? activity.selectPresentation(conversationId)
    : "none";

  useEffect(() => {
    if (!enabled || !conversationId) {
      setConsumed(null);
      return;
    }
    if (transition) {
      setConsumed(
        consumeConversationActivityAnnouncement({
          activity,
          conversationId,
          transition,
          title,
        }),
      );
      return;
    }
    if (
      presentation === "none" ||
      consumed?.conversationId !== conversationId
    ) {
      setConsumed(null);
    }
  }, [activity, consumed?.conversationId, conversationId, enabled, presentation, title, transition]);

  const announced =
    enabled && consumed?.conversationId === conversationId ? consumed : null;

  return (
    <ConversationActivityLiveRegion
      announcementKey={announced?.key ?? "none"}
      message={conversationActivityAnnouncementMessage(announced, title, t)}
    />
  );
}
