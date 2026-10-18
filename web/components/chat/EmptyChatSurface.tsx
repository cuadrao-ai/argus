"use client";

import { useTranslation } from "react-i18next";
import type { ReactNode } from "react";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import {
  CAPTCHA_UNAVAILABLE_CODE,
  type GuestEntryErrorKind,
} from "@/lib/guest-captcha";
import { landingStarterSurfaceEpoch } from "@/lib/landing-intent";
import { researchRailEnabled } from "@/lib/private-alpha-flags";
import ChatInput from "./ChatInput";
import ChatLegalNotice from "./ChatLegalNotice";
import EmptyChatGreeting from "./EmptyChatGreeting";
import EmptyChatHeading from "./EmptyChatHeading";
import StarterActions, {
  type StarterSelectionMetadata,
  type WorkspaceStarterEntry,
} from "./StarterActions";
import type { WorkspaceComposer } from "./ChatWorkspace";
import type { ChatMention } from "./types";
import { useLandingStarterPrefill } from "./useLandingStarterPrefill";

type EmptyChatSurfaceProps = {
  isGuest: boolean;
  expiresAt?: string | null;
  guestSubmissionPending: boolean;
  guestSubmissionError: GuestEntryErrorKind | null;
  isStreamingResponse: boolean;
  isHydratingConversation: boolean;
  canConsumeLandingStarter: boolean;
  /** A setting the user stated, never something Argus inferred. */
  preferredName?: string | null;
  placeholder: string;
  composerNotice?: ReactNode;
  onSend: (
    text: string,
    selection?: ChatMention[] | StarterSelectionMetadata,
  ) => void | boolean | Promise<void | boolean>;
  onRetryGuestSubmission: () => void;
  onToast: (message: string) => void;
  /** A workspace replaces the heading, the chips and the composer's control. */
  workspace?: {
    lead: ReactNode;
    starterEntries: readonly WorkspaceStarterEntry[];
    composer: WorkspaceComposer;
  };
};

export default function EmptyChatSurface({
  isGuest,
  expiresAt,
  guestSubmissionPending,
  guestSubmissionError,
  isStreamingResponse,
  isHydratingConversation,
  canConsumeLandingStarter,
  preferredName,
  placeholder,
  composerNotice,
  onSend,
  onRetryGuestSubmission,
  onToast,
  workspace,
}: EmptyChatSurfaceProps) {
  const { t } = useTranslation();
  const { isBelowTablet } = useResponsiveLayout();
  const landingDraftText = useLandingStarterPrefill(canConsumeLandingStarter && !workspace);
  const draftText = workspace ? workspace.composer.draftText : landingDraftText;
  const disabled =
    isStreamingResponse ||
    isHydratingConversation ||
    guestSubmissionPending ||
    guestSubmissionError === CAPTCHA_UNAVAILABLE_CODE;

  const showGreeting = researchRailEnabled;
  const showRegisteredDisclaimer = researchRailEnabled && !isGuest;

  // The tall top inset belongs to tablet and up. Expressing it as a min-width
  // variant rather than overriding a base value keeps `sm:` from winning the
  // cascade between 400 and 719px, where most phones actually sit.
  return (
    <div className="flex h-full flex-col items-center justify-start overflow-y-auto px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-6 tablet:pb-8 tablet:pt-[28vh]">
      {/* The heading absorbs the free space below the mobile threshold, which
          settles the pills and the composer onto the bottom edge where a thumb
          rests. Above it, the surface keeps its centered composition. */}
      <div className="order-1 flex w-full flex-col items-center max-tablet:flex-1 max-tablet:justify-center">
        {workspace ? (
          workspace.lead
        ) : showGreeting ? (
          // A guest always gets the neutral, nameless pool.
          <EmptyChatGreeting isGuest={isGuest} preferredName={preferredName} />
        ) : (
          <EmptyChatHeading isGuest={isGuest} />
        )}
      </div>

      <div
        aria-busy={guestSubmissionPending}
        className={
          showGreeting
            ? "order-3 w-full max-w-2xl"
            : "order-3 w-full max-w-2xl tablet:order-2"
        }
      >
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
        {guestSubmissionPending && (
          <div
            aria-label={t("guest.entry.sending", "Sending...")}
            className="mt-3 flex justify-center"
            role="status"
          >
            <span
              aria-hidden="true"
              className="h-4 w-4 animate-spin rounded-full border-2 border-black/25 border-t-black/70 dark:border-white/25 dark:border-t-white/70"
            />
            <span className="sr-only">
              {t("guest.entry.sending", "Sending...")}
            </span>
          </div>
        )}
        {guestSubmissionError && !guestSubmissionPending && (
          <div
            className="mt-3 flex flex-col items-center justify-center gap-2 text-center text-sm text-red-600 dark:text-red-300"
            role="alert"
          >
            {guestSubmissionError === CAPTCHA_UNAVAILABLE_CODE ? (
              <>
                <span>
                  {t(
                    "auth.errors.captcha_unavailable",
                    "This browser didn’t pass the security check. Open Argus in a regular browser, or reload the page.",
                  )}
                </span>
                <div className="flex flex-wrap items-center justify-center gap-2">
                  <button
                    type="button"
                    className="min-h-11 rounded-full border border-current px-4 py-2 font-medium"
                    onClick={() => window.location.reload()}
                  >
                    {t("guest.entry.reload", "Reload")}
                  </button>
                </div>
              </>
            ) : (
              <div className="flex flex-wrap items-center justify-center gap-2">
                <span>
                  {t(
                    "guest.entry.error",
                    "Argus couldn't open a temporary chat. Try again.",
                  )}
                </span>
                <button
                  type="button"
                  className="min-h-11 rounded-full border border-current px-4 py-2 font-medium"
                  onClick={onRetryGuestSubmission}
                >
                  {t("common.try_again", "Try again")}
                </button>
              </div>
            )}
          </div>
        )}
        <ChatLegalNotice
          expiresAt={expiresAt}
          isGuest={isGuest}
          showRegisteredDisclaimer={showRegisteredDisclaimer}
          showGuestSafetyLine={researchRailEnabled}
          variant="before_message"
        />
      </div>

      {/* One owner for the chips, always on. Flag off they sit above the
          composer on narrow screens and under it from tablet up; flag on, above
          at every width. They stop when this surface stops rendering. */}
      <div
        className={
          showGreeting
            ? "order-2 w-full max-w-2xl max-tablet:mb-3 tablet:mb-2"
            : "order-2 w-full max-w-2xl max-tablet:mb-3 tablet:order-3"
        }
      >
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
