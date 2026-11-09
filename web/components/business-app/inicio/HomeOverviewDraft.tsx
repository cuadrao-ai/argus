"use client";

// Inicio's first layer, Resumen del negocio: everything waiting in the Bandeja and where to continue, plus
// Personalizar Inicio. Draft copy lives here (es-419 first) until the copy pass moves it to the locale files; the
// setup guide (SetupGuide) sits above it and its copy already lives there.

import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { resolveLanguage } from "@/lib/language-features";
import type { Icon } from "@phosphor-icons/react";
import { ArrowDown, ArrowUp, ChevronRight, CircleAlert, FilePenLine, GripVertical, PenLine, RotateCcw, SlidersHorizontal, type LucideIcon } from "lucide-react";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { readStored, writeStored } from "@/lib/browser-storage";
import { invoicingShown, useBusiness } from "../BusinessWorkspace";
import { formatRelativeTime } from "../business-format";
import { inboxCount } from "../inbox-count";
import { EmptyState } from "../foundation/EmptyState";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { CHANNEL_ICON } from "../foundation/channel-icons";
import { FOCUS_RING } from "../foundation/presentation";
import { cardClass, quietButtonClass } from "../business-ui";
import { SCREEN_ICON } from "../nav-glyphs";
import { useReceiptStateWord } from "../receipt-state-word";
import { receptionDocumentTitle, receptionRows, receptionTarget, type ReceptionRow } from "../recepcion/reception-model";
import { RECENT_WORK, type RecentWork } from "./home-draft-data";
import { useHomeCounts, useSampleBusiness } from "./useHomeCounts";

const COPY = {
  es: {
    today: "Resumen del negocio",
    invoiceDrafts: (n: number) => (n === 1 ? "1 factura en borrador" : `${n} facturas en borrador`),
    needs: "Necesita atención",
    loading: "Cargando la Bandeja",
    needsFailed: "No pudimos cargar lo que necesita atención",
    needsFailedBody: "Tus documentos están guardados. Revisa tu conexión e inténtalo otra vez.",
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
  },
  en: {
    today: "Business overview",
    invoiceDrafts: (n: number) => (n === 1 ? "1 invoice draft" : `${n} invoice drafts`),
    needs: "Needs attention",
    loading: "Loading the Inbox",
    needsFailed: "We couldn't load what needs attention",
    needsFailedBody: "Your documents are saved. Check your connection and try again.",
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
  },
} as const;

type Copy = (typeof COPY)["es"] | (typeof COPY)["en"];

// The shared Business card (cardClass), without its padding, so the overview and Finanzas below read as one system.
// Read at render: business-ui sits in an import cycle with this module, so it is not ready at load.
const surface = () => cardClass.replace(/\bp-5\b/, "").trim();
const MUTED = "text-[#56635e] dark:text-white/70";

function useCopy(): Copy {
  const { i18n } = useTranslation();
  return COPY[(i18n.resolvedLanguage ?? resolveLanguage({})) === "en" ? "en" : "es"];
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
        {count != null ? <span data-testid={testId ? `${testId}-count` : undefined} className="rounded-full border border-[color:var(--surface-divider)] bg-white px-2 text-[13px] tabular-nums text-[#56635e] dark:bg-white/[0.06] dark:text-white/70">{count}</span> : null}
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
 * A count that lives on another screen, at the foot of a list: invoice drafts. It reads as a total, not an item, so
 * it sits under the rows on its own hairline and never joins the list's count.
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

/** Rows each list previews, so the month's figures begin in view on a laptop. Bandeja ("Ver todo") holds every waiting row; older work stays in its own screen. */
const PREVIEW_ROWS = { needs: 4, recent: 3 } as const;

/** A row that needs a fix before anything else: a receipt with a problem, or an email that brought no receipt. */
const problemRow = (row: ReceptionRow) => (row.kind === "receipt" ? Boolean(row.receipt.bandeja?.con_problema) : row.kind === "email" && row.email.standing === "no_receipt");

/**
 * Scope: everything waiting in the Bandeja, mixed kinds included, problems first. The count is the server's one
 * Bandeja number, the one the sidebar shows (Lucas, 2026-11-09); "Ver todo" opens the Bandeja as it is.
 */
function NeedsAttention({ c }: { c: Copy }) {
  const { records, openPanel, reload, chosen } = useBusiness();
  const { t, i18n } = useTranslation();
  const stateWord = useReceiptStateWord();
  // Resolver and Revisar are work: a read-only person opens the same rows to look, with no verb.
  const prepares = Boolean(chosen?.capabilities?.includes("prepare"));
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const forceEmpty = sampleParam("attention") === "empty";
  const waiting = forceEmpty ? [] : receptionRows(records.inbox ?? [], records.notes ?? [], records.emails ?? []);
  const rows = [...waiting.filter(problemRow), ...waiting.filter((row) => !problemRow(row))].slice(0, PREVIEW_ROWS.needs);
  const total = forceEmpty ? 0 : inboxCount(records);
  // Rows show once their lists are in; the count shows once the server has counted, never guessed from the rows.
  const ready = forceEmpty || (records.inbox !== null && (records.notes !== null || Boolean(records.notesFailure)) && (records.emails !== null || Boolean(records.emailsFailure)) && (total !== null || waiting.length > 0));
  // The Business did not load, or the server could not count the Bandeja: say so with its reference and a way to try
  // again, never an endless skeleton and never a zero.
  if ((records.error || (total === null && records.serverReference)) && !forceEmpty) {
    const reference = records.failureReference ?? records.serverReference;
    return (
      <Section title={c.needs} icon={CircleAlert} testId="home-needs-attention">
        <EmptyState kind="error" compact title={c.needsFailed} body={records.refused ? undefined : c.needsFailedBody} action={records.refused ? undefined : { label: c.retry, run: reload }} />
        {reference ? <div className="flex justify-center pb-2"><ReferenceCode reference={reference} /></div> : null}
      </Section>
    );
  }
  // The Bandeja still loading: the card as it will stand, header and four row cards, never an empty panel and never
  // "Todo al día" before the server has said so.
  if (!ready) {
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
  if (total === 0) {
    // Nothing waiting in the Bandeja: a short settled line, never an empty panel the height of five rows.
    return <Section title={c.needs} icon={CircleAlert} testId="home-needs-attention"><EmptyState kind="done" settled title={c.allClearTitle} body={c.allClearBody} /></Section>;
  }
  const neutral = `${TAG} bg-black/5 text-[#56635e] dark:bg-white/10 dark:text-white/70`;
  const alert = (text: string) => <span className={`${TAG} inline-flex items-center gap-1 bg-[#f6dfe0] text-[#9e2f39] dark:bg-[#4a2a2f] dark:text-[#ec9aa0]`}><span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />{text}</span>;
  const titleOf = (row: ReceptionRow) => receptionDocumentTitle(row, { untitled: c.untitled, pending: t("business.reception_preview.intake_pending"), exception: t("business.reception_preview.intake_exception"), text: t("business.reception_preview.text_intake") });
  return (
    <Section title={c.needs} icon={CircleAlert} testId="home-needs-attention" count={total} meta={rows.length > 0 && total !== null && total > rows.length ? c.showing(rows.length, total) : undefined} action={<button type="button" data-testid="home-needs-see-all" className={`${quietButtonClass} text-[14px]`} onClick={() => openPanel({ kind: "inbox" })}>{c.seeAll}</button>}>
      {rows.length ? <ul className="space-y-2">
        {rows.map((row) => {
          const problem = problemRow(row);
          // The verb says what the record screen lets you do: fix a problem, review what is ready, or just look.
          const verb = !prepares ? undefined : problem ? c.resolve : row.kind === "note" || (row.kind === "receipt" && row.receipt.bandeja?.por_revisar) ? c.review : c.open;
          const tag = row.kind === "receipt"
            ? problem ? alert(t(`business.attention_short.${row.receipt.attention ?? "other"}`)) : <span className={neutral}>{stateWord(row.receipt)}</span>
            : row.kind === "note" ? <span className={neutral}>{t("business.inbox.row_note")}</span>
            : problem ? alert(t("business.reception_preview.source_email")) : <span className={neutral}>{t("business.reception_preview.source_email")}</span>;
          return <li key={`${row.kind}:${row.id}`} data-kind={row.kind}><RowCard Icon={CHANNEL_ICON[row.source]} title={titleOf(row)} tag={tag} date={formatRelativeTime(row.receivedAt, locale)} verb={verb} onOpen={() => openPanel(receptionTarget(row))} /></li>;
        })}
      </ul> : null}
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

export type HomeSectionKey = "work" | "month" | "money";
export const HOME_DEFAULT_ORDER: readonly HomeSectionKey[] = ["work", "month", "money"];

/**
 * The sections Inicio shows, in the person's saved order: a saved section that is not shown (Cobros y pagos while
 * settlement is off) drops out, and a shown one the saved order lacks follows in its default place at the end.
 */
export function homeSectionOrder(saved: unknown, shown: readonly HomeSectionKey[]): HomeSectionKey[] {
  const kept = Array.isArray(saved) ? HOME_DEFAULT_ORDER.filter((key) => shown.includes(key) && saved.includes(key)).sort((a, b) => saved.indexOf(a) - saved.indexOf(b)) : [];
  return [...kept, ...HOME_DEFAULT_ORDER.filter((key) => shown.includes(key) && !kept.includes(key))];
}

/**
 * The whole saved order after the person reorders what is shown: each shown section takes the next place in `next`,
 * and a hidden one (Cobros y pagos while settlement is off) keeps its own place for when it shows again.
 */
export function savedSectionOrder(saved: readonly HomeSectionKey[], next: readonly HomeSectionKey[]): HomeSectionKey[] {
  const shown = [...next];
  return homeSectionOrder(saved, HOME_DEFAULT_ORDER).map((key) => (next.includes(key) ? shown.shift()! : key));
}

/**
 * The person's own section order for this Business. MISSING on the server: a per-person, per-Business
 * `home_section_order` preference (like `table_density` on /me). Until then the preview keeps it in this browser.
 */
export function useHomeOrder(userId: string | null | undefined, businessId: string | null | undefined, shown: readonly HomeSectionKey[] = HOME_DEFAULT_ORDER) {
  const key = `${userId ?? "anon"}:${businessId ?? "none"}`;
  const defaults = homeSectionOrder(undefined, shown);
  const all = (): Record<string, HomeSectionKey[]> => {
    try { return JSON.parse(readStored("cuadrao:home_section_order:v1") ?? "{}") ?? {}; } catch { return {}; }
  };
  // The state keeps every section's saved place; only the order shown leaves out what is hidden.
  const read = (): HomeSectionKey[] => homeSectionOrder(all()[key], HOME_DEFAULT_ORDER);
  const [state, setState] = useState<{ key: string; order: HomeSectionKey[] }>(() => ({ key, order: typeof window === "undefined" ? [...HOME_DEFAULT_ORDER] : read() }));
  const saved = state.key === key ? state.order : read();
  const order = homeSectionOrder(saved, shown);
  const save = (next: HomeSectionKey[]) => {
    const whole = savedSectionOrder(saved, next);
    setState({ key, order: whole });
    writeStored("cuadrao:home_section_order:v1", JSON.stringify({ ...all(), [key]: whole }));
  };
  return { order, save, defaults, isDefault: order.join() === defaults.join() };
}

/** Reorders whole sections only: move up or down, or drag; the greeting and Business context stay first. */
export function HomeCustomize({ order, defaults, onChange, isDefault }: { order: HomeSectionKey[]; defaults: readonly HomeSectionKey[]; onChange: (next: HomeSectionKey[]) => void; isDefault: boolean }) {
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
            <button type="button" disabled={isDefault} onClick={() => onChange([...defaults])} className={`${quietButtonClass} text-[14px]`}><RotateCcw className="h-4 w-4" aria-hidden="true" />{c.restore}</button>
            <p className={`text-[14px] ${MUTED}`}>{c.savedLocal}</p>
          </div>
        </AdaptivePanel>
      ) : null}
    </>
  );
}

export function HomeWork() {
  const c = useCopy();
  const counts = useHomeCounts();
  // Recent work has no endpoint yet (MISSING: GET /business/recents): the local preview shows its samples, a live
  // Business does not show it at all rather than invent it.
  const samples = useSampleBusiness();
  const { invoicing } = useBusiness();
  const recents = samples ? RECENT_WORK.filter((item) => item.target.kind !== "invoicing" || invoicingShown(invoicing)) : [];
  const drafts = counts.drafts ?? 0;
  const keepWorking = recents.length > 0 || drafts > 0;
  // Two columns only when each has room (the content box, not the window, decides) and the right one has something.
  // Both columns end on one line: the cards keep their content height, and Continuar trabajando pins to the bottom.
  return (
    <section className="@container space-y-4" aria-labelledby="home-work-title">
    <div className="flex min-h-11 items-center">
      <h2 id="home-work-title" className="font-display text-[21px] font-medium text-[#172b26] dark:text-white">{c.today}</h2>
    </div>
    <div data-testid="home-work" className={keepWorking ? "space-y-6 @min-[60rem]:grid @min-[60rem]:grid-cols-[minmax(0,11fr)_minmax(0,9fr)] @min-[60rem]:gap-6 @min-[60rem]:space-y-0" : ""}>
      <div><NeedsAttention c={c} /></div>
      {keepWorking ? <div className="flex flex-col justify-between gap-4">
        <ContinueWorking c={c} recents={recents} drafts={drafts} />
      </div> : null}
    </div>
    </section>
  );
}
