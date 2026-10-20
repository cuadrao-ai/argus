"use client";

import { useEffect, useState } from "react";
import { quickJumpHintDisplay } from "@/lib/keyboard-shortcuts";
import { House, Inbox, ReceiptText, UsersRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import SidebarNavButton from "@/components/sidebar/SidebarNavButton";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";
import { useBusiness, type BusinessPanelState } from "./BusinessWorkspace";
import { inboxCount as countInbox } from "./inbox-count";
import { recordList } from "./record-tray";

export default function BusinessSidebarNav({ shell }: { shell: ChatShellBridge }) {
  const { t } = useTranslation();
  const [command, setCommand] = useState(false);
  useEffect(() => { setCommand(/Mac|iPhone|iPad|iPod/.test(navigator.userAgent)); }, []);
  const { panel, openPanel, records } = useBusiness();
  const inboxCount = countInbox(records);
  const isActive = (kind: BusinessPanelState["kind"]) =>
    shell.currentView === "workspace" &&
    (panel.kind === kind || recordList(panel) === kind);
  const count = (value: number | null) =>
    value !== null && value > 0 && !shell.sidebarCollapsed ? (
      <span data-testid="business-inbox-count" className="rounded-full bg-black/5 px-2 py-0.5 text-[12px] tabular-nums text-black/60 dark:bg-white/10 dark:text-white/60">
        {value}
      </span>
    ) : null;

  return (
    <nav
      aria-label={t("business.nav.label", "Business")}
      data-testid="business-sidebar-nav"
      className="flex flex-col"
    >
      <SidebarNavButton
        icon={House}
        label={t("business.nav.overview", "Overview")}
        active={isActive("overview")}
        shortcutHint={quickJumpHintDisplay(1, command)}
        shortcutOnInteraction={!shell.isBelowTablet}
        collapsed={shell.sidebarCollapsed}
        onClick={() => openPanel({ kind: "overview" })}
        iconSize={20}
        variant="business"
      />
      <SidebarNavButton
        icon={Inbox}
        label={t("business.nav.inbox", "Inbox")}
        active={isActive("inbox")}
        shortcutHint={quickJumpHintDisplay(2, command)}
        shortcutOnInteraction={!shell.isBelowTablet}
        collapsed={shell.sidebarCollapsed}
        onClick={() => openPanel({ kind: "inbox" })}
        trailing={count(inboxCount)}
        activityPresentation={records.receiptActivity?.presentation === "working" ? "working" : records.receiptActivity?.presentation === "unread" ? "new_activity" : "none"}
        iconSize={20}
        variant="business"
      />
      <SidebarNavButton
        icon={ReceiptText}
        label={t("business.nav.expenses", "Expenses")}
        active={isActive("expenses")}
        shortcutHint={quickJumpHintDisplay(3, command)}
        shortcutOnInteraction={!shell.isBelowTablet}
        collapsed={shell.sidebarCollapsed}
        onClick={() => openPanel({ kind: "expenses" })}
        iconSize={20}
        variant="business"
      />
    </nav>
  );
}

/** Acceso sits above Ajustes at the foot of the rail, in the same row shape. */
export function BusinessSidebarFooter({ shell }: { shell: ChatShellBridge }) {
  const { t } = useTranslation();
  const { panel, openPanel } = useBusiness();
  return (
    <SidebarNavButton
      icon={UsersRound}
      label={t("business_access.nav", "Access")}
      active={shell.currentView === "workspace" && panel.kind === "access"}
      collapsed={shell.sidebarCollapsed}
      onClick={() => openPanel({ kind: "access" })}
      iconSize={20}
      variant="business"
    />
  );
}
