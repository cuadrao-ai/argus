"use client";

// DRAFT (design lane, light pass): shape review only. Copy lives here until Lucas
// approves the shape; the concrete pass moves it to the locale files and wires the API.

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { resolveLanguage } from "@/lib/language-features";
import { Check, CalendarBlank, Lock } from "@phosphor-icons/react";
import { Avatar } from "@/components/ui/Avatar";
import { CuadraoMark } from "@/components/CuadraoMark";
import { useBusiness } from "../BusinessWorkspace";
import { formatRelativeDay, formatShortDay } from "../business-format";
import { EmptyState } from "../foundation/EmptyState";
import { PageHeading } from "../foundation/PageHeading";
import ActivitySkeleton from "./ActivitySkeleton";
import { ACTIVITY_CARD, ACTIVITY_DAY, ACTIVITY_GRID, ACTIVITY_HEADER_ROW, ACTIVITY_ROW } from "./activity-layout";
import { secondaryButtonClass } from "../business-ui";
import { ToolbarPicker } from "../transacciones/RecordsToolbar";
import ActivityFilters, { ActivityFilterChips, EMPTY_ACTIVITY_FILTERS, type ActivityFilterValue, type ActivityFilterWords } from "./ActivityFilters";
import { dossierFixtureIds } from "../dossier-fixtures";

/* ---------- Contract shape: GET /business/activity (PR #1407) ---------- */

type ActorKind = "member" | "owner_via_agent" | "extractor";
type LedgerAction =
  | "review_draft" | "approve_expense" | "approve_income" | "approve_refund" | "capture_note" | "prepare_attachment"
  | "rebind_attachment" | "settle_remainder" | "mark_personal" | "decide_606" | "resolve_duplicate" | "edit_current_note"
  | "append_supporting_file" | "receipt_upload" | "receipt_review" | "receipt_confirm" | "email_ai_consent_declined"
  | "set_business_rnc" | "business_propose_activity" | "business_attach_source" | "business_propose_allocation"
  | "owner_grant" | "grant_access" | "invite_access" | "accept_invite" | "revoke_grant" | "revoke_invite" | "change_role" | "other";
type ActivityItem = {
  id: string;
  occurred_at: string;
  actor: { display_name: string; kind: ActorKind };
  action: LedgerAction;
  object: { kind: "draft" | "grant" | "invite"; id: string } | null;
};

/* ---------- MISSING from #1407: what this design needs on top ---------- */

/** Events the design shows that the ledger feed does not carry yet. */
/** ACT-2b brings these; no live rows until then. */
type MissingAction = "invoice_draft_created" | "invoice_revision_saved" | "document_read" | "document_read_failed" | "receipt_reading_enabled" | "receipt_reading_disabled" | "ownership_transferred";
type DraftItem = Omit<ActivityItem, "action" | "actor" | "object"> & {
  action: LedgerAction | MissingAction;
  /** null = an older event with no recorded actor (MISSING: nullable actor). MISSING: `membership`, so a member who left keeps their name. */
  actor: (ActivityItem["actor"] & { membership?: "current" | "former" }) | null;
  object: { kind: "draft" | "grant" | "invite" | "invoice"; id: string } | null;
  /** MISSING: a readable name for the affected record, and a short detail such as a role. */
  missing?: { object_label?: string; detail?: string; personal?: boolean };
};

type Area = "documents" | "records" | "invoicing" | "business";
type Group = "uploads" | "reading" | "reviews" | "approvals" | "edits" | "files" | "invoices" | "access" | "settings" | "other";

const ACTION_META: Record<DraftItem["action"], { area: Area; group: Group }> = {
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
  receipt_reading_enabled: { area: "business", group: "settings" },
  receipt_reading_disabled: { area: "business", group: "settings" },
  ownership_transferred: { area: "business", group: "access" },
  email_ai_consent_declined: { area: "business", group: "settings" },
  owner_grant: { area: "business", group: "access" },
  grant_access: { area: "business", group: "access" },
  invite_access: { area: "business", group: "access" },
  accept_invite: { area: "business", group: "access" },
  revoke_grant: { area: "business", group: "access" },
  revoke_invite: { area: "business", group: "access" },
  change_role: { area: "business", group: "access" },
  other: { area: "business", group: "other" },
};

/* ---------- Draft copy (es-419 first) ---------- */

const COPY = {
  es: {
    cols: { who: "Quién", what: "Qué pasó", record: "Registro", area: "Área", time: "Hora" },
    filters: { title: "Filtros", date: "Fecha", person: "Persona", area: "Área", action: "Acción", clear: "Limpiar filtros", clearGroup: "Limpiar", remove: "Quitar filtro:", all: "Todas las fechas", today: "Hoy", week: "Últimos 7 días", month: "Últimos 30 días" },
    areas: { documents: "Documentos", records: "Registros", invoicing: "Facturación", business: "Negocio" },
    groups: { uploads: "Subidas", reading: "Lecturas", reviews: "Revisiones", approvals: "Aprobaciones", edits: "Cambios en registros", files: "Adjuntos", invoices: "Facturas", access: "Accesos", settings: "Datos del negocio", other: "Otros" },
    actions: {
      receipt_upload: "subió un documento", document_read: "leyó un documento", document_read_failed: "no pudo leer un documento",
      receipt_review: "revisó un documento", receipt_confirm: "confirmó un documento", resolve_duplicate: "resolvió un duplicado",
      append_supporting_file: "adjuntó un archivo de soporte", prepare_attachment: "preparó un adjunto", rebind_attachment: "movió un adjunto a otro registro",
      business_attach_source: "vinculó un documento", review_draft: "revisó un registro", approve_expense: "aprobó un gasto",
      approve_income: "aprobó un ingreso", approve_refund: "aprobó un reembolso", capture_note: "creó un registro desde una nota",
      edit_current_note: "editó una nota", settle_remainder: "saldó el resto de un registro", mark_personal: "marcó un gasto como personal",
      decide_606: "decidió si un gasto va al 606", business_propose_activity: "propuso un registro", business_propose_allocation: "propuso cómo repartir un pago",
      invoice_draft_created: "creó un borrador de factura", invoice_revision_saved: "guardó cambios en una factura",
      set_business_rnc: "actualizó el RNC del negocio", receipt_reading_enabled: "activó la lectura de recibos", receipt_reading_disabled: "desactivó la lectura de recibos", ownership_transferred: "aceptó la propiedad del negocio", email_ai_consent_declined: "no autorizó leer correos con IA",
      owner_grant: "dio acceso de dueño", grant_access: "dio acceso", invite_access: "envió una invitación", accept_invite: "aceptó una invitación",
      revoke_grant: "quitó un acceso", revoke_invite: "canceló una invitación", change_role: "cambió un rol", other: "hizo un cambio",
    } as Record<DraftItem["action"], string>,
    viaChat: "desde el chat",
    formerMember: "Exmiembro",
    unmarkPersonal: "devolvió un gasto al negocio",
    managersOnly: "Solo lo ven dueños y administradores",
    noActor: "Actor no registrado",
    noRecord: "sin dato",
    loadMore: "Cargar más",
    am: "a.m.", pm: "p.m.",
    firstRunTitle: "Todavía no hay actividad",
    firstRunBody: "Cuando alguien suba, revise o apruebe algo en tu negocio, lo verás aquí.",
    filteredTitle: "Nada coincide con estos filtros",
    filteredBody: "Hay actividad fuera de esta fecha o de estos filtros.",
    errorTitle: "No pudimos cargar la actividad",
    errorBody: "Tus registros están bien. Inténtalo de nuevo en un momento. Ref. 7f3a2c",
    retry: "Reintentar",
  },
  en: {
    cols: { who: "Who", what: "What happened", record: "Record", area: "Area", time: "Time" },
    filters: { title: "Filters", date: "Date", person: "Person", area: "Area", action: "Action", clear: "Clear filters", clearGroup: "Clear", remove: "Remove filter:", all: "All dates", today: "Today", week: "Last 7 days", month: "Last 30 days" },
    areas: { documents: "Documents", records: "Records", invoicing: "Invoicing", business: "Business" },
    groups: { uploads: "Uploads", reading: "Reading", reviews: "Reviews", approvals: "Approvals", edits: "Record changes", files: "Attachments", invoices: "Invoices", access: "Access", settings: "Business details", other: "Other" },
    actions: {
      receipt_upload: "uploaded a document", document_read: "read a document", document_read_failed: "could not read a document",
      receipt_review: "reviewed a document", receipt_confirm: "confirmed a document", resolve_duplicate: "resolved a duplicate",
      append_supporting_file: "attached a supporting file", prepare_attachment: "prepared an attachment", rebind_attachment: "moved an attachment to another record",
      business_attach_source: "linked a document", review_draft: "reviewed a record", approve_expense: "approved an expense",
      approve_income: "approved an income", approve_refund: "approved a refund", capture_note: "created a record from a note",
      edit_current_note: "edited a note", settle_remainder: "settled a record's remainder", mark_personal: "marked an expense as personal",
      decide_606: "decided whether an expense goes in the 606", business_propose_activity: "proposed a record", business_propose_allocation: "proposed how to split a payment",
      invoice_draft_created: "created an invoice draft", invoice_revision_saved: "saved changes to an invoice",
      set_business_rnc: "updated the business RNC", receipt_reading_enabled: "turned on receipt reading", receipt_reading_disabled: "turned off receipt reading", ownership_transferred: "accepted ownership of the business", email_ai_consent_declined: "declined AI reading of emails",
      owner_grant: "gave owner access", grant_access: "gave access", invite_access: "sent an invitation", accept_invite: "accepted an invitation",
      revoke_grant: "removed access", revoke_invite: "cancelled an invitation", change_role: "changed a role", other: "made a change",
    } as Record<DraftItem["action"], string>,
    viaChat: "from chat",
    formerMember: "Former member",
    unmarkPersonal: "moved an expense back to the business",
    managersOnly: "Only owners and admins see this",
    noActor: "Actor not recorded",
    noRecord: "no data",
    loadMore: "Load more",
    am: "a.m.", pm: "p.m.",
    firstRunTitle: "No activity yet",
    firstRunBody: "When someone uploads, reviews or approves something in your business, you will see it here.",
    filteredTitle: "Nothing matches these filters",
    filteredBody: "There is activity outside this date or these filters.",
    errorTitle: "We could not load the activity",
    errorBody: "Your records are fine. Try again in a moment. Ref. 7f3a2c",
    retry: "Try again",
  },
} as const;

/* ---------- Fixtures, relative to now so the draft always reads fresh ---------- */

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();
const DAY = 24 * 60;
const LUCIA = { display_name: "Lucía Peña", kind: "member" as const };
const CARLOS = { display_name: "Carlos Méndez", kind: "member" as const };
const READER = { display_name: "Cuadrao", kind: "extractor" as const };
const draft = (key: keyof typeof dossierFixtureIds) => ({ kind: "draft" as const, id: dossierFixtureIds[key] });

function fixtureItems(): DraftItem[] {
  // Newest first, as the feed returns them.
  return ([] as DraftItem[]).concat([
    { id: "a01", occurred_at: minutesAgo(12), actor: LUCIA, action: "approve_expense", object: draft("ready"), missing: { object_label: "Ferretería La Esquina" } },
    { id: "a02", occurred_at: minutesAgo(26), actor: READER, action: "document_read", object: draft("ready"), missing: { object_label: "Ferretería La Esquina" } },
    { id: "a03", occurred_at: minutesAgo(27), actor: CARLOS, action: "receipt_upload", object: draft("ready"), missing: { object_label: "Ferretería La Esquina" } },
    { id: "a04", occurred_at: minutesAgo(95), actor: READER, action: "document_read_failed", object: draft("unknown"), missing: { object_label: "Foto de recibo, 10:51" } },
    { id: "a05", occurred_at: minutesAgo(140), actor: { ...LUCIA, kind: "owner_via_agent" }, action: "capture_note", object: draft("unprepared"), missing: { object_label: "Almuerzo con cliente" } },
    { id: "a06", occurred_at: minutesAgo(210), actor: CARLOS, action: "invoice_draft_created", object: { kind: "invoice", id: "inv-0042" }, missing: { object_label: "Factura a Hotel Costa Azul" } },
    { id: "a07", occurred_at: minutesAgo(DAY + 60), actor: LUCIA, action: "change_role", object: { kind: "grant", id: "g-carlos" }, missing: { object_label: "Carlos Méndez", detail: "Editor" } },
    { id: "a08", occurred_at: minutesAgo(DAY + 120), actor: CARLOS, action: "append_supporting_file", object: draft("income"), missing: { object_label: "Cliente Taller Rodríguez" } },
    { id: "a09", occurred_at: minutesAgo(DAY + 185), actor: LUCIA, action: "approve_income", object: draft("income"), missing: { object_label: "Cliente Taller Rodríguez" } },
    { id: "a10", occurred_at: minutesAgo(DAY + 300), actor: CARLOS, action: "resolve_duplicate", object: draft("fiscal"), missing: { object_label: "Estación Ruta 3" } },
    { id: "a11", occurred_at: minutesAgo(2 * DAY + 90), actor: CARLOS, action: "accept_invite", object: { kind: "invite", id: "i-carlos" }, missing: { object_label: "Carlos Méndez" } },
    { id: "a12", occurred_at: minutesAgo(3 * DAY + 30), actor: LUCIA, action: "invite_access", object: { kind: "invite", id: "i-carlos" }, missing: { object_label: "Carlos Méndez", detail: "Editor" } },
    { id: "a13", occurred_at: minutesAgo(3 * DAY + 50), actor: LUCIA, action: "set_business_rnc", object: null },
    { id: "a14", occurred_at: minutesAgo(3 * DAY + 400), actor: { display_name: "Ana Rosario", kind: "member", membership: "former" }, action: "edit_current_note", object: draft("fiscal"), missing: { object_label: "Estación Ruta 3" } },
    { id: "a15", occurred_at: minutesAgo(5 * DAY + 20), actor: LUCIA, action: "mark_personal", object: draft("unknownKind"), missing: { object_label: "Supermercado Nacional", personal: true } },
    { id: "a19", occurred_at: minutesAgo(4 * DAY + 10), actor: LUCIA, action: "receipt_reading_enabled", object: null },
    { id: "a21", occurred_at: minutesAgo(7 * DAY + 15), actor: LUCIA, action: "ownership_transferred", object: null },
    { id: "a22", occurred_at: minutesAgo(8 * DAY + 40), actor: LUCIA, action: "receipt_reading_disabled", object: null },
    { id: "a20", occurred_at: minutesAgo(6 * DAY + 45), actor: { display_name: "Exmiembro", kind: "member", membership: "former" }, action: "receipt_upload", object: draft("stale"), missing: { object_label: "Colmado El Progreso" } },
    { id: "a16", occurred_at: minutesAgo(5 * DAY + 70), actor: CARLOS, action: "invoice_revision_saved", object: { kind: "invoice", id: "inv-0041" }, missing: { object_label: "Factura a Colmado Peña" } },
    { id: "a17", occurred_at: minutesAgo(9 * DAY), actor: null, action: "receipt_upload", object: draft("readOnly"), missing: { object_label: "Nube Hosting" } },
    { id: "a18", occurred_at: minutesAgo(9 * DAY + 30), actor: LUCIA, action: "decide_606", object: draft("readOnly"), missing: { object_label: "Nube Hosting" } },
  ]).sort((a, z) => z.occurred_at.localeCompare(a.occurred_at));
}

const MISSING_ACTIONS = new Set<string>(["invoice_draft_created", "invoice_revision_saved", "document_read", "document_read_failed", "receipt_reading_enabled", "receipt_reading_disabled", "ownership_transferred"]);
/** `?activity=contract` shows only what #1407 returns today: no labels, no events it does not carry. */
const toContract = (items: DraftItem[]) => items.filter((item) => !MISSING_ACTIONS.has(item.action) && item.actor).map((item) => ({ ...item, actor: item.actor?.membership === "former" ? { display_name: "Exmiembro", kind: item.actor.kind } : item.actor && { display_name: item.actor.display_name, kind: item.actor.kind }, missing: undefined }));

/* ---------- Screen ---------- */

type DateKey = "all" | "today" | "week" | "month";
const DATE_DAYS: Record<Exclude<DateKey, "all">, number> = { today: 0, week: 7, month: 30 };
const PAGE = 12;

const localDay = (iso: string) => { const d = new Date(iso); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const capitalize = (text: string) => text.charAt(0).toLocaleUpperCase() + text.slice(1);

export default function ActivityDraft() {
  const { i18n } = useTranslation();
  const { openPanel } = useBusiness();
  const lang = (i18n.resolvedLanguage ?? resolveLanguage({})) === "en" ? "en" : "es";
  const locale = lang === "en" ? "en-US" : "es-419";
  const c = COPY[lang];
  const mode = typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("activity");
  const [filters, setFilters] = useState<ActivityFilterValue>(EMPTY_ACTIVITY_FILTERS);
  const [shown, setShown] = useState(PAGE);
  // Applying a filter starts the history over: first page, newest first (live: a new first cursor).
  const applyFilters = (next: ActivityFilterValue) => { setFilters(next); setShown(PAGE); };
  const { date, people, areas, actions: groups } = filters;
  const all = useMemo(() => (mode === "empty" ? [] : mode === "contract" ? toContract(fixtureItems()) : fixtureItems()) as DraftItem[], [mode]);

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
  const page = filtered.slice(0, shown);
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
    if (item.object?.kind === "draft") return () => openPanel({ kind: "draft", draftId: item.object!.id, list: "transactions" });
    // Grants, invites and invoices have no record screen to open yet (MISSING: link target); they stay plain, never a generic destination.
    return undefined;
  };

  const filterOptions = {
    people: [...new Set(all.map((item) => item.actor?.display_name ?? c.noActor))].map((name) => ({ value: name, label: name })),
    areas: (Object.keys(c.areas) as Area[]).map((value) => ({ value, label: c.areas[value] })),
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
    if (!item.actor) return { mark: <Avatar name={null} size={size} />, name: <span className="text-[#56635e] dark:text-white/60">{c.noActor}</span> };
    if (item.actor.kind === "extractor") return { mark: <span className={`inline-flex shrink-0 items-center justify-center rounded-full bg-[#e3ebe1] dark:bg-white/10 ${size === 24 ? "h-6 w-6" : "h-8 w-8"}`}><CuadraoMark size={size === 24 ? 14 : 18} /></span>, name: <span>Cuadrao</span> };
    // An erased account reaches us already renamed; a member who left keeps the name the ledger stored.
    const erased = item.actor.display_name === "Exmiembro";
    const former = item.actor.membership === "former" && !erased;
    return {
      mark: <Avatar name={erased ? null : item.actor.display_name} size={size} />,
      name: <span className={erased ? "text-[#56635e] dark:text-white/60" : undefined}>{erased ? c.formerMember : item.actor.display_name}{former ? <span className="text-[#56635e] dark:text-white/60"> · {c.formerMember}</span> : null}</span>,
    };
  };
  const what = (item: DraftItem, sentenceStart = false) => {
    const phrase = item.action === "mark_personal" && item.missing?.personal === false ? c.unmarkPersonal : c.actions[item.action];
    const words = sentenceStart ? capitalize(phrase) : phrase;
    const failed = item.action === "document_read_failed";
    return <span className={failed ? "text-[#9e2f39] dark:text-[#ec9aa0]" : undefined}>{failed ? <span aria-hidden="true" className="mr-1.5 inline-block h-1.5 w-1.5 -translate-y-0.5 rounded-full bg-current" /> : null}{words}</span>;
  };
  const channel = (item: DraftItem) => item.actor?.kind === "owner_via_agent" ? c.viaChat : null;
  // Access and Business-setting rows reach owners and admins only; the server filters them, this only says so.
  const restricted = (item: DraftItem) => ACTION_META[item.action].group === "access" || ACTION_META[item.action].group === "settings";
  const record = (item: DraftItem) => item.missing?.object_label
    ? <>{item.missing.object_label}{item.missing.detail ? <span className="text-[#56635e] dark:text-white/60"> · {item.missing.detail}</span> : null}</>
    : <span aria-label={c.noRecord} className="text-[#56635e] dark:text-white/60">-</span>;

  let body: React.ReactNode;
  if (mode === "error") {
    body = <div className="rounded-surface border border-black/[0.06] bg-white dark:border-white/[0.06] dark:bg-[#1f2225]"><EmptyState kind="error" title={c.errorTitle} body={c.errorBody} action={{ label: c.retry, run: () => window.location.reload() }} /></div>;
  } else if (mode === "loading") {
    body = <ActivitySkeleton columns={[c.cols.who, c.cols.what, c.cols.record, c.cols.area, c.cols.time]} />;
  } else if (all.length === 0) {
    body = <div className="rounded-surface border border-black/[0.06] bg-white dark:border-white/[0.06] dark:bg-[#1f2225]"><EmptyState kind="first_run" mark="calendar" title={c.firstRunTitle} body={c.firstRunBody} /></div>;
  } else if (filtered.length === 0) {
    body = <div className="rounded-surface border border-black/[0.06] bg-white dark:border-white/[0.06] dark:bg-[#1f2225]"><EmptyState kind="filtered" title={c.filteredTitle} body={c.filteredBody} action={{ label: c.filters.clear, run: clear }} /></div>;
  } else {
    const grid = ACTIVITY_GRID;
    body = <>
      <div className={ACTIVITY_CARD}>
        <div className={`${ACTIVITY_HEADER_ROW} ${grid}`}>
          <span>{c.cols.who}</span><span>{c.cols.what}</span><span>{c.cols.record}</span><span>{c.cols.area}</span><span className="text-right">{c.cols.time}</span>
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
                  <span className="hidden min-w-0 truncate md:block">{record(item)}</span>
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
      {filtered.length > shown ? <div className="mt-4 flex justify-center"><button type="button" onClick={() => setShown((n) => n + PAGE)} className={secondaryButtonClass}>{c.loadMore}</button></div> : null}
    </>;
  }

  return (
    <div data-testid="business-activity-draft">
      <PageHeading screen="activity" />
      {/* The controls stay while the history loads; empty and failed states have nothing to filter. */}
      {mode === "empty" || mode === "error" ? null : toolbar}
      {body}
    </div>
  );
}
