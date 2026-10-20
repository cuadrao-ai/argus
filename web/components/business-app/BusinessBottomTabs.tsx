"use client";

import { Bell, House, Inbox, ReceiptText } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";
import { useBusiness } from "./BusinessWorkspace";
import { BUSINESS_SECTIONS } from "./business-keyboard-shortcuts";
import { inboxCount } from "./inbox-count";
import { recordList } from "./record-tray";
const ICONS = [House, Inbox, ReceiptText, Bell];

export default function BusinessBottomTabs({ shell }: { shell: ChatShellBridge }) {
  const { t } = useTranslation();
  const { panel, openPanel, records } = useBusiness();
  const count = inboxCount(records);
  return <nav aria-label={t("business.nav.label", "Business")} data-testid="business-bottom-tabs" className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t border-black/10 bg-[var(--cuadrao-cream)] pb-[env(safe-area-inset-bottom)] dark:border-white/15 dark:bg-[#141517]">
    {BUSINESS_SECTIONS.map((section, index) => {
      const Icon = ICONS[index];
      const selected = shell.currentView === "workspace" && (panel.kind === section || recordList(panel) === section);
      return <button key={section} type="button" aria-current={selected ? "page" : undefined} onClick={() => openPanel({ kind: section })} className={`flex min-h-16 min-w-11 flex-col items-center justify-center gap-1 px-1 text-[12px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] ${selected ? "font-medium text-[var(--cuadrao-green)] dark:text-white" : "text-black/65 dark:text-white/65"}`}><span className="relative"><Icon className="h-5 w-5" strokeWidth={2} aria-hidden="true" />{section === "inbox" && count !== null && count > 0 ? <span className="absolute -right-4 -top-2 rounded-full bg-[var(--cuadrao-green)] px-1 text-[10px] text-white">{count}</span> : null}</span><span className="max-w-full whitespace-normal break-words text-center leading-4">{t(`business.nav.${section}`)}</span></button>;
    })}
  </nav>;
}
