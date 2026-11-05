"use client";

import { useId, useRef, useState } from "react";
import { Edit2, MoreVertical } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@/components/ui/Tooltip";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import pointerAffordances from "../pointerAffordances.module.css";

export type CommandPaletteRowAction = {
  id: "rename" | "archive" | "delete" | "open_source";
  /** Shown to the eye: short, and the same word Recents uses. */
  label: string;
  /**
   * Read aloud: names the object the row acts on, which the visible label can
   * leave to context but an icon-only control cannot.
   */
  accessibleName: string;
  icon: typeof Edit2;
  destructive?: boolean;
  disabled?: boolean;
  onSelect: () => void;
};

/**
 * Row actions for an Omnisearch result.
 *
 * Hover reveal is a pointer affordance, so touch gets an always-visible
 * trailing three-dot instead. Not long press: it has no visual affordance and
 * both mobile platforms moved to explicit controls for exactly this reason.
 */
export default function CommandPaletteRowActions({
  actions,
  variant,
}: {
  actions: CommandPaletteRowAction[];
  variant: "hover" | "menu";
}) {
  const { t } = useTranslation();
  const overlayId = useId();
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Escape and outside presses arrive from the registry, and only while this
  // menu is the topmost layer. It used to install both itself and lean on
  // stopPropagation, which cannot stop a sibling listener on the same target.
  useOverlayLayer({
    isOpen,
    overlayId,
    containerRef,
    onEscape: () => {
      setIsOpen(false);
      triggerRef.current?.focus();
    },
    onOutsidePointerDown: () => setIsOpen(false),
  });

  if (actions.length === 0) return null;

  const hoverActions = (
    <div
      className={`argus-row-hover-actions absolute bottom-2 right-2 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 ${pointerAffordances.finePointerActions}`}
      data-row-action
    >
      {actions.map((action) => (
        <Tooltip key={action.id} content={action.label} side="top">
          <button
            type="button"
            disabled={action.disabled}
            onClick={(event) => {
              event.stopPropagation();
              action.onSelect();
            }}
            className={
              action.destructive
                ? "rounded-full p-1.5 text-[#d66d75]/75 transition-colors hover:bg-[#d66d75]/10 hover:text-[#d66d75]"
                : "rounded-full p-1.5 text-black/45 transition-colors hover:bg-black/5 hover:text-black disabled:cursor-not-allowed disabled:opacity-50 dark:text-white/45 dark:hover:bg-white/10 dark:hover:text-white"
            }
            aria-label={action.accessibleName}
          >
            <action.icon className="h-3.5 w-3.5" />
          </button>
        </Tooltip>
      ))}
    </div>
  );

  const menuActions = (
    <div
      ref={containerRef}
      /*
       * Raised while open, because the rows below this one are positioned too
       * and paint after it. Without this the next row's date chip and its own
       * three-dot drew straight through the open menu, and the lower items were
       * unclickable: the menu's own z-index cannot help, since the thing
       * covering it is a sibling of the row rather than a sibling of the menu.
       */
      className={`absolute right-0 top-1/2 -translate-y-1/2 items-center ${
        isOpen ? "z-20" : ""
      } ${variant === "hover" ? pointerAffordances.touchSafeActions : "flex"}`}
      data-row-action
    >
      <button
        ref={triggerRef}
        type="button"
        data-testid="command-palette-row-menu"
        onClick={(event) => {
          event.stopPropagation();
          setIsOpen((open) => !open);
        }}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label={t("command_palette.row_actions", "Conversation actions")}
        className="flex h-11 w-11 items-center justify-center rounded-full text-black/45 transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:text-white/45 dark:hover:bg-white/10 dark:focus-visible:ring-white/30"
      >
        <MoreVertical className="h-4 w-4" aria-hidden="true" />
      </button>
      {isOpen ? (
        <div
          role="menu"
          aria-label={t("command_palette.row_actions", "Conversation actions")}
          className="absolute right-0 top-full z-10 mt-1 w-[min(220px,calc(100vw-3rem))] overflow-hidden rounded-[14px] border border-black/8 bg-white py-1 shadow-[0_16px_44px_rgba(15,23,42,0.16)] dark:border-white/10 dark:bg-[#1f2225] dark:shadow-[0_16px_44px_rgba(0,0,0,0.4)]"
        >
          {actions.map((action) => (
            <button
              key={action.id}
              type="button"
              role="menuitem"
              aria-label={action.accessibleName}
              disabled={action.disabled}
              onClick={(event) => {
                event.stopPropagation();
                setIsOpen(false);
                action.onSelect();
              }}
              className={`flex min-h-11 w-full items-center gap-3 px-4 text-left text-[15px] font-medium transition-colors disabled:opacity-50 ${
                action.destructive
                  ? "text-[#d66d75] hover:bg-[#d66d75]/10"
                  : "text-black hover:bg-black/5 dark:text-white dark:hover:bg-white/5"
              }`}
            >
              <action.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              {action.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );

  if (variant === "hover") {
    return (
      <>
        {hoverActions}
        {menuActions}
      </>
    );
  }

  return menuActions;
}
