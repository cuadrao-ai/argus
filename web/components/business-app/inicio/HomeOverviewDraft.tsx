"use client";

// Inicio's first layer, Resumen del negocio: what needs attention, where to continue and what setup remains, plus
// Personalizar Inicio. Draft copy lives here (es-419 first) until the copy pass moves it to the locale files.

import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { resolveLanguage } from "@/lib/language-features";
import { Briefcase, Check, IdentificationCard, Scan, UsersThree, type Icon } from "@phosphor-icons/react";
import { ArrowDown, ArrowUp, ChevronRight, CircleAlert, FilePenLine, FileSearch, GripVertical, PenLine, RotateCcw, SlidersHorizontal, type LucideIcon } from "lucide-react";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { readStored, writeStored } from "@/lib/browser-storage";
import type { ReceiptSummary } from "@/lib/business-api";
import { useBusiness, type BusinessPanelState } from "../BusinessWorkspace";
import { formatRelativeTime } from "../business-format";
import { EmptyState } from "../foundation/EmptyState";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { CHANNEL_ICON } from "../foundation/channel-icons";
import { FOCUS_RING } from "../foundation/presentation";
import { canManageBusiness, cardClass, quietButtonClass } from "../business-ui";
import { SCREEN_ICON } from "../nav-glyphs";
import { useReceiptStateWord } from "../receipt-state-word";
import { RECENT_WORK, SETUP_STATE, type RecentWork, type SetupStep, type SetupStepKey } from "./home-draft-data";
import { useHomeCounts, useSampleBusiness, type ReviewCount } from "./useHomeCounts";

const COPY = {
  es: {
    today: "Resumen del negocio",
    recordsToReview: (n: number) => (n === 1 ? "1 registro por revisar" : `${n} registros por revisar`),
    invoiceDrafts: (n: number) => (n === 1 ? "1 factura en borrador" : `${n} facturas en borrador`),
    needs: "Necesita atención",
    loading: "Cargando la Bandeja",
    needsFailed: "No pudimos cargar lo que necesita atención",
    needsFailedBody: "Tus documentos están guardados. Revisa tu conexión e inténtalo otra vez.",
    reviewCountFailed: "No pudimos cargar cuántos registros esperan revisión",
    retry: "Reintentar",
    showing: (shown: number, total: number) => `Mostrando ${shown} de ${total}`,
    customize: "Personalizar Inicio",
    customizeLead: "Cambia el orden de las secciones de tu Inicio. Solo cambia tu vista en este negocio.",
    restore: "Restaurar orden predeterminado",
    moveUp: (name: string) => `Subir ${name}`,
    moveDown: (name: string) => `Bajar ${name}`,
    drag: (name: string) => `Arrastrar ${name}`,
    savedLocal: "Se guarda en este navegador mientras el Inicio personalizado está en vista previa.",
    sections: { work: "Resumen del negocio", month: "Finanzas por mes", money: "Cobros y pagos" },
    continue: "Continuar trabajando",
    seeAll: "Ver todo",
    review: "Revisar",
    resolve: "Resolver",
    open: "Abrir",
    untitled: "Documento sin nombre",
    allClearTitle: "Todo al día",
    allClearBody: "No hay documentos esperando por ti.",
    edited: "Editado",
    recentKinds: { invoice_draft: "Borrador de factura", record: "Registro", receipt: "Documento" },
    setupTitle: "Configurar negocio",
    setupProgress: (done: number, total: number) => `${done} de ${total} listos`,
    setupLead: "Completa estos pasos para empezar a recibir y revisar documentos.",
    setupRemaining: (left: number) => (left === 1 ? "Falta 1 paso" : `Faltan ${left} pasos`),
    setupOptional: "Opcional",
    setupSeeAll: "Ver todos los pasos",
    steps: {
      created: { title: "Crear el negocio", body: "Nombre y país de operación." },
      fiscal_identity: { title: "Agrega el RNC o la cédula", body: "Identifica a este negocio en sus registros y reportes." },
      receiving_address: { title: "Activa el correo de recepción", body: "Reenvía facturas y recibos a una dirección propia." },
      receipt_reading: { title: "Activa la lectura de recibos", body: "Cuadrao prepara los datos para que tú los revises." },
      team: { title: "Invita al equipo", body: "Da acceso al contador o al equipo." },
      whatsapp: { title: "Conecta WhatsApp", body: "Envía documentos desde tu teléfono." },
      invoicing: { title: "Configura la facturación", body: "Prepara las facturas electrónicas." },
    } as Record<SetupStepKey, { title: string; body: string }>,
  },
  en: {
    today: "Business overview",
    recordsToReview: (n: number) => (n === 1 ? "1 record to review" : `${n} records to review`),
    invoiceDrafts: (n: number) => (n === 1 ? "1 invoice draft" : `${n} invoice drafts`),
    needs: "Needs attention",
    loading: "Loading the Inbox",
    needsFailed: "We couldn't load what needs attention",
    needsFailedBody: "Your documents are saved. Check your connection and try again.",
    reviewCountFailed: "We couldn't load how many records await review",
    retry: "Try again",
    showing: (shown: number, total: number) => `Showing ${shown} of ${total}`,
    customize: "Customize Home",
    customizeLead: "Change the order of your Home's sections. It only changes your view of this business.",
    restore: "Restore default order",
    moveUp: (name: string) => `Move ${name} up`,
    moveDown: (name: string) => `Move ${name} down`,
    drag: (name: string) => `Drag ${name}`,
    savedLocal: "Saved in this browser while the customized Home is in preview.",
    sections: { work: "Business overview", month: "Monthly finances", money: "Collections and payments" },
    continue: "Continue working",
    seeAll: "See all",
    review: "Review",
    resolve: "Resolve",
    open: "Open",
    untitled: "Untitled document",
    allClearTitle: "All caught up",
    allClearBody: "No documents are waiting for you.",
    edited: "Edited",
    recentKinds: { invoice_draft: "Invoice draft", record: "Record", receipt: "Document" },
    setupTitle: "Set up business",
    setupProgress: (done: number, total: number) => `${done} of ${total} done`,
    setupLead: "Finish these steps to start receiving and reviewing documents.",
    setupRemaining: (left: number) => (left === 1 ? "1 step left" : `${left} steps left`),
    setupOptional: "Optional",
    setupSeeAll: "See all steps",
    steps: {
      created: { title: "Create the business", body: "Name and country of operation." },
      fiscal_identity: { title: "Add the RNC or cédula", body: "Identifies this business in its records and reports." },
      receiving_address: { title: "Turn on the receiving email", body: "Forward invoices and receipts to its own address." },
      receipt_reading: { title: "Turn on receipt reading", body: "Cuadrao prepares the details for you to review." },
      team: { title: "Invite the team", body: "Give the accountant or team access." },
      whatsapp: { title: "Connect WhatsApp", body: "Send documents from your phone." },
      invoicing: { title: "Set up invoicing", body: "Prepare electronic invoices." },
    } as Record<SetupStepKey, { title: string; body: string }>,
  },
} as const;

type Copy = (typeof COPY)["es"] | (typeof COPY)["en"];

const STEP_ICON: Record<SetupStepKey, Icon> = { created: Briefcase, fiscal_identity: IdentificationCard, receiving_address: CHANNEL_ICON.email, receipt_reading: Scan, team: UsersThree, whatsapp: CHANNEL_ICON.whatsapp, invoicing: SCREEN_ICON.invoicing };
const STEP_TARGET: Record<SetupStepKey, BusinessPanelState> = {
  created: { kind: "business", tab: "datos" }, fiscal_identity: { kind: "business", tab: "datos" }, receiving_address: { kind: "business", tab: "correo" },
  receipt_reading: { kind: "business", tab: "correo" }, team: { kind: "business", tab: "equipo" }, whatsapp: { kind: "business", tab: "correo" }, invoicing: { kind: "invoicing" },
};
// The shared Business card (cardClass), without its padding, so the overview and Finanzas below read as one system.
// Read at render: business-ui sits in an import cycle with this module, so it is not ready at load.
const surface = () => cardClass.replace(/\bp-5\b/, "").trim();
const MUTED = "text-[#56635e] dark:text-white/70";
const ROW = `flex min-h-11 w-full items-center gap-3 rounded-item px-4 py-4 text-left transition-colors duration-[80ms] hover:bg-black/[0.03] dark:hover:bg-white/[0.04] ${FOCUS_RING}`;

function useCopy(): Copy {
  const { i18n } = useTranslation();
  return COPY[(i18n.resolvedLanguage ?? resolveLanguage({})) === "en" ? "en" : "es"];
}

/** A compact neutral ring with `n / n` in its center (Guide readiness rules). */
function ProgressRing({ done, total, label }: { done: number; total: number; label: string }) {
  const r = 19; const c = 2 * Math.PI * r;
  return (
    <span role="img" aria-label={label} className="relative inline-flex h-11 w-11 shrink-0 items-center justify-center">
      <svg viewBox="0 0 44 44" className="absolute inset-0" aria-hidden="true">
        <circle cx="22" cy="22" r={r} fill="none" strokeWidth="3" className="stroke-black/10 dark:stroke-white/15" />
        <circle cx="22" cy="22" r={r} fill="none" strokeWidth="3" strokeLinecap="round" strokeDasharray={`${(done / total) * c} ${c}`} transform="rotate(-90 22 22)" className="stroke-[#172b26] dark:stroke-white" />
      </svg>
      <span aria-hidden="true" className="text-[12px] font-medium tabular-nums">{done}/{total}</span>
    </span>
  );
}

/**
 * A list panel: the whole panel takes the soft header tint, a header row (icon, title, count, one action)
 * over a faint hairline, then rows as their own white cards. 16px of inner padding is at least the panel's
 * radius, so the row cards keep their own corner step.
 */
function Section({ title, icon: HeadIcon, count, meta, action, children, footer, testId }: { title: string; icon?: LucideIcon; count?: number | null; meta?: string; action?: ReactNode; children?: ReactNode; footer?: ReactNode; testId?: string }) {
  return (
    <section data-testid={testId} className={`${surface()} overflow-hidden bg-[color:var(--surface-header)]`}>
      <header className="flex min-h-12 flex-wrap items-center gap-x-2 gap-y-1 border-b border-[color:var(--surface-divider)] px-5 py-1.5">
        {HeadIcon ? <HeadIcon className={`h-[18px] w-[18px] shrink-0 ${MUTED}`} aria-hidden="true" /> : null}
        <h3 className="font-display text-[17px] font-medium text-[#172b26] dark:text-white">{title}</h3>
        {count != null ? <span className="rounded-full border border-[color:var(--surface-divider)] bg-white px-2 text-[13px] tabular-nums text-[#56635e] dark:bg-white/[0.06] dark:text-white/70">{count}</span> : null}
        {meta ? <span className={`text-[14px] ${MUTED}`}>{meta}</span> : null}
        <span className="ml-auto">{action}</span>
      </header>
      {children ? <div className="p-4">{children}</div> : null}
      {footer}
    </section>
  );
}

/** A row card: icon chip, bold title with an optional tag, a date pill, then the row's verb. The whole card is the target. */
function RowCard({ Icon, title, tag, date, verb, onOpen }: { Icon: Icon | LucideIcon; title: string; tag?: ReactNode; date: string; verb?: string; onOpen: () => void }) {
  return (
    <button type="button" onClick={onOpen} className={`group flex min-h-14 w-full items-center gap-3 rounded-item border border-[color:var(--surface-divider)] bg-white px-4 py-2.5 text-left transition-colors duration-[80ms] hover:border-[#7d8a84] focus-visible:border-[#7d8a84] dark:bg-[#24282b] dark:hover:border-white/40 ${FOCUS_RING}`}>
      <span aria-hidden="true" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[color:var(--surface-divider)] bg-[var(--cuadrao-cream)] text-[#56635e] dark:bg-white/[0.06] dark:text-white/70"><Icon size={16} /></span>
      <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
        <span className="min-w-0 truncate text-[16px] font-medium text-[#172b26] dark:text-white">{title}</span>
        {tag}
      </span>
      <span className="shrink-0 rounded-full border border-[color:var(--surface-divider)] bg-white px-2.5 py-0.5 text-[13px] text-[#56635e] dark:bg-white/[0.06] dark:text-white/70">{date}</span>
      {verb ? <span className="hidden shrink-0 items-center gap-0.5 text-[14px] font-medium text-[var(--cuadrao-green)] tablet:inline-flex">{verb}<ChevronRight className="h-4 w-4" aria-hidden="true" /></span> : <ChevronRight className={`h-4 w-4 shrink-0 ${MUTED}`} aria-hidden="true" />}
    </button>
  );
}

const TAG = "rounded-mark px-1.5 py-0.5 text-[13px] font-medium";

/** `?attention=empty`, `?setup=new`: sample states for the local design preview only, never a real Business. */
const sampleParam = (name: string) => process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true" && typeof window !== "undefined" ? new URLSearchParams(window.location.search).get(name) : null;
const SKELETON = "bg-black/[0.06] dark:bg-white/[0.08]";

/**
 * A count that lives on another screen, at the foot of a list: Registros waiting for review, invoice drafts.
 * It reads as a total, not an item, so it sits under the rows on its own hairline and never joins the list's count.
 */
function SummaryRow({ Icon, label, verb, onOpen, testId }: { Icon: LucideIcon; label: string; verb: string; onOpen: () => void; testId: string }) {
  return (
    <button type="button" data-testid={testId} onClick={onOpen} className={`flex min-h-12 w-full items-center gap-3 border-t border-[color:var(--surface-divider)] px-5 text-left transition-colors duration-[80ms] hover:bg-black/[0.03] dark:hover:bg-white/[0.04] ${FOCUS_RING}`}>
      <Icon aria-hidden="true" className={`h-[18px] w-[18px] shrink-0 ${MUTED}`} />
      <span className="min-w-0 flex-1 truncate text-[15px] font-medium text-[#172b26] dark:text-white">{label}</span>
      <span className="inline-flex shrink-0 items-center gap-0.5 text-[14px] font-medium text-[var(--cuadrao-green)]">{verb}<ChevronRight className="h-4 w-4" aria-hidden="true" /></span>
    </button>
  );
}

/** The review count is on its way: a quiet skeleton line where the summary row will stand. */
function CountLoading({ label }: { label: string }) {
  return (
    <div role="status" aria-busy="true" className="flex min-h-12 items-center gap-3 border-t border-[color:var(--surface-divider)] px-5">
      <span className="sr-only">{label}</span>
      <span aria-hidden="true" className={`h-[18px] w-[18px] shrink-0 animate-pulse rounded-full motion-reduce:animate-none ${SKELETON}`} />
      <span aria-hidden="true" className={`h-4 w-2/5 animate-pulse rounded-mark motion-reduce:animate-none ${SKELETON}`} />
    </div>
  );
}

/** The review count could not be read: say so with its reference and a way to ask again, never a zero. */
function CountFailed({ c, reference, retry }: { c: Copy; reference: string; retry: () => void }) {
  return (
    <div data-testid="home-records-to-review-failed" role="alert" className="flex min-h-12 flex-wrap items-center gap-x-3 gap-y-1 border-t border-[color:var(--surface-divider)] px-5 py-2">
      <CircleAlert aria-hidden="true" className="h-[18px] w-[18px] shrink-0 text-[#9e2f39] dark:text-[#ec9aa0]" />
      <span className="min-w-0 flex-1 text-[15px] text-[#172b26] dark:text-white">{c.reviewCountFailed}</span>
      <ReferenceCode reference={reference} />
      <button type="button" className={`${quietButtonClass} text-[14px]`} onClick={retry}>{c.retry}</button>
    </div>
  );
}

/** Rows each list previews, so the month's figures begin in view on a laptop. Bandeja ("Ver todo") holds every waiting row; older work stays in its own screen. */
const PREVIEW_ROWS = { needs: 4, recent: 3 } as const;

/**
 * Scope: every Bandeja document waiting on a person, problems first, then ready to review. The two server
 * buckets overlap (a duplicate can be both), so their counts are never added: the total needs one union
 * count from the server (MISSING: `waiting_on_person_count`). The local preview loads every fixture row, so
 * there the union of loaded rows is exact; elsewhere the count stays hidden until the server sends it.
 */
function NeedsAttention({ c, toReview: liveToReview, retryCount }: { c: Copy; toReview: ReviewCount; retryCount: () => void }) {
  const { records, openPanel, source, reload } = useBusiness();
  const { t, i18n } = useTranslation();
  const stateWord = useReceiptStateWord();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const forceEmpty = sampleParam("attention") === "empty";
  const inbox = forceEmpty ? [] : records.inbox ?? [];
  const problems = inbox.filter((r) => r.bandeja?.con_problema);
  const review = inbox.filter((r) => r.bandeja?.por_revisar && !r.bandeja?.con_problema);
  const all: ReceiptSummary[] = [...problems, ...review];
  const rows = all.slice(0, PREVIEW_ROWS.needs);
  const total = source.mode === "fixture" && records.inbox ? all.length : (records.receiptActivity as { waiting_on_person_count?: number } | null | undefined)?.waiting_on_person_count ?? null;
  const ready = records.inbox !== null || forceEmpty;
  // Registros keeps its own review queue (GET /business/reports overview, this month). It is a different queue from
  // Bandeja's, so it is a summary row under the list, never added to the count. MISSING: Registros opened on that filter.
  const toReview: ReviewCount = forceEmpty ? { kind: "ready", value: 0 } : liveToReview;
  let footer: ReactNode = null;
  if (toReview.kind === "ready" && toReview.value > 0) footer = <SummaryRow testId="home-records-to-review" Icon={FileSearch} label={c.recordsToReview(toReview.value)} verb={c.review} onOpen={() => openPanel({ kind: "transactions" })} />;
  else if (toReview.kind === "failed") footer = <CountFailed c={c} reference={toReview.reference} retry={retryCount} />;
  else if (toReview.kind === "loading") footer = <CountLoading label={c.loading} />;
  if (records.error && !forceEmpty) {
    // The Business did not load: say so with the server's reference and a way to try again, never an endless skeleton.
    const reference = records.failureReference ?? records.serverReference;
    return (
      <Section title={c.needs} icon={CircleAlert} testId="home-needs-attention">
        <EmptyState kind="error" compact title={c.needsFailed} body={records.refused ? undefined : c.needsFailedBody} action={records.refused ? undefined : { label: c.retry, run: reload }} />
        {reference ? <div className="flex justify-center pb-2"><ReferenceCode reference={reference} /></div> : null}
      </Section>
    );
  }
  // Bandeja still loading, or nothing in it while the review count is still on its way: the card as it will stand,
  // header and four row cards, never an empty panel and never "Todo al día" before the server has said so.
  if (!ready || (rows.length === 0 && toReview.kind === "loading")) {
    return (
      <Section title={c.needs} icon={CircleAlert} testId="home-needs-attention">
        <ul role="status" aria-busy="true" className="space-y-2">
          <li className="sr-only">{c.loading}</li>
          {[0, 1, 2, 3].map((index) => (
            <li key={index} aria-hidden="true" className="flex min-h-14 animate-pulse items-center gap-3 rounded-item border border-[color:var(--surface-divider)] bg-white px-4 py-2.5 motion-reduce:animate-none dark:bg-[#24282b]">
              <span className={`h-8 w-8 shrink-0 rounded-full ${SKELETON}`} />
              <span className={`h-4 w-2/5 rounded-mark ${SKELETON}`} />
              <span className={`ml-auto h-6 w-20 rounded-full ${SKELETON}`} />
            </li>
          ))}
        </ul>
      </Section>
    );
  }
  if (rows.length === 0) {
    // Nothing waiting in Bandeja and the count is a number: a short settled line, never an empty panel the height of five rows.
    return <Section title={c.needs} icon={CircleAlert} testId="home-needs-attention" footer={footer}>{footer ? null : <EmptyState kind="done" settled title={c.allClearTitle} body={c.allClearBody} />}</Section>;
  }
  return (
    <Section title={c.needs} icon={CircleAlert} testId="home-needs-attention" footer={footer} count={total} meta={total !== null && total > rows.length ? c.showing(rows.length, total) : undefined} action={<button type="button" className={`${quietButtonClass} text-[14px]`} onClick={() => openPanel({ kind: "inbox" })}>{c.seeAll}</button>}>
      <ul className="space-y-2">
        {rows.map((receipt) => {
          const Channel = CHANNEL_ICON[receipt.channel as keyof typeof CHANNEL_ICON] ?? CHANNEL_ICON.web;
          const problem = Boolean(receipt.bandeja?.con_problema);
          // The verb says what the record screen lets you do: fix a problem, review a prepared record, or just look.
          const verb = problem ? c.resolve : receipt.bandeja?.por_revisar ? c.review : c.open;
          const tag = problem
            ? <span className={`${TAG} inline-flex items-center gap-1 bg-[#f6dfe0] text-[#9e2f39] dark:bg-[#4a2a2f] dark:text-[#ec9aa0]`}><span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />{t(`business.attention_short.${receipt.attention ?? "other"}`)}</span>
            : <span className={`${TAG} bg-black/5 text-[#56635e] dark:bg-white/10 dark:text-white/70`}>{stateWord(receipt)}</span>;
          return <li key={receipt.id}><RowCard Icon={Channel} title={receipt.merchant || receipt.filename || c.untitled} tag={tag} date={formatRelativeTime(receipt.received_at, locale)} verb={verb} onOpen={() => openPanel({ kind: "receipt", receiptId: receipt.id, list: "inbox" })} /></li>;
        })}
      </ul>
    </Section>
  );
}

function ContinueWorking({ c, recents, drafts }: { c: Copy; recents: readonly RecentWork[]; drafts: number }) {
  const { openPanel } = useBusiness();
  const { i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const icon: Record<string, Icon> = { invoice_draft: SCREEN_ICON.invoicing, record: SCREEN_ICON.transactions, receipt: SCREEN_ICON.inbox };
  // Invoice drafts are unfinished work, so they sit here (useHomeCounts). MISSING: Facturación opened on its drafts stage.
  const footer = drafts > 0 ? <SummaryRow testId="home-invoice-drafts" Icon={FilePenLine} label={c.invoiceDrafts(drafts)} verb={c.open} onOpen={() => openPanel({ kind: "invoicing" })} /> : null;
  return (
    <Section title={c.continue} icon={PenLine} footer={footer}>
      <ul className="space-y-2">
        {recents.slice(0, PREVIEW_ROWS.recent).map((item) => (
          <li key={item.id}>
            <RowCard Icon={icon[item.kind]} title={item.label} tag={<span className={`${TAG} bg-black/5 text-[#56635e] dark:bg-white/10 dark:text-white/70`}>{c.recentKinds[item.kind]}</span>} date={formatRelativeTime(item.edited_at, locale)} onOpen={() => openPanel(item.target.kind === "draft" ? { kind: "draft", draftId: item.target.id, list: "transactions" } : { kind: "invoicing" })} />
          </li>
        ))}
      </ul>
    </Section>
  );
}

function StepRow({ step, c, onOpen }: { step: SetupStep; c: Copy; onOpen: (step: SetupStep) => void }) {
  const StepIcon = STEP_ICON[step.key];
  const words = c.steps[step.key];
  if (step.done) {
    // A finished step is a quiet row: muted title and a check, no description.
    return (
      <button type="button" onClick={() => onOpen(step)} className={`${ROW} ${MUTED}`}>
        <StepIcon size={20} aria-hidden="true" className="shrink-0" />
        <span className="min-w-0 flex-1 text-[16px]">{words.title}</span>
        <Check size={18} weight="bold" aria-label={c.setupProgress(1, 1)} className="shrink-0 text-[var(--cuadrao-green)]" />
      </button>
    );
  }
  return (
    <button type="button" onClick={() => onOpen(step)} className={`${surface()} ${ROW} !px-4 !py-4`}>
      <StepIcon size={20} aria-hidden="true" className="shrink-0 self-start text-[#172b26] dark:text-white" />
      <span className="min-w-0 flex-1"><span className="block text-[16px] font-medium">{words.title}</span><span className={`mt-0.5 block text-[14px] ${MUTED}`}>{words.body}</span></span>
      <ChevronRight aria-hidden="true" className={`h-4 w-4 shrink-0 ${MUTED}`} />
    </button>
  );
}

/** Setup lives apart from the work: a compact entry on Inicio, the steps in a side panel (a full sheet on a phone). */
function GuidedSetup({ c, stage }: { c: Copy; stage: "active" | "new" }) {
  const { openPanel, chosen, source } = useBusiness();
  const [open, setOpen] = useState(false);
  const steps = SETUP_STATE[stage];
  const required = steps.filter((s) => s.required);
  const done = required.filter((s) => s.done).length;
  // Every step is a configuration action (details, reception, access, invoicing), so setup shows only to people
  // who may configure this Business; the rest see the same Inicio without it. Optional steps never count.
  if (done === required.length || !canManageBusiness(chosen, source.mode === "live")) return null;
  const progress = c.setupProgress(done, required.length);
  const go = (step: SetupStep) => { setOpen(false); openPanel(STEP_TARGET[step.key]); };
  const panel = open ? (
    <AdaptivePanel title={c.setupTitle} summary={progress} onClose={() => setOpen(false)} closeLabel="Cerrar" width="md" snaps={["full"]} initialSnap="full">
      <div className="space-y-3 px-5 pb-6 pt-2" data-testid="home-setup-panel">
        <p className={`text-[16px] ${MUTED}`}>{c.setupLead}</p>
        {required.map((step) => <StepRow key={step.key} step={step} c={c} onOpen={go} />)}
        <h3 className={`pt-3 text-[14px] font-medium ${MUTED}`}>{c.setupOptional}</h3>
        {steps.filter((s) => !s.required).map((step) => <StepRow key={step.key} step={step} c={c} onOpen={go} />)}
      </div>
    </AdaptivePanel>
  ) : null;
  if (stage === "new") {
    // A brand-new Business: setup is the main job, so it leads Inicio with its open steps.
    return (
      <section className={`${surface()} p-5`} data-testid="home-setup-new">
        <div className="flex items-start gap-4">
          <span className="min-w-0 flex-1"><h3 className="font-display text-[21px] font-medium">{c.setupTitle}</h3><p className={`mt-1 text-[16px] ${MUTED}`}>{c.setupLead}</p></span>
          <ProgressRing done={done} total={required.length} label={progress} />
        </div>
        <div className="mt-4 space-y-3">{required.filter((s) => !s.done).map((step) => <StepRow key={step.key} step={step} c={c} onOpen={go} />)}</div>
        <button type="button" className={`${quietButtonClass} mt-2 text-[14px]`} onClick={() => setOpen(true)}>{c.setupSeeAll}</button>
        {panel}
      </section>
    );
  }
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} data-testid="home-setup-entry" aria-haspopup="dialog" className={`${surface()} flex min-h-14 w-full items-center gap-3 px-3 py-[5px] text-left transition-colors duration-[80ms] hover:bg-white dark:hover:bg-[#25292c] ${FOCUS_RING}`}>
        <ProgressRing done={done} total={required.length} label={progress} />
        {/* One line: the ring carries "n de 4" (and its label), the steps left sit by the chevron. */}
        <span className="min-w-0 flex-1 truncate text-[16px] font-medium">{c.setupTitle}</span>
        <span className={`shrink-0 text-[14px] ${MUTED}`}>{c.setupRemaining(required.length - done)}</span>
        <ChevronRight aria-hidden="true" className={`h-4 w-4 shrink-0 ${MUTED}`} />
      </button>
      {panel}
    </>
  );
}

export type HomeSectionKey = "work" | "month" | "money";
export const HOME_DEFAULT_ORDER: readonly HomeSectionKey[] = ["work", "month", "money"];

/**
 * The person's own section order for this Business. MISSING on the server: a per-person, per-Business
 * `home_section_order` preference (like `table_density` on /me). Until then the preview keeps it in this browser.
 */
export function useHomeOrder(userId: string | null | undefined, businessId: string | null | undefined) {
  const key = `${userId ?? "anon"}:${businessId ?? "none"}`;
  const all = (): Record<string, HomeSectionKey[]> => {
    try { return JSON.parse(readStored("cuadrao:home_section_order:v1") ?? "{}") ?? {}; } catch { return {}; }
  };
  const read = (): HomeSectionKey[] => {
    const saved = all()[key];
    return Array.isArray(saved) && saved.length === HOME_DEFAULT_ORDER.length && HOME_DEFAULT_ORDER.every((k) => saved.includes(k)) ? saved : [...HOME_DEFAULT_ORDER];
  };
  const [state, setState] = useState<{ key: string; order: HomeSectionKey[] }>(() => ({ key, order: typeof window === "undefined" ? [...HOME_DEFAULT_ORDER] : read() }));
  const order = state.key === key ? state.order : read();
  const save = (next: HomeSectionKey[]) => {
    setState({ key, order: next });
    writeStored("cuadrao:home_section_order:v1", JSON.stringify({ ...all(), [key]: next }));
  };
  return { order, save, isDefault: order.join() === HOME_DEFAULT_ORDER.join() };
}

/** Reorders whole sections only: move up or down, or drag; the greeting and Business context stay first. */
export function HomeCustomize({ order, onChange, isDefault }: { order: HomeSectionKey[]; onChange: (next: HomeSectionKey[]) => void; isDefault: boolean }) {
  const c = useCopy();
  const [open, setOpen] = useState(false);
  const [dragging, setDragging] = useState<HomeSectionKey | null>(null);
  const move = (from: number, to: number) => {
    if (to < 0 || to >= order.length) return;
    const next = [...order]; const [item] = next.splice(from, 1); next.splice(to, 0, item); onChange(next);
  };
  return (
    <>
      <button type="button" data-testid="home-customize" onClick={() => setOpen(true)} aria-haspopup="dialog" className={`${quietButtonClass} text-[14px]`}>
        <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />{c.customize}
      </button>
      {open ? (
        <AdaptivePanel title={c.customize} onClose={() => setOpen(false)} closeLabel="Cerrar" width="sm">
          <div className="space-y-4 px-5 pb-6 pt-2" data-testid="home-customize-panel">
            <p className={`text-[16px] ${MUTED}`}>{c.customizeLead}</p>
            <ol className="space-y-2">
              {order.map((key, index) => {
                const name = c.sections[key];
                return (
                  <li key={key} draggable onDragStart={() => setDragging(key)} onDragEnd={() => setDragging(null)} onDragOver={(event) => event.preventDefault()} onDrop={() => { if (dragging) move(order.indexOf(dragging), index); setDragging(null); }} data-section={key} className={`${surface()} flex min-h-14 items-center gap-2 px-2 ${dragging === key ? "opacity-60" : ""}`}>
                    <span aria-hidden="true" title={c.drag(name)} className={`flex h-11 w-8 shrink-0 cursor-grab items-center justify-center ${MUTED}`}><GripVertical className="h-4 w-4" /></span>
                    <span className="min-w-0 flex-1 text-[16px]">{name}</span>
                    <button type="button" aria-label={c.moveUp(name)} disabled={index === 0} onClick={() => move(index, index - 1)} className={`inline-flex h-11 w-11 items-center justify-center rounded-full disabled:opacity-30 hover:bg-black/5 dark:hover:bg-white/10 ${FOCUS_RING}`}><ArrowUp className="h-4 w-4" aria-hidden="true" /></button>
                    <button type="button" aria-label={c.moveDown(name)} disabled={index === order.length - 1} onClick={() => move(index, index + 1)} className={`inline-flex h-11 w-11 items-center justify-center rounded-full disabled:opacity-30 hover:bg-black/5 dark:hover:bg-white/10 ${FOCUS_RING}`}><ArrowDown className="h-4 w-4" aria-hidden="true" /></button>
                  </li>
                );
              })}
            </ol>
            <button type="button" disabled={isDefault} onClick={() => onChange([...HOME_DEFAULT_ORDER])} className={`${quietButtonClass} text-[14px]`}><RotateCcw className="h-4 w-4" aria-hidden="true" />{c.restore}</button>
            <p className={`text-[14px] ${MUTED}`}>{c.savedLocal}</p>
          </div>
        </AdaptivePanel>
      ) : null}
    </>
  );
}

/** A brand-new Business leads with setup; it stays above the movable sections. */
export function HomeSetupLead() {
  const c = useCopy();
  const samples = useSampleBusiness();
  return samples && sampleParam("setup") === "new" ? <GuidedSetup c={c} stage="new" /> : null;
}


export function HomeWork() {
  const c = useCopy();
  const counts = useHomeCounts();
  // Recent work and setup progress have no endpoint yet (MISSING: GET /business/recents, GET /business/setup): the
  // local preview shows their samples, a live Business does not show them at all rather than invent them.
  const samples = useSampleBusiness();
  const setup = samples && sampleParam("setup") !== "new";
  const recents = samples ? RECENT_WORK : [];
  const drafts = counts.drafts ?? 0;
  const keepWorking = recents.length > 0 || drafts > 0;
  // Two columns only when each has room (the content box, not the window, decides) and the right one has something.
  // Both columns end on one line: the cards keep their content height, and Continuar trabajando pins to the bottom.
  return (
    <section className="@container space-y-4" aria-labelledby="home-work-title">
    <div className="flex min-h-11 items-center">
      <h2 id="home-work-title" className="font-display text-[21px] font-medium text-[#172b26] dark:text-white">{c.today}</h2>
    </div>
    <div data-testid="home-work" className={setup || keepWorking ? "space-y-6 @min-[60rem]:grid @min-[60rem]:grid-cols-[minmax(0,11fr)_minmax(0,9fr)] @min-[60rem]:gap-6 @min-[60rem]:space-y-0" : ""}>
      <div><NeedsAttention c={c} toReview={counts.toReview} retryCount={counts.retry} /></div>
      {setup || keepWorking ? <div className="flex flex-col justify-between gap-4">
        {setup ? <GuidedSetup c={c} stage="active" /> : null}
        {keepWorking ? <ContinueWorking c={c} recents={recents} drafts={drafts} /> : null}
      </div> : null}
    </div>
    </section>
  );
}
