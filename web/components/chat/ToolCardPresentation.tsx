import React from "react";
import SafeMarkdown from "@/components/chat/SafeMarkdown";
import ResearchSourcesList from "./ResearchSourcesList";
import ReceiptChart from "@/components/receipt/ReceiptChart";
import { researchSourcesFromFacts } from "@/lib/chat-discovery-sidecar";
import { researchSourcesDisplay } from "@/lib/research-sources-display";
import {
  localizedToolText, shownToolInputs, shownToolRows, toolFactSourceText, toolFactValue, type ToolCardPresentation as Presentation,
  type ToolTranslator,
} from "@/lib/tool-result-card";

/** The same declared facts render in chat and in sanitized public receipts. */
export default function ToolCardPresentation({ presentation, t, locale, inputs, withheld = false }: {
  presentation: Presentation; t: ToolTranslator; locale: string; inputs?: React.ReactNode; withheld?: boolean;
}) {
  const sources = researchSourcesFromFacts(presentation.sources);
  const sourceCopy = researchSourcesDisplay(withheld);
  const shownInputs = shownToolInputs(presentation);
  const shownRows = shownToolRows(presentation);
  return <>
    <h2 className="text-[13px] font-medium text-black/55 dark:text-white/55">{localizedToolText(presentation.title, t)}</h2>
    {presentation.answer ? <div data-tool-answer className="mt-3">
      <p className="font-display break-words text-[34px] font-medium leading-tight tabular-nums tracking-tight text-black dark:text-white">{toolFactValue(presentation.answer, t, locale)}</p>
      <p className="mt-1 text-sm text-black/60 dark:text-white/60">{localizedToolText(presentation.answer.label, t)}</p>
    </div> : null}
    {presentation.narrative ? <div className="prose mt-4 max-w-none text-sm leading-relaxed text-black dark:prose-invert dark:text-white"><SafeMarkdown>{presentation.narrative}</SafeMarkdown></div> : null}
    {presentation.visual && presentation.visual.series.length > 1 ? <div data-tool-visual className="mt-4"><ReceiptChart visual={presentation.visual} /></div> : null}
    {shownRows.length > 0 ? <dl className="mt-4 divide-y divide-black/5 dark:divide-white/10">
      {shownRows.map((row) => <div key={row.name} className="flex justify-between gap-4 py-2 text-sm"><dt className="text-black/60 dark:text-white/60">{localizedToolText(row.label, t)}</dt><dd className="break-words text-right tabular-nums">{toolFactValue(row, t, locale)}</dd></div>)}
    </dl> : null}
    {shownInputs.length > 0 ? <section data-tool-inputs className="mt-5 border-t border-black/10 pt-3 dark:border-white/10">
      <h3 className="mb-2 text-xs font-medium text-black/50 dark:text-white/50">{t("tools.card.inputs")}</h3>
      {inputs ?? <dl className="space-y-2">{shownInputs.map((input) => {
        const provenance = toolFactSourceText(input, t, locale);
        return <div key={input.name} data-tool-input={input.name} data-tool-input-source={input.source?.kind} className="flex justify-between gap-4 text-sm"><dt className="text-black/60 dark:text-white/60">{localizedToolText(input.label, t)}{provenance ? <span data-tool-input-provenance className="block text-[11px] text-black/40 dark:text-white/40">{provenance}</span> : null}</dt><dd className="tabular-nums">{toolFactValue(input, t, locale)}</dd></div>;
      })}</dl>}
    </section> : null}
    {sources.length > 0 ? <details className="mt-4">
      <summary className="min-h-11 cursor-pointer py-3 text-sm text-black/60 dark:text-white/60">{t(sourceCopy.openKey, { count: sources.length })}</summary>
      <p className="text-xs leading-relaxed text-black/50 dark:text-white/50">{t(sourceCopy.noteKey)}</p>
      <ResearchSourcesList sources={sources} t={t} locale={locale} />
    </details> : null}
    {presentation.notes.length > 0 ? <ul className="mt-4 space-y-1 text-xs leading-relaxed text-black/50 dark:text-white/50">{presentation.notes.map((note, index) => <li key={`${note.locale_key}-${index}`}>{localizedToolText(note, t)}</li>)}</ul> : null}
  </>;
}
