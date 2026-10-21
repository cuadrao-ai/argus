"use client";

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { BottomSheet } from "@/components/ui/BottomSheet";
import {
  commandPaletteOpenFallback,
  commandPaletteOpenLabelKey,
} from "@/lib/command-palette-items";
import type { CommandPaletteDisplayItem } from "@/lib/command-palette-items";

/**
 * The run dossier as an overlay sheet below the desktop stop, with
 * `Open conversation` pinned so it is reachable without scrolling the dossier.
 */
export default function CommandPaletteDossierSheet({
  preview,
  navigationDisabled,
  onClose,
  onOpenConversation,
  children,
}: {
  preview: CommandPaletteDisplayItem;
  navigationDisabled: boolean;
  onClose: () => void;
  /** Runs after the history entry is handed to the destination. */
  onOpenConversation: () => void;
  children: ReactNode;
}) {
  const { t } = useTranslation();

  return (
    <BottomSheet
      isOpen
      snaps={["full"]}
      title={preview.title}
      titleHidden
      closeLabel={t("command_palette.close_dossier", "Close dossier")}
      backLabel={t("common.back", "Back")}
      onClose={onClose}
      footer={
        <button
          type="button"
          data-testid="dossier-sheet-open-conversation"
          disabled={!preview.conversationId || navigationDisabled}
          onClick={() => {
            // The transcript route replaces the URL on the entry this sheet
            // pushed, so that entry belongs to the destination now. Popping it
            // would restore the conversation the user just left.
            onClose();
            onOpenConversation();
          }}
          className="flex min-h-11 w-full items-center justify-center rounded-full bg-black px-6 text-[15px] font-medium text-white transition-opacity hover:opacity-85 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:bg-white dark:text-black dark:focus-visible:ring-white/30"
        >
          {t(
            commandPaletteOpenLabelKey(preview),
            commandPaletteOpenFallback(preview),
          )}
        </button>
      }
    >
      {children}
    </BottomSheet>
  );
}
