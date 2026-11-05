import type { StarterSelectionMetadata } from "@/components/chat/StarterActions";
import type { ChatActionOption, ChatMention } from "./types";

export type SendOptions = {
  /** Durable identity for a receiver follow-up resumed after navigation. */
  requestId?: string;
  /** Wait for transport and normal reconciliation, without claiming durability. */
  awaitCompletion?: boolean;
  /** An authorized canonical final frame settled this request. */
  onTerminal?: () => void;
  renderUserMessage?: boolean;
  replacementAssistantId?: string;
  /** Keep the local turn when a pre-persist claim 503 has nothing durable to reload. */
  keepLocalTranscript?: boolean;
  bypassGuestGate?: boolean;
  /** Start a fresh conversation for this send, whatever the surface shows now. */
  startNewConversation?: boolean;
};

export type SendSelection =
  | ChatMention[]
  | ChatActionOption
  | StarterSelectionMetadata;

export type GuestPendingSubmission = {
  text: string;
  mentionsOrAction?: SendSelection;
  actionArg?: ChatActionOption;
  options?: SendOptions;
};

export function isStarterSelectionMetadata(
  selection: SendSelection | undefined,
): selection is StarterSelectionMetadata {
  return (
    !Array.isArray(selection) &&
    typeof selection === "object" &&
    selection !== null &&
    "strategy_category" in selection &&
    !("type" in selection)
  );
}
