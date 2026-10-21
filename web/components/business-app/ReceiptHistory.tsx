"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessAccount } from "@/lib/business-api";
import { BUSINESS_FISCAL_FIELDS, type BusinessDossier, type BusinessDraftRevision, type BusinessFactField, type BusinessFact, type BusinessFiscalField } from "@/lib/business-dossier";
import { BUSINESS_STATUS, MUTED_TEXT } from "./foundation/presentation";
import { SURFACE_CARD } from "./foundation/surfaces";
import { quietButtonClass, useCategoryLabel } from "./business-ui";
import { presentBusinessFact, presentFiscalFact } from "./receipt-fact-presentation";
import FiscalRevision from "./FiscalRevision";

/** One thing that happened to the record, as the rail shows it. Only an approval changes the status, so only it gets a status dot. */
type HistoryEvent = { id: string; at: string; line: string | null; who: string | null; approved?: boolean; testId?: string; detail?: ReactNode };

const COLLAPSED = 3;
/** Spanish agrees the participle with the field's name. */
const FEMININE = new Set<string>(["occurred_on", "currency", "category_id", "kind", "business_share"]);

/** "DD/MM, h:mm a.m.", in the reader's local time. */
export function historyWhen(iso: string, am: string, pm: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const two = (value: number) => String(value).padStart(2, "0");
  const hours = date.getHours();
  return `${two(date.getDate())}/${two(date.getMonth() + 1)}, ${hours % 12 || 12}:${two(date.getMinutes())} ${hours < 12 ? am : pm}`;
}

/**
 * The record's Historial: what the API already records, newest first, as a
 * rail. Recibido comes from the first source, Leído from the reading's
 * revision, one correction per changed field from a person's revision, and
 * Aprobado from the recorded approval. Nothing here can be edited.
 */
export default function ReceiptHistory({ history, accounts, sources = [], approval = null }: {
  history: BusinessDraftRevision[];
  accounts: BusinessAccount[];
  sources?: BusinessDossier["sources"];
  approval?: BusinessDossier["approval_result"];
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const categoryLabel = useCategoryLabel();
  const [open, setOpen] = useState(false);
  const titleId = useId();
  const list = useRef<HTMLOListElement>(null);
  // Ver todo disappears once pressed, so focus moves to the first event it revealed.
  useEffect(() => {
    if (open) (list.current?.children[COLLAPSED] as HTMLElement | undefined)?.focus();
  }, [open]);
  const labels = {
    unknown: "",
    ownerUnknown: t("business.dossier.owner_unknown", "Owner doesn't know"),
    notRecorded: "",
    yes: t("business.marks.yes", "Yes"),
    no: t("business.marks.no", "No"),
    ownerFunds: t("business.dossier.owner_funds", "Owner's money"),
    businessAccount: t("business.dossier.business_account", "Business account"),
    value: (key: BusinessFactField, value: string) => {
      if (key === "category_id") return categoryLabel(value);
      const scope = key === "kind" ? "kind" : key === "business_share" ? "share" : key === "receipt_state" ? "receipt" : null;
      return scope ? t(`business.dossier.${scope}.${value}`, value) : value;
    },
  };
  const answer606 = (facts: BusinessDraftRevision["before"]) => {
    const fact = facts?.fiscal?.include_606;
    return fact && fact.state === "known" ? fact.value : null;
  };
  const said606 = (answer: boolean | null) => answer === null ? t("business.marks.pending_606", "Waiting for the accountant") : answer ? labels.yes : labels.no;
  /** One correction as a sentence, or null when the shown value did not change (a confirmation changes only who stated it). */
  const changed = (key: string, before: string, after: string): string | null => {
    if (before === after) return null;
    const field = t(`business.dossier.field.${key}`, key);
    if (!before) return t("business.history.set", "{{field}}: {{after}}", { field, after });
    if (!after) after = t("business.dossier.not_recorded", "Not recorded");
    return t(FEMININE.has(key) ? "business.history.changed_female" : "business.history.changed", "{{field}} changed from {{before}} to {{after}}", { field, before, after });
  };
  const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

  const events: HistoryEvent[] = [];
  // What arrived is a file or a WhatsApp message; a chat proposal or a web action is not a receipt coming in.
  const first = sources
    .filter((item) => item.kind === "attachment" || (item.kind === "message" && item.channel === "whatsapp"))
    .sort((a, b) => Date.parse(a.received_at) - Date.parse(b.received_at))[0];
  if (first) {
    const channel = first.channel === "whatsapp" ? "WhatsApp" : first.channel === "email" ? t("business.history.channel_email", "Email") : t("business.history.channel_web", "Uploaded");
    events.push({ id: `source-${first.id}`, at: first.received_at, line: `${t("business.history.received", "Received")} · ${channel}`, who: null });
  }
  for (const revision of history) {
    const at = revision.created_at;
    const who = revision.actor.display_name;
    if (revision.actor.actor_kind === "extractor") {
      events.push({ id: `read-${revision.version}`, at, line: t("business.history.read", "Read"), who });
      continue;
    }
    const facts = (Object.keys(revision.after).filter((key) => key !== "fiscal") as BusinessFactField[]).filter((key) => !same(revision.before?.[key], revision.after[key]));
    for (const key of facts) {
      const show = (side: BusinessDraftRevision["before"]) => side ? presentBusinessFact(key, side, accounts, locale, labels) : "";
      events.push({ id: `${revision.version}-${key}`, at, line: changed(key, show(revision.before), show(revision.after)), who });
    }
    for (const key of BUSINESS_FISCAL_FIELDS) {
      if (key === "include_606") {
        const before = answer606(revision.before);
        const after = answer606(revision.after);
        // The 606 answer is a person's: an event only when someone gave or changed it, never for a read that left it open.
        if (after !== null && after !== before) events.push({ id: `${revision.version}-606`, at, line: changed(key, said606(before), said606(after)), who, testId: "history-606" });
        continue;
      }
      const before = revision.before?.fiscal?.[key as Exclude<BusinessFiscalField, "include_606">] as BusinessFact<string> | undefined;
      const after = revision.after.fiscal?.[key as Exclude<BusinessFiscalField, "include_606">] as BusinessFact<string> | undefined;
      if (same(before, after)) continue;
      const show = (side: BusinessDraftRevision["before"]) => side ? presentFiscalFact(key, side, locale, labels) : "";
      const line = changed(key, show(revision.before), show(revision.after));
      const verified = key === "rnc" && line === null && after?.state === "known" && after.verified && !before?.verified;
      events.push({ id: `${revision.version}-${key}`, at, line: verified ? t("business.history.rnc_verified", "RNC verified") : line, who });
    }
    if (revision.after_dgii && !same(revision.before_dgii, revision.after_dgii)) {
      events.push({ id: `${revision.version}-dgii`, at, line: `${t("business.dossier.fiscal_details", "Fiscal details")} · ${revision.after_dgii.form}`, who, detail: <FiscalRevision declaration={revision.after_dgii} /> });
    }
    if (!events.some((event) => event.line !== null && event.id.startsWith(`${revision.version}-`))) {
      events.push({ id: `${revision.version}-reviewed`, at, line: t("business.dossier.reviewed_revision", "This revision was reviewed."), who });
    }
  }
  if (approval?.status === "recorded") {
    events.push({ id: "approved", at: approval.approved_at, line: t("business.history.approved", "Approved"), who: approval.actor.display_name, approved: true });
  }
  const kept = events.filter((event): event is HistoryEvent & { line: string } => event.line !== null);
  if (!kept.length) return null;
  // Newest first; events of one revision keep their field order.
  const newestFirst = kept.map((event, index) => ({ event, index })).sort((a, b) => Date.parse(b.event.at) - Date.parse(a.event.at) || a.index - b.index).map(({ event }) => event);
  const shown = open ? newestFirst : newestFirst.slice(0, COLLAPSED);
  const am = t("business.history.am", "a.m.");
  const pm = t("business.history.pm", "p.m.");

  return (
    <section className={SURFACE_CARD} aria-labelledby={titleId} data-testid="receipt-history">
      <h3 id={titleId} className="font-display text-[18px] font-medium leading-6 text-[#172b26] dark:text-white">{t("business.history.title", "History")}</h3>
      <ol ref={list} className="mt-4">
        {shown.map((event, index) => (
          <li key={event.id} tabIndex={-1} data-testid={event.testId ?? "history-event"} data-approved={event.approved ? "true" : undefined} className="relative pb-4 pl-6 last:pb-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49]">
            {index < shown.length - 1 ? <span aria-hidden="true" className="absolute bottom-0 left-[5px] top-3 w-px bg-[#DCE0DA] dark:bg-white/15" /> : null}
            <span aria-hidden="true" data-testid="history-dot" className="absolute left-0 top-[5px] h-3 w-3 rounded-full" style={{ backgroundColor: event.approved ? BUSINESS_STATUS.approved.ink : MUTED_TEXT }} />
            <p className="break-words text-[15px] leading-[22px] text-[#172b26] dark:text-white">{event.line}</p>
            <p className="mt-1 text-[13px] leading-[18px] text-[#56635e] dark:text-white/70">{[event.who, historyWhen(event.at, am, pm)].filter(Boolean).join(" · ")}</p>
            {event.detail}
          </li>
        ))}
      </ol>
      {!open && newestFirst.length > COLLAPSED ? (
        <button type="button" onClick={() => setOpen(true)} className={`${quietButtonClass} mt-2`}>
          {t("business.history.see_all", "See all")}
        </button>
      ) : null}
    </section>
  );
}
