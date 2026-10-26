"use client";

import { useEffect, useState } from "react";
import { FileText } from "lucide-react";
import { quickJumpHintDisplay } from "@/lib/keyboard-shortcuts";
import { NAV_GLYPHS, navGlyph } from "./nav-glyphs";
import { useTranslation } from "react-i18next";
import SidebarNavButton from "@/components/sidebar/SidebarNavButton";
import { CuadraoMark } from "@/components/CuadraoMark";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";
import { useBusiness, type BusinessPanelState } from "./BusinessWorkspace";
import { inboxCount as countInbox, porIgualarCount } from "./inbox-count";
import { useIgualarEnabled } from "./transacciones/transacciones-gate";
import { recordList } from "./record-tray";

export default function BusinessSidebarNav({ shell }: { shell: ChatShellBridge }) {
  const { t } = useTranslation();
  const [command, setCommand] = useState(false);
  useEffect(() => { setCommand(/Mac|iPhone|iPad|iPod/.test(navigator.userAgent)); }, []);
  const { panel, openPanel, records } = useBusiness();
  const inboxCount = countInbox(records);
  // Only beside the screen that lists them: with igualar off here, Transacciones shows no Por igualar.
  const igualarCount = useIgualarEnabled() ? porIgualarCount(records) : null;
  const isActive = (kind: BusinessPanelState["kind"]) =>
    shell.currentView === "workspace" &&
    (panel.kind === kind || recordList(panel) === kind);
  const count = (value: number | null, testId = "business-inbox-count") =>
    value !== null && value > 0 && !shell.sidebarCollapsed ? (
      <span data-testid={testId} className="rounded-mark bg-black/5 px-2 py-0.5 text-[14px] tabular-nums text-black/60 dark:bg-white/10 dark:text-white/60">
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
        glyph={navGlyph(NAV_GLYPHS.overview)}
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
        glyph={navGlyph(NAV_GLYPHS.inbox)}
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
        glyph={navGlyph(NAV_GLYPHS.transactions)}
        label={t("business.nav.transactions", "Transactions")}
        active={isActive("transactions")}
        shortcutHint={quickJumpHintDisplay(3, command)}
        shortcutOnInteraction={!shell.isBelowTablet}
        collapsed={shell.sidebarCollapsed}
        onClick={() => openPanel({ kind: "transactions" })}
        trailing={count(igualarCount, "business-igualar-count")}
        iconSize={20}
        variant="business"
      />
      {process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true" ? <SidebarNavButton
        icon={FileText} label={t("business.invoicing_preview.title")}
        active={isActive("invoicing")} collapsed={shell.sidebarCollapsed}
        onClick={() => openPanel({ kind: "invoicing" })} iconSize={20} variant="business"
      /> : null}
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
