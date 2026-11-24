"use client";

import { useId, useState } from "react";
import { ArrowDownToLine, BadgeCheck, ChevronDown, Copy, Paperclip, Pencil, ScanText, Unlink, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { personName } from "@/lib/person-name";
import type { BusinessAccount } from "@/lib/business-api";
import type { DgiiDeclaration, DgiiField, DgiiFields } from "@/lib/business-dgii";
import { BUSINESS_FISCAL_FIELDS, type BusinessDossier, type BusinessDraftRevision, type BusinessFactField, type BusinessFact, type BusinessFacts, type BusinessFiscalField, type BusinessSupportingFile } from "@/lib/business-dossier";
import { formatDay, formatMoney, formatTimestamp } from "./business-format";
import { DOCUMENT_TYPE_LABELS } from "./receipt-fact-rows";
import { dossierRowLabel } from "./dossier-attention";
import { DossierCard } from "./dossier/DossierParts";
import { hasNoteChange } from "./dossier/annotation-history";
import { fiscalFieldLabel } from "./dossier/fiscal-field-label";
import styles from "./dossier/dossier.module.css";
import { FOCUS_RING } from "./foundation/presentation";
import { useCategoryLabel } from "./business-ui";
import { dgiiOptionLabel, presentBusinessFact, presentDgiiValue, presentFiscalFact } from "./receipt-fact-presentation";
import { resolveLanguage } from "@/lib/language-features";

/** One DGII field a fiscal save changed: `before` is null when the field had no value to strike. */
type FiscalChange = { name: string; field: string; before: string | null; after: string };

/** One thing that happened to the record, as the rail shows it. Only an approval changes the status, so only it gets a status dot. */
type HistoryEvent = { id: string; at: string; kind?: keyof typeof EVENT_ICON; line: string | null; heading?: string; sub?: string; who: string | null; note?: string; approved?: boolean; testId?: string; diff?: { before: string | null; after: string }; changes?: FiscalChange[] };

const EVENT_ICON = { received: ArrowDownToLine, read: ScanText, edit: Pencil, approved: BadgeCheck, duplicate: Copy, supporting: Paperclip, unlinked: Unlink } satisfies Record<string, LucideIcon>;

const STRUCK = "rounded-mark bg-[#f6dfe0] px-1.5 text-[#9e2f39] dark:bg-[#4a2a2f] dark:text-[#ec9aa0]";
const ADDED = "rounded-mark bg-[#e3ebe1] px-1.5 text-[#2f5a49] no-underline dark:bg-[#293b32] dark:text-[#8fcbb0]";
const ARROW = "text-[#56635e] dark:text-white/60";
/** A fiscal save shows this many changes before the rest wait behind a button. */
const CHANGES_SHOWN = 2;

const NO_FORMS: readonly string[] = [];

/** Spanish agrees the participle with the field's name. */
const FEMININE = new Set<string>(["occurred_on", "currency", "category_id", "kind", "business_share"]);

/** The local calendar day of an instant, as `YYYY-MM-DD`. */
function localDay(date: Date): string {
  const two = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${two(date.getMonth() + 1)}-${two(date.getDate())}`;
}

/**
 * The Historial tab: what the API already records, newest first, in one card
 * per day ("Hoy", "Ayer", then the date). Its arrival comes from the first
 * source. The revision that creates the record is one line, never a list of
 * its values: Leído when Cuadrao read a document or a message, the person's
 * line when a person started it. Later revisions give one correction per
 * changed field with its struck-to-green diff, and the dated acceptance comes
 * from the recorded approval: the one place an accepted record says so. Notes
 * and supporting file changes come from saved revisions.
 */
export default function ReceiptHistory({ history, accounts, sources = [], approval = null, documentType, dgiiFields = null, salePaymentForms = NO_FORMS, supportingFiles = [] }: {
  history: BusinessDraftRevision[];
  documentType?: BusinessDossier["document_type"];
  accounts: BusinessAccount[];
  sources?: BusinessDossier["sources"];
  approval?: BusinessDossier["approval_result"];
  /** The DGII field dictionary that names and orders a fiscal save's changes; until it loads a save shows no field list. */
  dgiiFields?: DgiiFields | null;
  /** The 607 fields that are a sale's ways to pay, as the server lists them. A save names the ways, never their amounts. */
  salePaymentForms?: readonly string[];
  supportingFiles?: readonly BusinessSupportingFile[];
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const categoryLabel = useCategoryLabel();
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
  const fieldName = (key: string) => dossierRowLabel(t, key as Parameters<typeof dossierRowLabel>[1], { document_type: documentType });
  /** One correction as a sentence, or null when the shown value did not change (a confirmation changes only who stated it). */
  const changed = (key: string, before: string, after: string): string | null => {
    if (before === after) return null;
    const field = fieldName(key);
    if (!before) return t("business.history.set", "{{field}}: {{after}}", { field, after });
    if (!after) after = t("business.dossier.not_recorded", "Not recorded");
    return t(FEMININE.has(key) ? "business.history.changed_female" : "business.history.changed", "{{field}} changed from {{before}} to {{after}}", { field, before, after });
  };
  const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
  /** The two values come from the saved revision; an empty side says so. */
  const diffOf = (before: string, after: string) => before !== after
    ? { before: before || null, after: after || t("business.dossier.row.no_data") }
    : undefined;
  /** One changed field as the rail shows it: its name, then the diff. The sentence is for a screen reader. */
  const correction = (key: string, before: string, after: string): Pick<HistoryEvent, "line" | "heading" | "diff"> => {
    const diff = diffOf(before, after);
    return { line: changed(key, before, after), heading: diff ? fieldName(key) : undefined, diff };
  };
  /** The dictionary's fields a save changed, in its order, named and worded as Datos fiscales shows them; a field the earlier declaration lacked has nothing to strike. A sale's ways to pay are one line, where the first of them sorts, named as General names them. */
  const fiscalChanges = (before: DgiiDeclaration | null | undefined, after: DgiiDeclaration, facts: BusinessFacts, reviewed?: readonly string[] | null): FiscalChange[] | null => {
    if (!dgiiFields) return null;
    const shown = (field: DgiiField, value: DgiiDeclaration[string] | undefined) => presentDgiiValue(field, value, facts, locale, t, t("business.dossier.unknown", "Unknown"));
    const forms = after.form === "607" ? salePaymentForms : NO_FORMS;
    const paidBy = (declaration: DgiiDeclaration | null | undefined) => forms.filter((name) => Number(declaration?.[name]) > 0).map((name) => dgiiOptionLabel(t, "sale_payment_form", name)).join(", ");
    const payment = { before: paidBy(before), after: paidBy(after) };
    const firstForm = dgiiFields[after.form].find((field) => forms.includes(field.name))?.name;
    // The ways to pay are one line, so a person's edit to any of them names the whole group.
    const named = (name: string) => !reviewed || (forms.includes(name) ? forms : [name]).some((each) => reviewed.includes(each));
    return dgiiFields[after.form].flatMap((field): FiscalChange[] => {
      if (!named(field.name)) return [];
      if (forms.includes(field.name)) {
        if (field.name !== firstForm || payment.before === payment.after) return [];
        return [{ name: "sale_payment", field: dossierRowLabel(t, "sale_payment", { document_type: documentType }), before: payment.before || null, after: payment.after || t("business.dossier.row.no_data") }];
      }
      if ((before?.[field.name] ?? null) === (after[field.name] ?? null)) return [];
      return [{
        name: field.name,
        field: fiscalFieldLabel(t, after.form, field.name),
        before: before && field.name in before ? shown(field, before[field.name]) : null,
        after: shown(field, after[field.name]),
      }];
    });
  };

  const events: HistoryEvent[] = [];
  const changedFiles = new Set(history.filter((revision) => revision.supporting_change).map((revision) => revision.source_ids[0]));
  const filesBySource = new Map(supportingFiles.map((file) => [file.source_id, file]));
  // What arrived is a file or a WhatsApp message; a chat proposal or a web action is not a receipt coming in.
  const first = sources
    .filter((item) => (item.kind === "attachment" && !changedFiles.has(item.id) && !filesBySource.has(item.id)) || (item.kind === "message" && item.channel === "whatsapp"))
    .sort((a, b) => Date.parse(a.received_at) - Date.parse(b.received_at))[0];
  if (first) {
    const channel = first.channel === "whatsapp" ? "WhatsApp" : first.channel === "email" ? t("business.history.channel_email", "Email") : t("business.history.channel_web", "Web");
    events.push({ id: `source-${first.id}`, at: first.received_at, kind: "received", line: t("business.history.arrived", { channel }), sub: first.kind === "attachment" ? first.filename ?? undefined : undefined, who: null });
  }
  for (const revision of history) {
    const at = revision.created_at;
    // A revision the server made for a stated reason is a change like any other, made through Cuadrao for the person who caused it.
    const name = personName(t, revision.actor);
    const who = revision.reason ? t("business.history.via_cuadrao", { name }) : name;
    const start = events.length;
    if (revision.duplicate) {
      const { other_counterparty: counterparty, other_filename: filename } = revision.duplicate;
      const other = [counterparty, filename].filter(Boolean).join(", ") || t("business.receipts.duplicate_resolution.documents.other");
      events.push({ id: `${revision.version}-duplicate`, at, kind: "duplicate", line: t(`business.history.duplicate.${revision.duplicate.decision}`, { other }), who });
      continue;
    }
    // The server writes a read as the extractor, for a file from any channel, and a chat message as the owner's agent.
    const readByCuadrao = revision.actor.actor_kind === "extractor" || (!revision.before && revision.actor.actor_kind === "owner_via_agent");
    if (!revision.reason && readByCuadrao) {
      events.push({ id: `read-${revision.version}`, at, kind: "read", line: t("business.history.read", "Read"), who: t("business.activity_feed.extractor_name") });
      continue;
    }
    if (!revision.before) {
      // A person started the record: its first values are not corrections.
      events.push({ id: `${revision.version}-reviewed`, at, line: t("business.dossier.reviewed_revision", "This revision was reviewed."), who });
      continue;
    }
    const { before_document_type: typeBefore, after_document_type: typeAfter } = revision;
    const retyped = typeBefore && typeAfter && typeBefore !== typeAfter ? { before: t(DOCUMENT_TYPE_LABELS[typeBefore]), after: t(DOCUMENT_TYPE_LABELS[typeAfter]) } : null;
    if (retyped) events.push({ id: `${revision.version}-document-type`, at, ...correction("document_type", retyped.before, retyped.after), who });
    // A type change moves the activity and other answers with it; beside its one Tipo line, only what the server says the person also set counts.
    const reviewed = retyped ? { facts: revision.reviewed_fact_fields ?? [], declaration: revision.reviewed_declaration_fields ?? [] } : null;
    const shown = (key: string) => !reviewed || (key !== "kind" && reviewed.facts.includes(key));
    const facts = (Object.keys(revision.after).filter((key) => key !== "fiscal" && shown(key)) as BusinessFactField[]).filter((key) => !same(revision.before?.[key], revision.after[key]));
    for (const key of facts) {
      const show = (side: BusinessDraftRevision["before"]) => side ? presentBusinessFact(key, side, accounts, locale, labels) : "";
      const subtotal = (side: "before" | "after") => {
        const amount = revision[`${side}_net_amount`];
        return amount === undefined ? show(revision[side]) : amount?.amount == null ? "" : formatMoney(amount.amount, revision[side]?.currency.value ?? "", locale);
      };
      events.push({ id: `${revision.version}-${key}`, at, ...correction(key, key === "net_amount" ? subtotal("before") : show(revision.before), key === "net_amount" ? subtotal("after") : show(revision.after)), who });
    }
    for (const key of BUSINESS_FISCAL_FIELDS) {
      if (!shown(key)) continue;
      if (key === "include_606") {
        if (documentType === "venta") continue;
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
      const change = correction(key, show(revision.before), show(revision.after));
      const verified = key === "rnc" && change.line === null && after?.state === "known" && after.verified && !before?.verified;
      events.push({ id: `${revision.version}-${key}`, at, ...(verified ? { line: t("business.history.rnc_verified", "RNC verified") } : change), who });
    }
    if (hasNoteChange(revision)) {
      const field = t("business.dossier.note.title");
      const after = revision.after_current_note || t("business.dossier.not_recorded", "Not recorded");
      const before = revision.before_current_note || null;
      const line = before ? t("business.history.changed_female", { field, before, after }) : t("business.history.set", { field, after });
      events.push({ id: `${revision.version}-current-note`, at, line, heading: field, who, testId: "history-current-note", diff: { before, after } });
    }
    if (revision.supporting_change) {
      const sourceId = revision.source_ids[0];
      const file = filesBySource.get(sourceId);
      const unlinked = revision.supporting_change === "unlinked";
      events.push({
        id: `${revision.version}-supporting`, at, line: t(`business.history.supporting.${revision.supporting_change}`),
        sub: unlinked ? undefined : revision.supporting_filename ?? file?.filename ?? undefined,
        who, kind: unlinked ? "unlinked" : "supporting", testId: "history-supporting",
      });
    } else if (revision.before && same(revision.before, revision.after)) {
      // Earlier links did not record an explicit supporting change.
      const attachments = revision.source_ids.flatMap((id) => {
        const source = sources.find((source) => source.id === id);
        return source?.kind === "attachment" ? [source.filename ?? t("business.transactions.layout.annotations.received_document")] : [];
      });
      if (attachments.length) events.push({ id: `${revision.version}-supporting`, at, line: `${t("business.transactions.layout.annotations.linked_evidence")} · ${attachments.join(", ")}`, who, kind: "supporting", testId: "history-supporting" });
    }
    if (revision.after_dgii) {
      const named = reviewed ? reviewed.declaration : revision.reviewed_declaration_fields;
      const changes = fiscalChanges(revision.before_dgii, revision.after_dgii, revision.after, named);
      // Until the dictionary loads, any difference is a save; then only a field it names counts.
      if (changes ? changes.length : named?.length === 0 ? false : !same(revision.before_dgii, revision.after_dgii)) {
        events.push({ id: `${revision.version}-dgii`, at, line: t("business.history.fiscal_saved", { form: revision.after_dgii.form }), who, changes: changes ?? undefined });
      }
    }
    if (!events.some((event) => event.line !== null && event.id.startsWith(`${revision.version}-`))) {
      events.push({ id: `${revision.version}-reviewed`, at, line: t("business.dossier.reviewed_revision", "This revision was reviewed."), who });
    }
    const explained = revision.reason ? events.slice(start).find((event) => event.line !== null) : undefined;
    if (explained) explained.note = t(`business.history.reason.${revision.reason}`);
  }
  if (approval?.status === "recorded") {
    events.push({ id: "approved", at: approval.approved_at, kind: "approved", line: t("business.history.approved", "Approved"), sub: t("business.history.accepted_note"), who: personName(t, approval.actor), approved: true });
  }
  const kept = events.filter((event): event is HistoryEvent & { line: string } => event.line !== null);
  if (!kept.length) return null;
  // Newest first; events of one revision keep their field order.
  const newestFirst = kept.map((event, index) => ({ event, index })).sort((a, b) => Date.parse(b.event.at) - Date.parse(a.event.at) || a.index - b.index).map(({ event }) => event);
  const today = new Date();
  const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
  const dayName = (day: string) => day === localDay(today) ? t("business.history.today") : day === localDay(yesterday) ? t("business.history.yesterday") : formatDay(day, locale);
  const days: { day: string; events: typeof newestFirst }[] = [];
  for (const event of newestFirst) {
    const at = new Date(event.at);
    const day = Number.isNaN(at.getTime()) ? "" : localDay(at);
    const last = days[days.length - 1];
    if (last?.day === day) last.events.push(event);
    else days.push({ day, events: [event] });
  }

  return (
    <div className={styles.stack} data-testid="receipt-history">
      {days.map(({ day, events: dated }) => (
        <DossierCard key={day} title={day ? dayName(day) : t("business.history.title", "History")} testId="history-day">
          <ol className={styles.events}>
            {dated.map((event) => {
              const Icon = EVENT_ICON[event.kind ?? "edit"];
              return (
                <li key={event.id} data-testid={event.testId ?? "history-event"} data-approved={event.approved ? "true" : undefined} className={styles.event}>
                  <span className={styles.eventIcon} data-approved={event.approved || undefined} data-testid="history-dot"><Icon size={15} aria-hidden="true" /></span>
                  <p className={styles.eventTitle}>{event.heading ? <><span aria-hidden="true">{event.heading}</span><span className="sr-only">{event.line}</span></> : event.line}</p>
                  <div className={styles.eventWho} data-testid="history-who">{event.who ? <span>{event.who}</span> : null}<time dateTime={event.at}>{formatTimestamp(event.at, locale)}</time></div>
                  {event.sub ? <p className={styles.eventSub} data-testid="history-sub">{event.sub}</p> : null}
                  {/* The sentence says it for every reader; the diff shows it at a glance. */}
                  {event.diff ? <div aria-hidden="true" data-testid="history-diff" className={`${styles.eventMore} flex flex-wrap items-center gap-1.5 text-[13.5px] leading-5 tabular-nums`}>
                    {event.diff.before ? <><del className={STRUCK}>{event.diff.before}</del><span className={ARROW}>→</span></> : null}
                    <ins className={ADDED}>{event.diff.after}</ins>
                  </div> : null}
                  {event.changes?.length ? <div className={styles.eventMore}><FiscalChanges changes={event.changes} /></div> : null}
                  {event.note ? <p data-testid="history-note" className={styles.eventSub}>{event.note}</p> : null}
                </li>
              );
            })}
          </ol>
        </DossierCard>
      ))}
    </div>
  );
}

/** What one fiscal save changed, field by field; past two, the rest wait behind one button. */
function FiscalChanges({ changes }: { changes: FiscalChange[] }) {
  const { t } = useTranslation();
  const [all, setAll] = useState(false);
  const listId = useId();
  const more = changes.length - CHANGES_SHOWN;
  return (
    <>
      <ul id={listId} data-testid="history-changes" className="mt-1.5 flex flex-col gap-1">
        {(all || more <= 0 ? changes : changes.slice(0, CHANGES_SHOWN)).map((change) => (
          <li key={change.name} data-testid="history-change" className="flex flex-wrap items-center gap-1.5 text-[14px] leading-5">
            <span className="text-[#56635e] dark:text-white/70">{change.field}</span>
            {change.before === null ? null : <><del className={STRUCK}>{change.before}</del><span aria-hidden="true" className={ARROW}>→</span></>}
            <ins className={ADDED}>{change.after}</ins>
          </li>
        ))}
      </ul>
      {more > 0 ? (
        <button type="button" data-testid="history-more" aria-expanded={all} aria-controls={listId} onClick={() => setAll((value) => !value)} className={`-mb-2 -ml-2 mt-0.5 inline-flex min-h-8 items-center gap-1 rounded-item px-2 text-[13px] font-medium leading-[18px] text-[var(--cuadrao-green)] hover:bg-black/[0.03] dark:hover:bg-white/[0.05] ${FOCUS_RING}`}>
          {all ? t("business.search.show_less", "See less") : t("business.history.more_changes", { count: more })}
          <ChevronDown className={`h-3.5 w-3.5 shrink-0 transition-transform motion-reduce:transition-none ${all ? "rotate-180" : ""}`} aria-hidden="true" />
        </button>
      ) : null}
    </>
  );
}
