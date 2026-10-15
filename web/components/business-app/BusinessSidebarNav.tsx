"use client";

import { Bell, Inbox, LayoutGrid, ReceiptText, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import SidebarNavButton from "@/components/sidebar/SidebarNavButton";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";
import { useBusiness, type BusinessPanelState } from "./BusinessWorkspace";
import { inboxCount as countInbox } from "./BusinessInboxPanel";

export default function BusinessSidebarNav({ shell }: { shell: ChatShellBridge }) {
  const { t } = useTranslation();
  const { panel, openPanel, records } = useBusiness();
  const inboxCount = countInbox(records);
  const isActive = (kind: BusinessPanelState["kind"]) =>
    shell.currentView === "workspace" &&
    (panel.kind === kind || (kind === "inbox" && panel.kind === "receipt") || (kind === "expenses" && panel.kind === "expense"));
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
      className="mt-2 border-t border-black/5 pt-2 dark:border-white/5"
    >
      <SidebarNavButton
        icon={LayoutGrid}
        label={t("business.nav.overview", "Overview")}
        active={isActive("overview")}
        collapsed={shell.sidebarCollapsed}
        onClick={() => openPanel({ kind: "overview" })}
        iconSize={20}
      />
      <SidebarNavButton
        icon={Inbox}
        label={t("business.nav.inbox", "Inbox")}
        active={isActive("inbox")}
        collapsed={shell.sidebarCollapsed}
        onClick={() => openPanel({ kind: "inbox" })}
        trailing={count(inboxCount)}
        activityPresentation={records.receiptActivity?.presentation === "working" ? "working" : records.receiptActivity?.presentation === "unread" ? "new_activity" : "none"}
        iconSize={20}
      />
      <SidebarNavButton
        icon={ReceiptText}
        label={t("business.nav.expenses", "Expenses")}
        active={isActive("expenses")}
        collapsed={shell.sidebarCollapsed}
        onClick={() => openPanel({ kind: "expenses" })}
        iconSize={20}
      />
      <SidebarNavButton
        icon={Bell}
        label={t("business.nav.updates", "Updates")}
        active={isActive("updates")}
        collapsed={shell.sidebarCollapsed}
        onClick={() => openPanel({ kind: "updates" })}
        iconSize={20}
      />
      <SidebarNavButton
        icon={Users}
        label={t("business_access.nav", "Access")}
        active={isActive("access")}
        collapsed={shell.sidebarCollapsed}
        onClick={() => openPanel({ kind: "access" })}
        iconSize={20}
      />
    </nav>
  );
}
