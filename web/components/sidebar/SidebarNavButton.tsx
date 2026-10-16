"use client";

import { Tooltip } from "@/components/ui/Tooltip";
import { KeyboardShortcutKeycap } from "@/components/keyboard/KeyboardShortcutKeycap";
import { ConversationActivityIndicator } from "@/components/chat/ConversationActivityIndicator";
import type { ConversationActivityPresentation } from "@/lib/conversation-activity-state";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

type SidebarNavButtonProps = {
  /** Lucide icon component */
  icon: LucideIcon;
  /** Button label (shown when expanded, used as tooltip when collapsed) */
  label: string;
  /** Whether this nav item is currently active */
  active?: boolean;
  /** Whether the sidebar is collapsed (icon-only mode) */
  collapsed?: boolean;
  /** Click handler */
  onClick: () => void;
  /** Optional extra class names */
  className?: string;
  /** Optional right-side content (e.g. chevron for accordion) */
  trailing?: ReactNode;
  /** A compact keyboard hint shown while the primary modifier is held */
  shortcutHint?: string;
  /** Whether the keyboard hint is currently visible */
  showShortcutHint?: boolean;
  shortcutOnInteraction?: boolean;
  /** Icon size override (default: 22) */
  iconSize?: number;
  /** Optional aggregate conversation activity rendered over the icon */
  activityPresentation?: ConversationActivityPresentation;
};

/**
 * Reusable sidebar navigation button.
 *
 * Typography: Space Grotesk (font-display) per DESIGN.md Nav/UI role.
 * When collapsed: shows only the icon with a premium custom tooltip.
 * When expanded: shows icon + label, with optional trailing element.
 */
export default function SidebarNavButton({
  icon: Icon,
  label,
  active = false,
  collapsed = false,
  onClick,
  className = "",
  trailing,
  shortcutHint,
  showShortcutHint = false,
  shortcutOnInteraction = false,
  iconSize = 22,
  activityPresentation = "none",
}: SidebarNavButtonProps) {
  const button = (
    <button
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={`group mb-1 flex h-11 w-full items-center rounded-[14px] transition-colors duration-200 ${
        active
          ? "bg-black/5 dark:bg-white/5"
          : "hover:bg-black/5 dark:hover:bg-white/5"
      } ${className}`}
    >
      {/* Icon container: fixed 44px square, always centered */}
      <div className="relative flex h-11 w-11 flex-shrink-0 items-center justify-center">
        <Icon
          style={{ width: iconSize, height: iconSize }}
          className="text-black/60 transition-transform duration-150 ease-out group-hover:scale-[1.06] group-hover:text-black dark:text-white/60 dark:group-hover:text-white"
        />
        {activityPresentation !== "none" ? (
          <span
            data-sidebar-activity-overlay="true"
            className="pointer-events-none absolute right-1 top-1"
          >
            <ConversationActivityIndicator
              presentation={activityPresentation}
              compact
            />
          </span>
        ) : null}
      </div>
      {/* Label: font-display (Space Grotesk) per DESIGN.md Nav/UI role */}
      <span
        className={`ml-1 whitespace-nowrap font-display text-[15px] font-medium tracking-tight text-black transition-[opacity,max-width] duration-300 ease-in-out dark:text-white ${
          collapsed
            ? "pointer-events-none max-w-0 overflow-hidden opacity-0"
            : "max-w-[180px] opacity-100"
        }`}
      >
        {label}
      </span>
      {!collapsed && (shortcutHint || trailing) && (
        <div className="ml-auto flex h-[22px] shrink-0 items-center justify-end pr-4">
          {shortcutOnInteraction && shortcutHint ? <>
            <span className="group-hover:hidden group-focus-visible:hidden">{trailing}</span>
            <KeyboardShortcutKeycap className="hidden group-hover:inline-flex group-focus-visible:inline-flex">{shortcutHint}</KeyboardShortcutKeycap>
          </> : showShortcutHint && shortcutHint ? (
            <KeyboardShortcutKeycap className="select-none">
              {shortcutHint}
            </KeyboardShortcutKeycap>
          ) : (
            trailing
          )}
        </div>
      )}
    </button>
  );

  if (collapsed) {
    return (
      <Tooltip content={shortcutOnInteraction && shortcutHint ? `${label} · ${shortcutHint}` : label} side="right" delay={150}>
        {button}
      </Tooltip>
    );
  }

  return button;
}
