"use client";

import { Briefcase, ChevronRight, Inbox, Info } from "lucide-react";
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { formatRelativeTime, isRelativeTimestamp } from "@/components/business-app/business-format";
import { CHANNEL_ICON } from "@/components/business-app/foundation/channel-icons";
import { Tooltip } from "@/components/ui/Tooltip";
import { formatRnc } from "@/lib/rnc-status";
import type { WhatsAppLinkStatus } from "@/lib/whatsapp-link-api";

const muted = "text-sm leading-5 text-[#56635e] dark:text-white/70";
const key = (name: string) => `settings.whatsapp.${name}`;

export function HeldFiles({ count }: { count: number }) {
  const { t } = useTranslation();
  const title = t(key("held_title"));
  return (
    <section aria-label={title} className="flex min-h-14 items-center gap-3 rounded-surface border border-dashed border-[#A39E90] py-2 pr-3.5 pl-4 dark:border-white/30">
      <Inbox size={18} aria-hidden="true" className="shrink-0 text-[#56635e] dark:text-white/70" />
      <div className="min-w-0 flex-1">
        <p>{title}</p>
        {count > 0 && <p className={muted}>{t(key("held_help"))}</p>}
      </div>
      <span className="inline-flex h-[22px] items-center rounded bg-[#f2e8c9] px-[7px] text-[13px] leading-none font-medium text-[#735c14] tabular-nums dark:bg-[#f6e7c1]/14 dark:text-[#f6e7c1]">{count}</span>
      <ChevronRight size={18} aria-hidden="true" className="shrink-0 text-[#56635e] dark:text-white/70" />
    </section>
  );
}

export function WhatsAppLinkedDetails({ status, confirming }: { status: WhatsAppLinkStatus; confirming: boolean }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage || i18n.language;
  const now = new Date();
  const numberLabel = useRef<HTMLHeadingElement>(null);
  const stamp = formatRelativeTime(status.linked_at, locale, now);
  const WhatsApp = CHANNEL_ICON.whatsapp;
  const receivingTitle = t(key("receiving_title"));
  return <>
    <section className="flex items-center gap-3.5 rounded-surface bg-[#F7F5EE] p-4 dark:bg-[#1f2225]">
      <span className="grid size-11 shrink-0 place-items-center"><WhatsApp size={24} aria-hidden="true" /></span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <h3 ref={numberLabel} className="text-base leading-6 font-medium tabular-nums">{t(key("linked"), { last4: status.last4 })}</h3>
          {!confirming && <Tooltip explanation labelRef={numberLabel} side="bottom" content={t(key("reading_info"))}>
            <button type="button" aria-label={t(key("reading_info_label"))} className="relative -my-2.5 -ml-2.5 grid size-11 shrink-0 place-items-center rounded-full text-[#56635e] dark:text-white/70">
              <Info size={24} aria-hidden="true" />
            </button>
          </Tooltip>}
        </div>
        {status.linked_at && stamp && <time dateTime={status.linked_at} className={`block ${muted}`}>
          {isRelativeTimestamp(status.linked_at, now)
            ? t(key("linked_relative"), { relativeTime: stamp })
            : t(key("linked_date"), { date: locale.startsWith("es") ? stamp.toLocaleLowerCase(locale) : stamp })}
        </time>}
      </div>
    </section>
    <HeldFiles count={status.held_count} />
    <section className="space-y-2">
      <div>
        <h3 className="text-base font-medium">{receivingTitle}</h3>
        <p className={`${muted} mt-1`}>{t(key("routing_help"))}</p>
      </div>
      {status.receiving_businesses.length > 0 && <ul aria-label={receivingTitle} className="overflow-hidden rounded-surface bg-[#F7F5EE] dark:bg-[#1f2225]">
        {status.receiving_businesses.map(({ space_id, name, tax_id }) => (
          <li key={space_id} className="relative flex min-h-14 items-center gap-3 px-4 py-2 not-first:before:absolute not-first:before:inset-x-0 not-first:before:top-0 not-first:before:left-4 not-first:before:border-t not-first:before:border-[#172b26]/12 dark:not-first:before:border-white/10">
            <span className="grid size-8 shrink-0 place-items-center rounded-item bg-[#E8E6DE] text-[#3d4a45] dark:bg-white/8 dark:text-white/80"><Briefcase size={16} aria-hidden="true" /></span>
            <div className="min-w-0 break-words"><p>{name}</p><p className={`${muted} tabular-nums`}>{t(`business.dgii.tax_id_${tax_id.type}`)} {formatRnc(tax_id.value)}</p></div>
          </li>
        ))}
      </ul>}
      <p className={muted}>{t(key("receiving_hint"))}</p>
    </section>
  </>;
}
