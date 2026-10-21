"use client";

import { Tooltip } from "@/components/ui/Tooltip";
import { KeyboardShortcutKeycap } from "@/components/keyboard/KeyboardShortcutKeycap";
import { ConversationActivityIndicator } from "@/components/chat/ConversationActivityIndicator";
import type { ConversationActivityPresentation } from "@/lib/conversation-activity-state";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

const BUSINESS_ROW_HOVER = "hover:bg-[#e3ebe1]/50";

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
  /** Business rail row: 44px, Inter 14, the approved green fill when active. */
  variant?: "business";
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
  variant,
  activityPresentation = "none",
}: SidebarNavButtonProps) {
  const business = variant === "business";
  const overlay = activityPresentation !== "none" ? (
    <span
      data-sidebar-activity-overlay="true"
      className={`pointer-events-none absolute ${business ? "-right-1.5 -top-1.5" : "right-1 top-1"}`}
    >
      <ConversationActivityIndicator
        presentation={activityPresentation}
        compact
      />
    </span>
  ) : null;
  const trailingSlot = !collapsed && (shortcutHint || trailing) ? (
    <div className={`ml-auto flex h-[22px] shrink-0 items-center justify-end ${business ? "" : "pr-4"}`}>
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
  ) : null;

  const button = business ? (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      data-sidebar-row="business"
      className={`group flex h-11 shrink-0 items-center gap-3 rounded-[12px] px-3 ${collapsed ? "w-11" : "w-full"} text-left font-sans text-[14px] leading-5 transition-colors duration-200 ${
        active
          ? "bg-[#e3ebe1] font-medium text-[#2f5a49] dark:bg-white/10 dark:text-white"
          : `${BUSINESS_ROW_HOVER} font-normal text-[#172b26] dark:text-white/80 dark:hover:bg-white/5`
      } ${className}`}
    >
      <span className="relative flex h-5 w-5 shrink-0 items-center justify-center">
        <Icon
          aria-hidden="true"
          strokeWidth={2}
          style={{ width: iconSize, height: iconSize }}
          className={active ? "text-[#2f5a49] dark:text-white" : "text-[#56635e] dark:text-white/60"}
        />
        {overlay}
      </span>
      <span className={collapsed ? "sr-only" : "min-w-0 truncate"}>{label}</span>
      {trailingSlot}
    </button>
  ) : (
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
          strokeWidth={2}
          style={{ width: iconSize, height: iconSize }}
          className="text-black/60 transition-transform duration-150 ease-out group-hover:scale-[1.06] group-hover:text-black dark:text-white/60 dark:group-hover:text-white"
        />
        {overlay}
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
      {trailingSlot}
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
