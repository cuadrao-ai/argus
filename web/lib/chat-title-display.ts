import { WEB_APP_NAME } from "./app-brand";
import type { ConversationSurface } from "./conversation-surface-api";
import type { TitleSource } from "@/lib/argus-api";

export type ConversationTitleRecord = {
  title: string;
  title_source?: TitleSource | null;
};

export type HeaderTitleState = {
  conversationId: string;
  title: string;
  titleSource: TitleSource | null;
};

/** Backend default titles stay internal; unnamed chats render the localized placeholder. */
export function conversationDisplayTitle(
  record: ConversationTitleRecord | null | undefined,
  placeholder: string,
): string {
  if (!record) return placeholder;
  if (record.title_source === "system_default") return placeholder;
  if (!record.title.trim()) return placeholder;
  return record.title;
}

/** Rename starts empty until the chat carries a generated or user-chosen name. */
export function renamePrefillTitle(
  record: ConversationTitleRecord | null | undefined,
): string {
  if (!record) return "";
  if (
    record.title_source === "ai_generated" ||
    record.title_source === "user_renamed"
  ) {
    return record.title;
  }
  return "";
}

/** The reveal marks the naming event — never navigation, rename, or re-delivery. */
export function shouldPlayTitleReveal(
  previous: HeaderTitleState | null,
  next: HeaderTitleState | null,
): boolean {
  if (!previous || !next) return false;
  if (previous.conversationId !== next.conversationId) return false;
  if (next.titleSource !== "ai_generated") return false;
  if (
    previous.titleSource === "ai_generated" ||
    previous.titleSource === "user_renamed"
  ) {
    return false;
  }
  return previous.title !== next.title;
}

export function conversationTabTitle(
  record: ConversationTitleRecord | null,
  isChatViewActive: boolean,
  surface: ConversationSurface,
): string {
  const brand = surface === "business" ? WEB_APP_NAME : "Argus";
  const named = isChatViewActive && record &&
    (record.title_source === "ai_generated" || record.title_source === "user_renamed") &&
    record.title.trim();
  return named ? `${record.title} · ${brand}` : brand;
}
