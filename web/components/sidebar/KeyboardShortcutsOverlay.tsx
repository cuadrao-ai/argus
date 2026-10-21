"use client";

import { withViewportPortal } from "@/components/ui/withViewportPortal";

import { useEffect, useId, useRef, useState } from "react";
import { Keyboard, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useModalSurface } from "@/components/layout/useModalSurface";
import { workspaceShortcutKeys, workspaceShortcutMatchesQuery } from "@/lib/keyboard-shortcuts";
import { useChatWorkspace, useChatAvailable } from "@/components/chat/ChatWorkspace";
import {
  KEYBOARD_SHORTCUTS,
  keyboardShortcutDisplay,
  type KeyboardShortcutGroup,
  type KeyboardShortcutId,
} from "@/lib/keyboard-shortcuts";

type KeyboardShortcutsOverlayProps = {
  onClose: () => void;
};

function usesCommandKey(): boolean {
  if (typeof navigator === "undefined") return false;
  return /Mac|iPhone|iPad|iPod/.test(navigator.userAgent);
}

const HELP_GROUPS: ReadonlyArray<{
  id: Exclude<KeyboardShortcutGroup, "omnisearch">;
  className: string;
}> = [
  { id: "navigation", className: "" },
  { id: "chat", className: "" },
  { id: "quick_jump", className: "md:col-span-2" },
];

const CHAT_HELP_ORDER: readonly KeyboardShortcutId[] = [
  "new_chat",
  "rename_focused_chat",
  "archive_focused_chat",
  "toggle_read_focused_chat",
  "toggle_pin_focused_chat",
  "delete_focused_chat",
];

function shortcutsForHelpGroup(group: KeyboardShortcutGroup, chatAvailable: boolean) {
  const shortcuts = KEYBOARD_SHORTCUTS.filter(
    (shortcut) => shortcut.group === group && (chatAvailable || !shortcut.needsChat),
  );
  if (group !== "chat") return shortcuts;
  return [...shortcuts].sort(
    (left, right) =>
      CHAT_HELP_ORDER.indexOf(left.id) - CHAT_HELP_ORDER.indexOf(right.id),
  );
}

export function KeyboardShortcutsOverlaySurface({
  onClose,
}: KeyboardShortcutsOverlayProps) {
  const overlayId = useId();
  const modalRef = useRef<HTMLDivElement>(null);
  // Reachable from the drawer, so it owns Escape, focus, and system back.
  useModalSurface({ isOpen: true, overlayId, containerRef: modalRef, onDismiss: onClose });
  const { t } = useTranslation();
  const chatAvailable = useChatAvailable();
  const workspaceShortcuts = useChatWorkspace()?.keyboardShortcuts;
  const [query, setQuery] = useState("");
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [showCommandKey, setShowCommandKey] = useState(false);

  useEffect(() => {
    setShowCommandKey(usesCommandKey());
    closeButtonRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[130] flex items-center justify-center bg-black/25 p-4 backdrop-blur-sm dark:bg-black/60">
      <button
        tabIndex={-1}
        type="button"
        className="absolute inset-0 cursor-default"
        onClick={onClose}
        aria-label={t("keyboard_shortcuts.close", "Close keyboard shortcuts")}
      />
      <section
        ref={modalRef}
        className="relative max-h-[calc(100dvh-2rem)] w-full max-w-[860px] overflow-y-auto rounded-[18px] border border-black/10 bg-white p-5 text-black dark:border-white/10 dark:bg-[#1b1d20] dark:text-white md:p-6"
        role="dialog"
        aria-modal="true"
        aria-labelledby="argus-keyboard-shortcuts-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-black/[0.04] dark:bg-white/[0.08]">
              <Keyboard className="h-5 w-5 text-black/65 dark:text-white/70" />
            </div>
            <div>
              <h2
                id="argus-keyboard-shortcuts-title"
                className="font-display text-[18px] font-medium"
              >
                {t("keyboard_shortcuts.title", "Keyboard shortcuts")}
              </h2>
              {!workspaceShortcuts ? <p className="mt-0.5 text-[13px] leading-relaxed text-black/55 dark:text-white/55">
                {t(
                  "keyboard_shortcuts.description",
                  "Quick ways to move through Argus.",
                )}
              </p> : null}
            </div>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="-mr-1 -mt-1 rounded-full p-2 text-black/55 hover:bg-black/[0.05] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/20 dark:text-white/60 dark:hover:bg-white/[0.08] dark:focus-visible:ring-white/30"
            aria-label={t("keyboard_shortcuts.close", "Close keyboard shortcuts")}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {workspaceShortcuts ? <div className="mt-5">
          <input type="search" aria-label={t("common.search", "Search")} placeholder={t("common.search", "Search")} value={query} onChange={(event) => setQuery(event.target.value)} className="mb-4 min-h-11 w-full rounded-xl border border-black/15 bg-transparent px-3 text-[16px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)] dark:border-white/20" />
          <div className="divide-y divide-black/10 dark:divide-white/10">
            {workspaceShortcuts.filter((shortcut) => workspaceShortcutMatchesQuery(shortcut, showCommandKey, query)).map((shortcut) => <div key={shortcut.id} data-workspace-shortcut={shortcut.id} className="flex min-h-11 items-center justify-between gap-4 py-2 text-[14px]"><span>{shortcut.label}</span><span className="flex shrink-0 gap-1">{workspaceShortcutKeys(shortcut, showCommandKey).map((key) => <kbd key={key} className="rounded-md border border-black/10 bg-black/[0.035] px-2 py-1 text-[12px] dark:border-white/15 dark:bg-white/[0.08]">{key}</kbd>)}</span></div>)}
          </div>
        </div> : <div className="mt-6 grid grid-cols-1 gap-5 md:grid-cols-2">
          {HELP_GROUPS.map((group) => {
            const shortcuts = shortcutsForHelpGroup(group.id, chatAvailable);
            if (shortcuts.length === 0) return null;
            return (
              <div
                key={group.id}
                data-shortcut-group={group.id}
                className={group.className}
              >
                <p className="px-1 text-[11px] font-medium uppercase tracking-[0.12em] text-black/45 dark:text-white/45">
                  {t(
                    `keyboard_shortcuts.groups.${group.id}`,
                    group.id === "chat"
                      ? "Chat"
                      : group.id === "quick_jump"
                        ? "Quick jump"
                        : "Navigation",
                  )}
                </p>
                <div className="mt-2 overflow-hidden rounded-[14px] border border-black/[0.08] dark:border-white/[0.1]">
                  {shortcuts.map((shortcut, index) => {
                    const keys = keyboardShortcutDisplay(
                      shortcut.id,
                      showCommandKey,
                    );
                    return (
                      <div
                        key={shortcut.id}
                        className={`flex min-h-11 items-center justify-between gap-4 px-3.5 py-2.5 ${
                          index > 0 ? "border-t border-black/[0.06] dark:border-white/[0.08]" : ""
                        }`}
                      >
                        <span className="min-w-0 text-[14px] text-black/75 dark:text-white/80">
                          {t(shortcut.labelKey, {
                            defaultValue: shortcut.defaultLabel,
                          }).trim() || shortcut.defaultLabel}
                        </span>
                        <span className="flex shrink-0 items-center gap-1.5" aria-hidden="true">
                          {keys.map((key) => (
                            <kbd
                              key={key}
                              className="rounded-md border border-black/10 bg-black/[0.035] px-2 py-1 font-sans text-[12px] font-medium text-black/65 dark:border-white/15 dark:bg-white/[0.08] dark:text-white/75"
                            >
                              {key}
                            </kbd>
                          ))}
                        </span>
                      </div>
                    );
                  })}
                </div>
                {group.id === "quick_jump" ? (
                  <p className="mt-2 px-1 text-[12px] leading-relaxed text-black/50 dark:text-white/55">
                    {t(
                      "keyboard_shortcuts.quick_jump_description",
                      "Hold the modifier keys to reveal numbers on visible items.",
                    )}
                  </p>
                ) : null}
              </div>
            );
          })}
        </div>}
      </section>
    </div>
  );
}

export default withViewportPortal(KeyboardShortcutsOverlaySurface);
