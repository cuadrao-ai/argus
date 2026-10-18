"use client";

import { Bell, Inbox, LayoutGrid, ReceiptText } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";
import { useBusiness } from "./BusinessWorkspace";
import { BUSINESS_SECTIONS } from "./business-keyboard-shortcuts";
import { inboxCount } from "./inbox-count";
const ICONS = [LayoutGrid, Inbox, ReceiptText, Bell];

export default function BusinessBottomTabs({ shell }: { shell: ChatShellBridge }) {
  const { t } = useTranslation();
  const { panel, openPanel, records } = useBusiness();
  const count = inboxCount(records);
  return <nav aria-label={t("business.nav.label", "Business")} data-testid="business-bottom-tabs" className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t border-black/10 bg-[var(--cuadrao-cream)] pb-[env(safe-area-inset-bottom)] dark:border-white/15 dark:bg-[#141517]">
    {BUSINESS_SECTIONS.map((section, index) => {
      const Icon = ICONS[index];
      const selected = shell.currentView === "workspace" && (panel.kind === section || section === "inbox" && ["receipt", "draft"].includes(panel.kind) || section === "expenses" && panel.kind === "expense");
      return <button key={section} type="button" aria-current={selected ? "page" : undefined} onClick={() => openPanel({ kind: section })} className={`flex h-16 min-w-11 flex-col items-center justify-center gap-1 rounded-lg px-1 text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)] ${selected ? "font-medium text-[var(--cuadrao-green)] dark:text-white" : "text-black/65 dark:text-white/65"}`}><span className="relative"><Icon className="h-5 w-5" aria-hidden="true" />{section === "inbox" && count !== null && count > 0 ? <span className="absolute -right-4 -top-2 rounded-full bg-[var(--cuadrao-green)] px-1 text-[10px] text-white">{count}</span> : null}</span><span>{t(`business.nav.${section}`)}</span></button>;
    })}
  </nav>;
}
