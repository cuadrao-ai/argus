"use client";

// Actividad: the live history reads GET /business/activity (#1407) and shows only what that feed returns. The local
// preview (sample data, `?activity=contract|empty|loading|error`) also shows the fields #1410 and ACT-2a add.
// UI copy lives in the locale files (`business.activity_feed`).

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { resolveLanguage } from "@/lib/language-features";
import { Check, CalendarBlank, Lock } from "@phosphor-icons/react";
import { Avatar } from "@/components/ui/Avatar";
import { CuadraoMark } from "@/components/CuadraoMark";
import { invoicingShown, useBusiness } from "../BusinessWorkspace";
import { formatRelativeDay, formatShortDay } from "../business-format";
import { EmptyState } from "../foundation/EmptyState";
import GuideCard from "../foundation/GuideCard";
import { PageHeading } from "../foundation/PageHeading";
import ActivitySkeleton from "./ActivitySkeleton";
import { ACTIVITY_CARD, ACTIVITY_DAY, ACTIVITY_GRID, ACTIVITY_GRID_LIVE, ACTIVITY_HEADER_ROW, ACTIVITY_ROW } from "./activity-layout";
import { useActivityFeed } from "./useActivityFeed";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { secondaryButtonClass } from "../business-ui";
import { ToolbarPicker } from "../transacciones/RecordsToolbar";
import ActivityFilters, { ActivityFilterChips, EMPTY_ACTIVITY_FILTERS, type ActivityFilterValue, type ActivityFilterWords } from "./ActivityFilters";
import { fixtureItems, toContract, type ActivityItem, type DraftItem, type LedgerAction } from "./activity-sample";
import { activityActorName, activityPhrase, activityTarget } from "./activity-words";

type Area = "documents" | "records" | "invoicing" | "business";
type Group = "uploads" | "reading" | "reviews" | "approvals" | "edits" | "files" | "invoices" | "access" | "settings" | "other";

const ACTION_META: Record<DraftItem["action"], { area: Area; group: Group }> = {
  delete_document: { area: "documents", group: "edits" },
  restore_document: { area: "documents", group: "edits" },
  purge_document: { area: "documents", group: "edits" },
  expire_document: { area: "documents", group: "edits" },
  receipt_upload: { area: "documents", group: "uploads" },
  document_read: { area: "documents", group: "reading" },
  document_read_failed: { area: "documents", group: "reading" },
  receipt_review: { area: "documents", group: "reviews" },
  receipt_confirm: { area: "documents", group: "reviews" },
  resolve_duplicate: { area: "documents", group: "edits" },
  append_supporting_file: { area: "documents", group: "files" },
  prepare_attachment: { area: "documents", group: "files" },
  rebind_attachment: { area: "documents", group: "files" },
  business_attach_source: { area: "documents", group: "files" },
  review_draft: { area: "records", group: "reviews" },
  approve_expense: { area: "records", group: "approvals" },
  approve_income: { area: "records", group: "approvals" },
  approve_refund: { area: "records", group: "approvals" },
  reopen_draft: { area: "records", group: "approvals" },
  capture_note: { area: "records", group: "edits" },
  edit_current_note: { area: "records", group: "edits" },
  settle_remainder: { area: "records", group: "edits" },
  mark_personal: { area: "records", group: "edits" },
  decide_606: { area: "records", group: "edits" },
  business_propose_activity: { area: "records", group: "edits" },
  business_propose_allocation: { area: "records", group: "edits" },
  invoice_draft_created: { area: "invoicing", group: "invoices" },
  invoice_revision_saved: { area: "invoicing", group: "invoices" },
  set_business_rnc: { area: "business", group: "settings" },
  set_business_legal_name: { area: "business", group: "settings" },
  receipt_reading_enabled: { area: "business", group: "settings" },
  receipt_reading_disabled: { area: "business", group: "settings" },
  ownership_transferred: { area: "business", group: "access" },
  business_ask: { area: "records", group: "other" },
  owner_grant: { area: "business", group: "access" },
  grant_access: { area: "business", group: "access" },
  invite_access: { area: "business", group: "access" },
  accept_invite: { area: "business", group: "access" },
  revoke_grant: { area: "business", group: "access" },
  revoke_invite: { area: "business", group: "access" },
  change_role: { area: "business", group: "access" },
  other: { area: "business", group: "other" },
};

/* ---------- Screen ---------- */

type DateKey = "all" | "today" | "week" | "month";
const DATE_DAYS: Record<Exclude<DateKey, "all">, number> = { today: 0, week: 7, month: 30 };
const PAGE = 12;

const localDay = (iso: string) => { const d = new Date(iso); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const capitalize = (text: string) => text.charAt(0).toLocaleUpperCase() + text.slice(1);

/** A live row as the screen draws it; an action this screen does not know yet reads as "other". */
const fromFeed = (item: Omit<ActivityItem, "action" | "actor"> & { action: string; actor: ActivityItem["actor"] | null }): DraftItem => ({ ...item, action: item.action in ACTION_META ? (item.action as LedgerAction) : "other" });

export default function ActivityDraft() {
  const { t, i18n } = useTranslation();
  const { openPanel, source, chosen, invoicing, userId } = useBusiness();
  const live = source.mode === "live";
  const feed = useActivityFeed(live, chosen?.space_id ?? null);
  const lang = (i18n.resolvedLanguage ?? resolveLanguage({})) === "en" ? "en" : "es";
  const locale = lang === "en" ? "en-US" : "es-419";
  const c = {
    cols: { who: t("business.activity_feed.cols.who"), what: t("business.activity_feed.cols.what"), record: t("business.activity_feed.cols.record"), area: t("business.activity_feed.cols.area"), time: t("business.activity_feed.cols.time") },
    filters: { title: t("business.activity_feed.filters.title"), date: t("business.activity_feed.filters.date"), person: t("business.activity_feed.filters.person"), area: t("business.activity_feed.filters.area"), action: t("business.activity_feed.filters.action"), clear: t("business.activity_feed.filters.clear"), clearGroup: t("business.activity_feed.filters.clear_group"), remove: t("business.activity_feed.filters.remove"), all: t("business.activity_feed.filters.all"), today: t("business.activity_feed.filters.today"), week: t("business.activity_feed.filters.week"), month: t("business.activity_feed.filters.month") },
    areas: { documents: t("business.activity_feed.areas.documents"), records: t("business.activity_feed.areas.records"), invoicing: t("business.activity_feed.areas.invoicing"), business: t("business.activity_feed.areas.business") },
    groups: { uploads: t("business.activity_feed.groups.uploads"), reading: t("business.activity_feed.groups.reading"), reviews: t("business.activity_feed.groups.reviews"), approvals: t("business.activity_feed.groups.approvals"), edits: t("business.activity_feed.groups.edits"), files: t("business.activity_feed.groups.files"), invoices: t("business.activity_feed.groups.invoices"), access: t("business.activity_feed.groups.access"), settings: t("business.activity_feed.groups.settings"), other: t("business.activity_feed.groups.other") },
    viaChat: t("business.activity_feed.via_chat"),
    formerMember: t("business.activity_feed.former_member"),
    unmarkPersonal: t("business.activity_feed.unmark_personal"),
    managersOnly: t("business.activity_feed.managers_only"),
    noActor: t("business.activity_feed.no_actor"),
    noRecord: t("business.activity_feed.no_record"),
    loadMore: t("business.activity_feed.load_more"),
    am: t("business.activity_feed.am"),
    pm: t("business.activity_feed.pm"),
    firstRunTitle: t("business.activity_feed.first_run_title"),
    firstRunBody: t("business.activity_feed.first_run_body"),
    filteredTitle: t("business.activity_feed.filtered_title"),
    filteredBody: t("business.activity_feed.filtered_body"),
    errorTitle: t("business.activity_feed.error_title"),
    errorBody: t("business.activity_feed.error_body"),
    goHome: t("business.activity_feed.go_home"),
    loadMoreFailed: t("business.activity_feed.load_more_failed"),
    retry: t("business.activity_feed.retry"),
    recordPlaceholder: t("business.activity_feed.record_placeholder"),
  };
  const mode = live || typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("activity");
  const [filters, setFilters] = useState<ActivityFilterValue>(EMPTY_ACTIVITY_FILTERS);
  const [shown, setShown] = useState(PAGE);
  // Applying a filter starts the history over: first page, newest first (live: a new first cursor).
  const applyFilters = (next: ActivityFilterValue) => { setFilters(next); setShown(PAGE); };
  const { date, people, areas, actions: groups } = filters;
  const liveItems = feed.items;
  const all = useMemo(() => (live ? liveItems.map(fromFeed) : mode === "empty" ? [] : mode === "contract" ? toContract(fixtureItems()) : fixtureItems()) as DraftItem[], [live, liveItems, mode]);

  const today = localDay(new Date().toISOString());
  const filtered = all.filter((item) => {
    const meta = ACTION_META[item.action];
    if (date !== "all") {
      const since = new Date(); since.setHours(0, 0, 0, 0); since.setDate(since.getDate() - DATE_DAYS[date]);
      if (new Date(item.occurred_at) < since) return false;
    }
    if (people.length && !people.includes(item.actor?.display_name ?? c.noActor)) return false;
    if (areas.length && !areas.includes(meta.area)) return false;
    if (groups.length && !groups.includes(meta.group)) return false;
    return true;
  });
  const page = live ? filtered : filtered.slice(0, shown);
  const days = page.reduce<{ day: string; items: DraftItem[] }[]>((acc, item) => {
    const day = localDay(item.occurred_at);
    const last = acc[acc.length - 1];
    if (last?.day === day) last.items.push(item); else acc.push({ day, items: [item] });
    return acc;
  }, []);
  const clear = () => applyFilters(EMPTY_ACTIVITY_FILTERS);

  const dayLabel = (day: string) => {
    const relative = capitalize(formatRelativeDay(day, today, locale));
    const short = formatShortDay(day, locale);
    return relative === capitalize(short) ? relative : `${relative} · ${short}`;
  };
  const time = (iso: string) => { const d = new Date(iso); const h = d.getHours(); return `${h % 12 || 12}:${String(d.getMinutes()).padStart(2, "0")} ${h < 12 ? c.am : c.pm}`; };
  const open = (item: DraftItem) => {
    const target = activityTarget(item);
    return target ? () => openPanel(target) : undefined;
  };

  const filterOptions = {
    people: [...new Set(all.map((item) => item.actor?.display_name ?? c.noActor))].map((name) => ({ value: name, label: name })),
    areas: (Object.keys(c.areas) as Area[]).filter((value) => value !== "invoicing" || invoicingShown(invoicing)).map((value) => ({ value, label: c.areas[value] })),
    actions: (Object.keys(c.groups) as Group[]).filter((g) => all.some((item) => ACTION_META[item.action].group === g)).map((value) => ({ value, label: c.groups[value] })),
  };
  const filterWords: ActivityFilterWords = {
    title: c.filters.title, date: c.filters.date, people: c.filters.person, areas: c.filters.area, actions: c.filters.action,
    clear: c.filters.clear, clearGroup: c.filters.clearGroup, remove: (label) => `${c.filters.remove} ${label}`,
    dates: { all: c.filters.all, today: c.filters.today, week: c.filters.week, month: c.filters.month },
  };
  const datePicker = (
    <ToolbarPicker label={c.filters.date} value={c.filters[date]} icon={<CalendarBlank size={17} aria-hidden="true" />}>
      {(close) => <div className="space-y-0.5">{(["all", "today", "week", "month"] as const).map((key) => (
        <button key={key} type="button" onClick={() => { applyFilters({ ...filters, date: key }); close(); }} className="flex min-h-11 w-full items-center justify-between gap-3 rounded-item px-3 text-left text-[15px] text-[#172b26] hover:bg-black/5 dark:text-white dark:hover:bg-white/5">
          {c.filters[key]}{date === key ? <Check size={16} aria-hidden="true" /> : null}
        </button>
      ))}</div>}
    </ToolbarPicker>
  );
  // One quiet row of controls, so the history stays the main content.
  const toolbar = (
    <div className="mb-5 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <ActivityFilters value={filters} onChange={applyFilters} options={filterOptions} words={filterWords} datePicker={datePicker} />
      </div>
      <ActivityFilterChips value={filters} onChange={applyFilters} options={filterOptions} words={filterWords} />
    </div>
  );

  const actor = (item: DraftItem, size: 24 | 32) => {
    if (!item.actor) return { mark: <Avatar name={null} size={size} />, name: <span className="text-[#56635e] dark:text-white/60">{activityActorName(t, item.actor)}</span> };
    if (item.actor.kind === "extractor") return { mark: <span className={`inline-flex shrink-0 items-center justify-center rounded-full bg-[#e3ebe1] dark:bg-white/10 ${size === 24 ? "h-6 w-6" : "h-8 w-8"}`}><CuadraoMark size={size === 24 ? 14 : 18} /></span>, name: <span>{activityActorName(t, item.actor)}</span> };
    // An erased account reaches us already renamed; a member who left keeps the name the ledger stored.
    const erased = item.actor.display_name === "Exmiembro";
    const former = item.actor.membership === "former" && !erased;
    return {
      mark: <Avatar name={erased ? null : item.actor.display_name} size={size} />,
      name: <span className={erased ? "text-[#56635e] dark:text-white/60" : undefined}>{activityActorName(t, item.actor)}{former ? <span className="text-[#56635e] dark:text-white/60"> · {c.formerMember}</span> : null}</span>,
    };
  };
  const what = (item: DraftItem, sentenceStart = false) => {
    const phrase = item.action === "mark_personal" && item.missing?.personal === false ? c.unmarkPersonal : activityPhrase(t, item);
    const words = sentenceStart ? capitalize(phrase) : phrase;
    const failed = item.action === "document_read_failed";
    return <span className={failed ? "text-[#9e2f39] dark:text-[#ec9aa0]" : undefined}>{failed ? <span aria-hidden="true" className="mr-1.5 inline-block h-1.5 w-1.5 -translate-y-0.5 rounded-full bg-current" /> : null}{words}{(item.action === "delete_document" || item.action === "restore_document") && open(item) ? <> <span className="underline underline-offset-2">{t(item.action === "delete_document" ? "business.document_delete.view_deleted" : "business.document_delete.open")}</span></> : null}</span>;
  };
  const channel = (item: DraftItem) => item.actor?.kind === "owner_via_agent" ? c.viaChat : null;
  // Access and Business-setting rows reach owners and admins only; the server filters them, this only says so.
  const restricted = (item: DraftItem) => ACTION_META[item.action].group === "access" || ACTION_META[item.action].group === "settings";
  const record = (item: DraftItem) => item.missing?.object_label
    ? <>{item.missing.object_label}{item.missing.detail ? <span className="text-[#56635e] dark:text-white/60"> · {item.missing.detail}</span> : null}</>
    : <span aria-label={c.noRecord} className="text-[#56635e] dark:text-white/60">{c.recordPlaceholder}</span>;

  const columns = live ? [c.cols.who, c.cols.what, c.cols.area, c.cols.time] : [c.cols.who, c.cols.what, c.cols.record, c.cols.area, c.cols.time];
  let body: React.ReactNode;
  if (mode === "error" || (live && feed.status === "error")) {
    // A failure says what happened, keeps the server's reference and offers a way out.
    body = <div className="rounded-surface border border-black/[0.06] bg-white dark:border-white/[0.06] dark:bg-[#1f2225]">
      <EmptyState kind="error" title={c.errorTitle} body={c.errorBody} action={{ label: c.retry, run: live ? feed.retry : () => window.location.reload() }} secondary={{ label: c.goHome, run: () => openPanel({ kind: "overview" }) }} />
      {live && feed.reference ? <div className="flex justify-center pb-6"><ReferenceCode reference={feed.reference} /></div> : null}
    </div>;
  } else if (mode === "loading" || (live && feed.status === "loading")) {
    body = <ActivitySkeleton columns={columns} withRecord={!live} />;
  } else if (all.length === 0) {
    body = <div className="rounded-surface border border-black/[0.06] bg-white dark:border-white/[0.06] dark:bg-[#1f2225]"><EmptyState kind="first_run" mark="calendar" title={c.firstRunTitle} body={c.firstRunBody} /></div>;
  } else if (filtered.length === 0) {
    body = <div className="rounded-surface border border-black/[0.06] bg-white dark:border-white/[0.06] dark:bg-[#1f2225]"><EmptyState kind="filtered" title={c.filteredTitle} body={c.filteredBody} action={{ label: c.filters.clear, run: clear }} /></div>;
  } else {
    const grid = live ? ACTIVITY_GRID_LIVE : ACTIVITY_GRID;
    body = <>
      <div className={ACTIVITY_CARD}>
        <div className={`${ACTIVITY_HEADER_ROW} ${grid}`}>
          {columns.map((label, index) => <span key={label} className={index === columns.length - 1 ? "text-right" : undefined}>{label}</span>)}
        </div>
        {days.map(({ day, items }) => (
          <section key={day} aria-label={dayLabel(day)}>
            <h3 className={`sticky top-0 z-[1] ${ACTIVITY_DAY}`}>{dayLabel(day)}</h3>
            <ul>
              {items.map((item) => {
                const run = open(item);
                const who = actor(item, 24);
                const content = <>
                  {/* Desktop: one row per change. */}
                  <span className="hidden min-w-0 items-center gap-2.5 md:flex">{who.mark}<span className="truncate">{who.name}</span></span>
                  <span className="hidden min-w-0 truncate md:block">{what(item, true)}{channel(item) ? <span className="text-[#56635e] dark:text-white/60"> · {channel(item)}</span> : null}</span>
                  {live ? null : <span className="hidden min-w-0 truncate md:block">{record(item)}</span>}
                  <span className="hidden min-w-0 items-center gap-1.5 truncate text-[#56635e] dark:text-white/60 md:flex">{c.areas[ACTION_META[item.action].area]}{restricted(item) ? <Lock size={14} aria-label={c.managersOnly} /> : null}</span>
                  <span className="hidden text-right tabular-nums text-[#56635e] dark:text-white/60 md:block">{time(item.occurred_at)}</span>
                  {/* Phone: a sentence, then where and when. */}
                  <span className="flex gap-3 md:hidden">
                    <span className="pt-0.5">{actor(item, 32).mark}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[15px] leading-snug"><span className="font-medium">{who.name}</span> {what(item)}</span>
                      {item.missing?.object_label ? <span className="mt-0.5 block truncate text-[15px] leading-snug">{record(item)}</span> : null}
                      <span className="mt-1 flex flex-wrap items-center gap-x-1 text-[13px] text-[#56635e] dark:text-white/60">{restricted(item) ? <Lock size={13} aria-label={c.managersOnly} /> : null}{c.areas[ACTION_META[item.action].area]}{channel(item) ? <> · {channel(item)}</> : null} · <span className="tabular-nums">{time(item.occurred_at)}</span></span>
                    </span>
                  </span>
                </>;
                const rowClass = `${ACTIVITY_ROW} ${grid}`;
                return (
                  <li key={item.id} className="border-b border-[#dce0da] last:border-0 dark:border-white/10">
                    {run
                      ? <button type="button" onClick={run} className={`${rowClass} transition-colors duration-[80ms] hover:bg-black/[0.03] focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[#2f5a49] dark:hover:bg-white/[0.04]`}>{content}</button>
                      : <div className={rowClass}>{content}</div>}
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
      {live ? (feed.next ? <div className="mt-4 flex flex-col items-center gap-2">
        {feed.more === "error" ? <p role="alert" className="text-[14px] text-[#9e2f39] dark:text-[#ec9aa0]">{c.loadMoreFailed}</p> : null}
        {feed.more === "error" && feed.moreReference ? <ReferenceCode reference={feed.moreReference} /> : null}
        <button type="button" onClick={feed.loadMore} disabled={feed.more === "loading"} aria-busy={feed.more === "loading"} className={secondaryButtonClass}>{c.loadMore}</button>
      </div> : null) : filtered.length > shown ? <div className="mt-4 flex justify-center"><button type="button" onClick={() => setShown((n) => n + PAGE)} className={secondaryButtonClass}>{c.loadMore}</button></div> : null}
    </>;
  }

  return (
    <div data-testid="business-activity-draft">
      <PageHeading screen="activity" />
      {live && userId && chosen ? (
        <GuideCard cardId="actividad-intro" userId={userId} title={t("business.guide_cards.actividad_intro.title")} points={[
          { label: t("business.guide_cards.actividad_intro.follow.label"), body: t("business.guide_cards.actividad_intro.follow.body") },
          { label: t("business.guide_cards.actividad_intro.open.label"), body: t("business.guide_cards.actividad_intro.open.body") },
          { label: t("business.guide_cards.actividad_intro.deleted.label"), body: t("business.guide_cards.actividad_intro.deleted.body") },
        ]} />
      ) : null}
      {/* The controls stay while the history loads; empty and failed states have nothing to filter. */}
      {live || mode === "empty" || mode === "error" ? null : toolbar}
      {body}
    </div>
  );
}
