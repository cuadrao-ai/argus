"use client";

import { useEffect, useRef, useState, type ComponentProps } from "react";
import { Check, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { resolveBusinessDuplicate } from "@/lib/business-api";
import { BUSINESS_COMPARED_FIELDS, type BusinessComparedDocument, type BusinessComparedField, type BusinessDossier, type BusinessDuplicateCandidate, type BusinessDuplicateDecision } from "@/lib/business-dossier";
import { counterpartyTerm, documentFamily } from "@/lib/counterparty-term";
import { resolveLanguage } from "@/lib/language-features";
import { randomId } from "@/lib/random-id";
import { dangerButtonClass, dangerConfirmButtonClass, secondaryButtonClass, useChannelLabel } from "./business-ui";
import { formatDay, formatMoney, formatTimestamp, UNKNOWN_VALUE } from "./business-format";
import ReceiptReviewFrame from "./ReceiptReviewFrame";
import { DossierCompareDocument, type CompareSide } from "./dossier/DossierDocument";
import { DossierCard } from "./dossier/DossierParts";
import { sentByName, type SentBy } from "@/lib/sent-by";
import { useBusiness } from "./BusinessWorkspace";
import type { DossierTab } from "./dossier-attention";
import styles from "./dossier/compare.module.css";
import { StatusPill } from "./foundation/StatusChip";
import { showToast } from "./foundation/toasts";
import { DUPLICATE_KEYS as KEYS, duplicateBasisKey } from "./dossier-attention";

/**
 * Which candidate the review panel compares now, if any. A candidate the server no longer lists, another draft or a
 * document that is no longer open ends the compare view on its own.
 */
export function useDuplicateCompare(dossier: BusinessDossier | null) {
  const [shown, setShown] = useState<{ draftId: string; otherId: string } | null>(null);
  // Where focus lands once the review is back: the first enabled match, in order.
  const focusAfter = useRef<string[]>([]);
  useEffect(() => {
    if (shown || !focusAfter.current.length) return;
    const targets = focusAfter.current;
    focusAfter.current = [];
    for (const selector of targets) {
      const target = Array.from(document.querySelectorAll<HTMLElement>(selector)).find((item) => !item.matches(":disabled"));
      if (target) { target.focus(); return; }
    }
  }, [shown]);
  const close = (targets: string[]) => { focusAfter.current = targets; setShown(null); };
  const candidate = shown && dossier?.draft_id === shown.draftId && dossier.review_state === "open"
    ? dossier.duplicate_candidates?.find((item) => item.draft_id === shown.otherId) ?? null
    : null;
  return {
    candidate,
    open: (otherId: string) => { if (dossier) setShown({ draftId: dossier.draft_id, otherId }); },
    back: () => close([`[data-compare="${shown?.otherId}"]`]),
    /** A decision kept the document: the review's main action, else what the top box still asks. */
    settled: () => close(["[data-review-primary]", '[data-testid="dossier-status"] button']),
  };
}

function shownValue(field: BusinessComparedField, document: BusinessComparedDocument, locale: string): string {
  switch (field) {
    case "occurred_on": return formatDay(document.occurred_on, locale) || UNKNOWN_VALUE;
    case "amount": return formatMoney(document.amount, document.currency, locale) || document.amount || UNKNOWN_VALUE;
    default: return document[field] || UNKNOWN_VALUE;
  }
}

type Row = { field: string; label: string; values: readonly [string, string]; different?: boolean; wraps?: boolean };

function ComparisonTable({ rows, caption, origin = false }: { rows: Row[]; caption: string; origin?: boolean }) {
  const { t } = useTranslation();
  return <table className={styles.table} data-origin={origin || undefined}>
    <caption className="sr-only">{caption}</caption>
    <thead><tr>
      <th scope="col"><span className="sr-only">{t(`${KEYS}.table.field`)}</span></th>
      <th scope="col">{t(`${KEYS}.column.this`)}</th>
      <th scope="col">{t(`${KEYS}.column.saved_before`)}</th>
      <td />
    </tr></thead>
    <tbody>{rows.map(({ field, label, values, different, wraps }) => <tr key={field} data-testid={origin ? undefined : "duplicate-compare-row"} data-field={field} data-state={different == null ? undefined : different ? "different" : "same"}>
      <th scope="row">{label}</th>
      {values.map((value, side) => <td key={side} title={value} data-wrap={wraps || undefined} data-highlight={!origin && different || undefined}>{value}</td>)}
      <td className={styles.marker}>{different == null ? null : different
        ? <StatusPill tone={origin ? "neutral" : "caution"} data-compare-marker="different">{t(`${KEYS}.different`)}</StatusPill>
        : <Check size={16} role="img" aria-label={t(`${KEYS}.same`)} data-compare-marker="same" />}</td>
    </tr>)}</tbody>
  </table>;
}

function CompareOrigin({ comparison }: { comparison: BusinessDuplicateCandidate["comparison"] }) {
  const { t, i18n } = useTranslation();
  const { source } = useBusiness();
  const channelLabel = useChannelLabel();
  const first = comparison.document.file?.connection_id;
  const second = comparison.other.file?.connection_id;
  const [senders, setSenders] = useState<Record<string, SentBy | "unavailable" | null>>({});
  useEffect(() => {
    const controller = new AbortController();
    for (const id of new Set([first, second])) {
      if (!id) continue;
      void source.receipt(id, controller.signal).then(receipt => {
        if (!controller.signal.aborted) setSenders(previous => ({ ...previous, [id]: receipt.sent_by ?? null }));
      }).catch(() => {
        if (!controller.signal.aborted) setSenders(previous => ({ ...previous, [id]: "unavailable" }));
      });
    }
    return () => controller.abort();
  }, [source, first, second]);
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const empty = t("business.dossier.row.no_data");
  const cells = (doc: BusinessComparedDocument) => {
    const file = doc.file;
    const sender = file && senders[file.connection_id];
    const senderName = sender === "unavailable" ? t("business.activity.state_unknown")
      : sender ? sentByName(t, sender) || empty
      : file && sender === undefined ? t("common.loading") : empty;
    const arrived = file?.received_at ?? doc.received_at;
    return {
      channel: { raw: file?.channel, text: file ? channelLabel(file.channel) : empty },
      sent_by: { raw: sender && sender !== "unavailable" ? sender.id : null, text: senderName },
      arrived: { raw: arrived, text: arrived ? formatTimestamp(arrived, locale) : empty },
      file: { raw: file?.filename, text: file?.filename || empty },
    };
  };
  const mine = cells(comparison.document);
  const other = cells(comparison.other);
  const rows: Row[] = (["channel", "sent_by", "arrived", "file"] as const).map(field => ({
    field, label: t(`business.dossier.details.${field}`), values: [mine[field].text, other[field].text],
    different: mine[field].raw != null && other[field].raw != null ? mine[field].raw !== other[field].raw : undefined,
    wraps: field === "arrived",
  }));
  const title = t(`${KEYS}.origin`);
  return <DossierCard title={title} testId="duplicate-origin"><ComparisonTable rows={rows} caption={title} origin /></DossierCard>;
}

export function ReceiptDuplicateCompare({ dossier, candidate, busy = false, onBack, onBusyChange, onChanged, onDeleted, head }: {
  dossier: BusinessDossier;
  candidate: BusinessDuplicateCandidate;
  busy?: boolean;
  onBack: () => void;
  onBusyChange: (busy: boolean) => void;
  /** The decision kept the document; the compare view is done. */
  onChanged: (next: BusinessDossier) => void;
  /** The reviewed document went to Eliminados. */
  onDeleted: (gone: BusinessDossier) => void;
  head: Pick<ComponentProps<typeof ReceiptReviewFrame>, "recordId" | "title" | "back" | "status">;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const { source, reload, openPanel } = useBusiness();
  const [working, setWorking] = useState<BusinessDuplicateDecision | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const inFlight = useRef(false);
  const request = useRef<{ draftId: string; version: number; otherId: string; otherVersion: number; decision: BusinessDuplicateDecision; key: string } | null>(null);
  const [side, setSide] = useState<CompareSide>("document");
  const [tab, setTab] = useState<DossierTab>("general");
  const title = useRef<HTMLElement>(null);
  useEffect(() => { title.current?.focus(); }, []);
  const channelLabel = useChannelLabel();
  const { comparison } = candidate;
  const firstFile = comparison.document.file;
  const secondFile = comparison.other.file;
  const recommended = comparison.recommendation;
  const decisions = (["different_purchase", "same_purchase"] as const).filter(item => candidate.decisions.includes(item));
  const locked = busy || working !== null;

  const decide = async (decision: BusinessDuplicateDecision) => {
    if (inFlight.current || busy || !candidate.decisions.includes(decision)) return;
    inFlight.current = true;
    setWorking(decision);
    onBusyChange(true);
    setProblem(null);
    const saved = request.current;
    // A retry of the same request keeps its key, so the server answers it once.
    const command = saved?.draftId === dossier.draft_id && saved.version === dossier.version && saved.otherId === candidate.draft_id && saved.otherVersion === candidate.version && saved.decision === decision
      ? saved
      : { draftId: dossier.draft_id, version: dossier.version, otherId: candidate.draft_id, otherVersion: candidate.version, decision, key: randomId() };
    request.current = command;
    try {
      const next = await resolveBusinessDuplicate(command.draftId, command.version, command.otherId, command.otherVersion, decision, command.key);
      request.current = null;
      if (next.deleted) {
        const restore = source.restoreDocument;
        const key = randomId();
        const undo = restore && next.restore_available ? async () => {
          try {
            await restore(next.draft_id, key);
            reload();
            showToast({ kind: "success", text: t("business.document_delete.restored") });
          } catch {
            openPanel({ kind: "draft", draftId: next.draft_id });
          }
        } : undefined;
        onDeleted(next);
        showToast({ kind: "success", text: t(`${KEYS}.deleted`), action: undo
          ? { label: t("business.transactions.undo"), run: undo } : undefined });
      } else {
        showToast({ kind: "success", text: t(`${KEYS}.marked_different`) });
        onChanged(next);
      }
    } catch (error) {
      const code = error !== null && typeof error === "object" && "code" in error ? error.code : null;
      setProblem(code === "stale_version" || code === "duplicate_evidence_changed" ? t("business.dossier.stale")
        : code === "duplicate_same_comprobante" ? t(`${KEYS}.refused_same_comprobante`)
        : t("business.dossier.refused"));
    } finally {
      inFlight.current = false;
      setWorking(null);
      onBusyChange(false);
    }
  };

  const rows: Row[] = BUSINESS_COMPARED_FIELDS.map(field => ({
    field, label: field === "counterparty" ? counterpartyTerm(t, documentFamily(dossier.document_type)) : t(`${KEYS}.field.${field}`),
    values: [shownValue(field, comparison.document, locale), shownValue(field, comparison.other, locale)],
    different: comparison.differences.includes(field),
  }));
  const old = comparison.other;
  const stamp = old.file?.received_at ?? old.received_at;
  const arrival = stamp ? t(`${KEYS}.arrived`, { stamp: formatTimestamp(stamp, locale) }) : null;
  const body = <section ref={title} tabIndex={-1} aria-label={t(`${KEYS}.compare_saved`)} data-testid="duplicate-compare-title">
    <div data-testid="duplicate-compare" aria-busy={working !== null}>
      <DossierCard title={t(`${KEYS}.compare_saved`)} aside={<span className={styles.meta}>{[arrival, old.file && channelLabel(old.file.channel)].filter(Boolean).join(" · ")}</span>}>
        <p className={`rounded-item ${styles.verdict}`} data-same={recommended === "same_purchase"} data-testid="duplicate-recommendation">
          {t(recommended ? `${KEYS}.recommendation.${recommended}` : duplicateBasisKey(candidate.basis, dossier.document_type))}
        </p>
        <ComparisonTable rows={rows} caption={t(`${KEYS}.table.caption`)} />
        {candidate.basis === "fiscal_number" && dossier.document_type !== "venta" ? <p className={styles.fiscal}>{t(`${KEYS}.refused_same_comprobante`)}</p> : null}
      </DossierCard>
    </div>
  </section>;
  const document = <div className={styles.document}>
    <div className={`rounded-full ${styles.sides}`}>
      <SegmentedControl label={t(`${KEYS}.select_document`)} value={side} onChange={setSide} segments={[{ key: "document" as const, label: t(`${KEYS}.column.this`) }, { key: "other" as const, label: t(`${KEYS}.column.saved_before`) }]} />
    </div>
    <DossierCompareDocument key={JSON.stringify([firstFile?.connection_id, secondFile?.connection_id])} side={side}
      files={{ document: firstFile && { id: firstFile.connection_id, ...firstFile }, other: secondFile && { id: secondFile.connection_id, ...secondFile } }}
      noFile={<p className={styles.meta}>{t(`${KEYS}.no_file`)}</p>} />
  </div>;

  const footer = <div className="flex flex-wrap items-center justify-between gap-2">
    {problem ? <p role="alert" className="basis-full text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{problem}</p> : null}
    <button type="button" className={secondaryButtonClass} disabled={locked} onClick={onBack}>{t("common.back")}</button>
    {decisions.length ? <div className="contents min-[520px]:flex min-[520px]:flex-wrap min-[520px]:items-center min-[520px]:justify-end min-[520px]:gap-2">
      {decisions.map((decision) => <button key={decision} type="button" aria-busy={working === decision} className={`${(decision === "different_purchase" ? secondaryButtonClass : recommended === "same_purchase" ? dangerConfirmButtonClass : dangerButtonClass)} whitespace-nowrap`} disabled={locked} onClick={() => void decide(decision)}>
        {working === decision ? <Loader2 className="h-[18px] w-[18px] animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
        {t(`${KEYS}.decision.${decision}`)}
      </button>)}
    </div> : null}
  </div>;

  return <ReceiptReviewFrame {...head} tab={tab} onTab={setTab} tabs={[
    { key: "general", content: body },
    { key: "detalles", content: tab === "detalles" ? <CompareOrigin comparison={comparison} /> : null },
  ]} document={document} documentBelow footer={footer} />;
}
