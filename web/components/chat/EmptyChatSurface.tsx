"use client";

import type { ReactNode } from "react";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { landingStarterSurfaceEpoch } from "@/lib/landing-intent";
import ChatInput from "./ChatInput";
import EmptyChatHeading from "./EmptyChatHeading";
import StarterActions, {
  type StarterSelectionMetadata,
  type WorkspaceStarterEntry,
} from "./StarterActions";
import type { WorkspaceComposer } from "./ChatWorkspace";
import type { ChatMention } from "./types";
import { useLandingStarterPrefill } from "./useLandingStarterPrefill";

type EmptyChatSurfaceProps = {
  isStreamingResponse: boolean;
  isHydratingConversation: boolean;
  canConsumeLandingStarter: boolean;
  placeholder: string;
  composerNotice?: ReactNode;
  onSend: (
    text: string,
    selection?: ChatMention[] | StarterSelectionMetadata,
  ) => void | boolean | Promise<void | boolean>;
  onToast: (message: string) => void;
  /** A workspace replaces the heading, the chips and the composer's control. */
  workspace?: {
    lead: ReactNode;
    starterEntries: readonly WorkspaceStarterEntry[];
    composer: WorkspaceComposer;
  };
};

export default function EmptyChatSurface({
  isStreamingResponse,
  isHydratingConversation,
  canConsumeLandingStarter,
  placeholder,
  composerNotice,
  onSend,
  onToast,
  workspace,
}: EmptyChatSurfaceProps) {
  const { isBelowTablet } = useResponsiveLayout();
  const landingDraftText = useLandingStarterPrefill(canConsumeLandingStarter && !workspace);
  const draftText = workspace ? workspace.composer.draftText : landingDraftText;
  const disabled = isStreamingResponse || isHydratingConversation;

  // The tall top inset belongs to tablet and up. Expressing it as a min-width
  // variant rather than overriding a base value keeps `sm:` from winning the
  // cascade between 400 and 719px, where most phones actually sit.
  return (
    <div className="flex h-full flex-col items-center justify-start overflow-y-auto px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-6 tablet:pb-8 tablet:pt-[28vh]">
      {/* The heading absorbs the free space below the mobile threshold, which
          settles the pills and the composer onto the bottom edge where a thumb
          rests. Above it, the surface keeps its centered composition. */}
      <div className="order-1 flex w-full flex-col items-center max-tablet:flex-1 max-tablet:justify-center">
        {workspace ? workspace.lead : <EmptyChatHeading />}
      </div>

      <div className="order-3 w-full max-w-2xl tablet:order-2">
        {composerNotice}
        <ChatInput
          key={workspace?.composer.draftKey ?? `new-conversation-${landingStarterSurfaceEpoch()}`}
          onSend={onSend}
          disabled={disabled}
          placeholder={workspace?.composer.placeholder ?? placeholder}
          onToast={onToast}
          draftText={draftText}
          leadingControl={workspace?.composer.leadingControl}
          onDraftChange={workspace?.composer.onDraftChange}
          onSent={workspace?.composer.onSent}
        />
      </div>

      <div className="order-2 w-full max-w-2xl max-tablet:mb-3 tablet:order-3">
        <StarterActions
          disabled={disabled}
          onSelect={onSend}
          layout={isBelowTablet ? "scroll" : "wrap"}
          entries={workspace?.starterEntries}
        />
      </div>
    </div>
  );
}
