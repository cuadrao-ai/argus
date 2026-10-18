import type { ConversationSurface } from "./conversation-surface-api";
import { businessPilotEnabled } from "./private-alpha-flags";

/**
 * A conversation opens only in the shell of its own surface. The backend says
 * which surface a conversation belongs to when its messages load; a shell that
 * receives the other surface's conversation sends it to that shell with the
 * same conversation id and never renders it.
 */
export class ConversationOnOtherSurfaceError extends Error {
  constructor(
    readonly conversationId: string,
    readonly surface: ConversationSurface,
  ) {
    super("This conversation belongs to the other chat surface.");
    this.name = "ConversationOnOtherSurfaceError";
  }
}

type Shell = Readonly<{
  surface: ConversationSurface;
  open: (conversationId: string, surface: ConversationSurface) => void;
}>;

let shell: Shell | null = null;

/** The mounted chat shell; returns the cleanup that unregisters it. */
export function registerConversationShell(next: Shell): () => void {
  shell = next;
  return () => {
    if (shell === next) shell = null;
  };
}

export function surfacePath(surface: ConversationSurface): string {
  return surface === "business" ? "/biz" : "/chat";
}

export const CONVERSATION_UNAVAILABLE = "conversation_unavailable";

/**
 * Where a shell sends a conversation that is not its own. On a Business build
 * a Personal conversation has no shell at all: the address keeps the page,
 * drops the conversation and names the notice, so nothing asks for that
 * conversation again and no reload loop is possible.
 */
export function conversationExitHref(
  currentHref: string,
  conversationId: string,
  surface: ConversationSurface,
  businessBuild: boolean = businessPilotEnabled,
): string {
  if (businessBuild && surface === "personal") {
    const current = new URL(currentHref);
    return `${current.pathname}?notice=${CONVERSATION_UNAVAILABLE}`;
  }
  return conversationShellHref(currentHref, conversationId, surface);
}

/** Throws, after sending the conversation to its own shell, when it belongs elsewhere. */
export function requireConversationInShell(
  conversationId: string,
  surface: ConversationSurface | undefined,
): void {
  if (!shell || !surface || surface === shell.surface) return;
  shell.open(conversationId, surface);
  throw new ConversationOnOtherSurfaceError(conversationId, surface);
}

/** The conversation's own shell, keeping the linked message when the address names it. */
export function conversationShellHref(
  currentHref: string,
  conversationId: string,
  surface: ConversationSurface,
): string {
  const current = new URL(currentHref);
  const next = new URLSearchParams({ conversation: conversationId });
  const message = current.searchParams.get("message");
  if (message && current.searchParams.get("conversation") === conversationId) {
    next.set("message", message);
  }
  return `${surfacePath(surface)}?${next.toString()}`;
}
