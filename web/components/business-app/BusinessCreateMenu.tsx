"use client";

import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@/components/ui/Tooltip";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";
import ActionMenu from "./ActionMenu";
import { useBusiness } from "./BusinessWorkspace";

/** + Create: at the sidebar foot on desktop, a header button on phones. */
export default function BusinessCreateMenu({
  shell,
  compact = false,
}: {
  shell: ChatShellBridge;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const { actions } = useBusiness();
  const label = t("business.create.label", "Create");

  if (compact) {
    return (
      <ActionMenu
        actions={actions.create}
        label={label}
        placement="below-end"
        renderTrigger={({ ref, open, toggle, menuId }) => (
          <button
            ref={ref}
            type="button"
            aria-haspopup="menu"
            aria-expanded={open}
            aria-controls={open ? menuId : undefined}
            data-testid="business-create-compact"
            onClick={toggle}
            className="flex h-11 min-w-11 shrink-0 items-center justify-center gap-1.5 rounded-full pl-3 pr-4 font-display text-[15px] font-medium tracking-tight text-black transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 active:scale-95 dark:text-white dark:hover:bg-white/5 dark:focus-visible:ring-white/30"
          >
            <Plus className="h-5 w-5 text-black/70 dark:text-white/70" aria-hidden="true" />
            {label}
          </button>
        )}
      />
    );
  }

  const collapsed = shell.sidebarCollapsed;
  return (
    <ActionMenu
      actions={actions.create}
      label={label}
      placement="above-start"
      portal={!shell.isBelowTablet}
      renderTrigger={({ ref, open, toggle, menuId }) => {
        const button = (
          <button
            ref={ref}
            type="button"
            aria-label={collapsed ? label : undefined}
            aria-haspopup="menu"
            aria-expanded={open}
            aria-controls={open ? menuId : undefined}
            data-testid="business-create"
            onClick={toggle}
            className={`group flex h-11 w-full items-center rounded-[14px] transition-colors duration-200 hover:bg-black/5 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:hover:bg-white/5 ${
              open ? "bg-black/5 dark:bg-white/5" : ""
            }`}
          >
            {/* Same 44px icon cell and 20px glyph as every other sidebar row. */}
            <span className="flex h-11 w-11 flex-shrink-0 items-center justify-center">
              <Plus className="h-5 w-5 text-black/60 transition-transform duration-150 ease-out group-hover:scale-[1.06] group-hover:text-black dark:text-white/60 dark:group-hover:text-white" />
            </span>
            {collapsed ? null : (
              <span className="ml-1 whitespace-nowrap font-display text-[15px] font-medium tracking-tight text-black dark:text-white">
                {label}
              </span>
            )}
          </button>
        );
        return collapsed ? (
          // The tooltip attaches its own ref to its child, so the button keeps
          // the menu's ref inside a wrapper.
          <Tooltip content={label} side="right" delay={150}>
            <span className="inline-flex">{button}</span>
          </Tooltip>
        ) : (
          button
        );
      }}
    />
  );
}
