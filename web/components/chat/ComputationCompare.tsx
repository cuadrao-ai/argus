"use client";

import React, { useEffect, useState } from "react";
import ToolCardPresentation from "./ToolCardPresentation";
import type { ComputationComparison, ComputedAnswerSummary } from "@/lib/computation-contract";
import { comparedValueText, differenceText } from "@/lib/computation-compare";
import { compareComputedAnswers, listComputedAnswers } from "@/lib/computations-api";
import { localizedToolText, parseToolResultCard, type ToolTranslator } from "@/lib/tool-result-card";
import { useConversationSurface } from "./ChatWorkspace";

export type ComputationSource = { conversationId: string; messageId: string; kind: string };

/**
 * Pick another owned result of the same kind and see both side by side. The
 * differences are the backend's; nothing here calls a model or a provider.
 */
export function ComputationComparePanel({ source, t, locale }: { source: ComputationSource; t: ToolTranslator; locale: string }) {
  const [choices, setChoices] = useState<ComputedAnswerSummary[] | null>(null);
  const [comparison, setComparison] = useState<ComputationComparison | null>(null);
  const [busy, setBusy] = useState(true);
  const [failed, setFailed] = useState(false);
  const surface = useConversationSurface();
  useEffect(() => {
    let active = true;
    setBusy(true);
    setFailed(false);
    setComparison(null);
    listComputedAnswers(source.kind, source.messageId, surface)
      .then((page) => { if (active) setChoices(page.items); })
      .catch(() => { if (active) setFailed(true); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [source.kind, source.messageId, surface]);
  const pick = async (choice: ComputedAnswerSummary) => {
    setBusy(true);
    setFailed(false);
    try {
      setComparison(await compareComputedAnswers(
        { conversation_id: source.conversationId, message_id: source.messageId },
        { conversation_id: choice.conversation_id, message_id: choice.message_id },
      ));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };
  const dateText = (value: string) => new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(value));
  let body: React.ReactNode = null;
  if (comparison) body = <ComputationComparisonView comparison={comparison} t={t} locale={locale} />;
  else if (choices === null) body = busy ? <p role="status" className="text-sm text-black/50 dark:text-white/50">{t("tools.compute.compare_loading")}</p> : null;
  else if (choices.length === 0) body = <p className="text-sm text-black/55 dark:text-white/55">{t("tools.compute.compare_empty")}</p>;
  else body = <div>
    <p className="mb-2 text-xs font-medium text-black/50 dark:text-white/50">{t("tools.compute.compare_pick")}</p>
    <ul className="divide-y divide-black/5 dark:divide-white/10">
      {choices.map((choice) => <li key={choice.message_id}>
        <button type="button" data-compare-choice={choice.message_id} disabled={busy} onClick={() => { void pick(choice); }}
          className="flex min-h-11 w-full items-center justify-between gap-3 py-2 text-left text-sm disabled:opacity-50">
          <span className="min-w-0 truncate text-black dark:text-white">{choice.asked ?? choice.symbols.join(", ")}</span>
          <span className="shrink-0 text-xs text-black/45 dark:text-white/45">{t("tools.compute.computed_on", { date: dateText(choice.computed_at) })}</span>
        </button>
      </li>)}
    </ul>
  </div>;
  return <div data-computation-compare aria-busy={busy} className="mt-3 w-full min-w-0">
    {failed ? <p role="alert" className="mb-2 text-xs text-rose-700 dark:text-rose-300">{t("tools.compute.compare_failed")}</p> : null}
    {body}
  </div>;
}

/** Both results and the backend's differences; read-only, never recomputed here. */
export function ComputationComparisonView({ comparison, t, locale }: { comparison: ComputationComparison; t: ToolTranslator; locale: string }) {
  const sides = [
    { side: "left", answer: comparison.left, label: t("tools.compute.left") },
    { side: "right", answer: comparison.right, label: t("tools.compute.right") },
  ];
  return <div data-computation-comparison={comparison.kind} className="grid min-w-0 gap-3 md:grid-cols-2">
    {sides.map(({ side, answer, label }) => {
      const card = parseToolResultCard(answer.card);
      return <section key={side} data-compared={side} className="min-w-0 rounded-2xl border border-black/10 p-4 dark:border-white/10">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-black/40 dark:text-white/40">{label}</p>
        {answer.asked ? <p className="mt-1 break-words text-[13px] text-black/60 dark:text-white/60">{answer.asked}</p> : null}
        {card ? <div className="mt-3"><ToolCardPresentation presentation={card.presentation} t={t} locale={locale} withheld={card.outcome.status !== "succeeded"} /></div>
          : <p role="status" className="mt-3 text-sm text-black/60 dark:text-white/60">{t("tools.card.unavailable")}</p>}
      </section>;
    })}
    <section data-computation-differences className="min-w-0 md:col-span-2">
      <h3 className="text-xs font-medium text-black/50 dark:text-white/50">{t("tools.compute.differences")}</h3>
      {comparison.differences.length === 0 ? <p className="mt-2 text-sm text-black/55 dark:text-white/55">{t("tools.compute.no_differences")}</p> : (
        <dl className="mt-2 divide-y divide-black/5 dark:divide-white/10">
          {comparison.differences.map((difference) => <div key={`${difference.section}:${difference.name}`} data-difference={difference.name}
            className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 py-2 text-sm">
            <dt className="min-w-0 break-words text-black/60 dark:text-white/60">{localizedToolText(difference.label, t)}</dt>
            <dd className="text-right font-medium tabular-nums text-black dark:text-white">{differenceText(difference, t, locale)}</dd>
            <dd className="col-span-2 text-xs tabular-nums text-black/45 dark:text-white/45">
              {t("tools.compute.from_to", { left: comparedValueText(difference, "left", t, locale), right: comparedValueText(difference, "right", t, locale) })}
            </dd>
          </div>)}
        </dl>
      )}
    </section>
  </div>;
}
