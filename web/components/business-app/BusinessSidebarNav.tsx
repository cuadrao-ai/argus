"use client";

import { useEffect, useState } from "react";
import { quickJumpHintDisplay } from "@/lib/keyboard-shortcuts";
import { House, Inbox, ReceiptText } from "lucide-react";
import { useTranslation } from "react-i18next";
import SidebarNavButton from "@/components/sidebar/SidebarNavButton";
import { CuadraoMark } from "@/components/CuadraoMark";
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

/** The foot of the rail: the product's own mark, quiet, so the business above stays the one name that reads first. */
export function BusinessSidebarFooter({ shell }: { shell: ChatShellBridge }) {
  return (
    // The mark keeps one place, centred on the closed rail; the word fades and the rail's width clips it.
    <div data-testid="sidebar-brand" className="flex items-center gap-2 overflow-hidden pb-3 pl-3 pt-2">
      <CuadraoMark size={20} className="h-5 w-5 shrink-0 opacity-70" />
      <span aria-hidden={shell.sidebarCollapsed || undefined} className={`whitespace-nowrap font-display text-[15px] font-medium tracking-tight text-[#56635e] transition-opacity duration-150 ease-out motion-reduce:transition-none dark:text-white/60 ${shell.sidebarCollapsed ? "opacity-0" : "opacity-100"}`}>cuadrao</span>
    </div>
  );
}
