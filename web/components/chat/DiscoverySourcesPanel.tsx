"use client";

import { withViewportPortal } from "@/components/ui/withViewportPortal";

import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { BottomSheet } from "@/components/ui/BottomSheet";
import ResearchSourcesList from "./ResearchSourcesList";
export { formattedSourceDate } from "./ResearchSourcesList";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { researchSourcesDisplay } from "@/lib/research-sources-display";
import type { DiscoverySidecar } from "./types";

/** Everything the panel renders: sources and when they were retrieved. */
export type SourcesPanelSidecar = Pick<
  DiscoverySidecar,
  "sources" | "retrieved_at"
>;

type DiscoverySourcesPanelProps = {
  onClose: () => void;
  sidecar: SourcesPanelSidecar;
  /** Opens scrolled to this source, so a row chip lands on its evidence. */
  anchorIndex?: number | null;
  /**
   * The turn withheld its answer: these are the pages Argus read and could
   * not verify it with, framed as where Argus looked. Decided by the
   * backend's typed degraded code, never by reading the sources.
   */
  withheld?: boolean;
};

/**
 * Evidence trail for one discovery turn. A pure renderer of the persisted
 * `metadata.discovery` sidecar — it never re-queries. Links open the publisher
 * in a new tab, and the visible domain always comes from the href being opened
 * so an untrusted provider title cannot disguise the destination.
 */
export function DiscoverySourcesPanelSurface({
  onClose,
  sidecar,
  anchorIndex = null,
  withheld = false,
}: DiscoverySourcesPanelProps) {
  const { t, i18n } = useTranslation();
  // The panel line, not the sidebar's: at tablet width the dossier beside
  // this was already a sheet while this was not.
  const { isBelowDesktop } = useResponsiveLayout();
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (isBelowDesktop) {
      // BottomSheet owns focus, Escape, and focus restore for the sheet form.
      panelRef.current
        ?.querySelector(`[data-source-index="${anchorIndex}"]`)
        ?.scrollIntoView({ block: "start" });
      return;
    }
    restoreFocusRef.current = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    panel?.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    if (anchorIndex !== null) {
      panel
        ?.querySelector(`[data-source-index="${anchorIndex}"]`)
        ?.scrollIntoView({ block: "start" });
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const focusable = panel.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown, true);
    return () => {
      document.removeEventListener("keydown", handleKeyDown, true);
      restoreFocusRef.current?.focus?.();
    };
  }, [onClose, anchorIndex, isBelowDesktop]);

  const display = researchSourcesDisplay(withheld);
  const title = t(display.titleKey, { defaultValue: display.titleFallback });
  const note = t(display.noteKey, { defaultValue: display.noteFallback });
  const closeLabel = t("chat.discovery_results.sources_panel_close", {
    defaultValue: "Close sources",
  });

  const sourceList = <ResearchSourcesList sources={sidecar.sources} locale={i18n.language} t={t} anchorIndex={anchorIndex} />;

  // Below the mobile threshold the evidence trail is a sheet, not a side panel.
  if (isBelowDesktop) {
    return (
      <BottomSheet
        isOpen
        snaps={["half", "full"]}
        title={title}
        description={note}
        closeLabel={closeLabel}
        onClose={onClose}
      >
        <div ref={panelRef} className="flex h-full flex-col">
          {sourceList}
        </div>
      </BottomSheet>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="presentation">
      <div
        aria-hidden="true"
        onClick={onClose}
        className="absolute inset-0 bg-black/25 dark:bg-black/50"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="relative flex max-h-full w-full flex-col self-end overflow-hidden rounded-t-2xl border border-black/10 bg-white shadow-none dark:border-white/10 dark:bg-[#1d2023] sm:max-w-[420px] sm:self-stretch sm:rounded-none sm:rounded-s-2xl sm:border-y-0 sm:border-e-0"
      >
        <div className="flex items-start justify-between gap-3 border-b border-black/8 px-4 py-3 dark:border-white/8">
          <div className="min-w-0">
            <p className="text-[14px] font-medium leading-[1.45] tracking-tight text-black dark:text-white">
              {title}
            </p>
            <p className="mt-0.5 text-[12px] leading-[1.5] text-black/50 dark:text-white/50">
              {note}
            </p>
          </div>
          <button
            type="button"
            data-autofocus
            onClick={onClose}
            aria-label={closeLabel}
            className="-me-2 -mt-2 inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-full text-black/60 transition-colors hover:bg-black/5 hover:text-black dark:text-white/60 dark:hover:bg-white/10 dark:hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {sourceList}
      </div>
    </div>
  );
}

export default withViewportPortal(DiscoverySourcesPanelSurface);
