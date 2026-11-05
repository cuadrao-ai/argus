import { Fragment } from "react";
import SafeMarkdown from "@/components/chat/SafeMarkdown";
import { type ReceiptCopy, formatReceiptDay } from "@/lib/receipt-copy";
import type { ReceiptFigures, ReceiptPresentation } from "@/lib/receipt-presentation";
import type { ArgusLanguage } from "@/lib/language-features";
import ReceiptChart from "./ReceiptChart";

const MUTED = "text-black/55 dark:text-white/55";
const RULE = "border-t border-black/10 dark:border-white/10";
const CARD = "min-w-0 rounded-[24px] border border-black/10 bg-black/[0.02] p-5 dark:border-white/10 dark:bg-white/[0.025]";

function Figures({ figures }: { figures: ReceiptFigures }) {
  const negative = Boolean(figures.headline?.trim().startsWith("-"));
  return <>
    <div className={`font-display break-words text-3xl font-medium leading-tight tabular-nums tablet:text-4xl ${figures.neutralHeadline ? "text-black dark:text-white" : negative ? "text-[#b94c55] dark:text-[#d66d75]" : "text-[#3f7e70] dark:text-[#5ba897]"}`}>{figures.headline}</div>
    {figures.verdict && <p className="mt-2 text-sm font-medium tabular-nums">{figures.verdict}{figures.benchmark && figures.benchmarkSymbol && <span className={MUTED}>{" · "}{figures.benchmarkSymbol} {figures.benchmark}</span>}</p>}
    <dl className="mt-4">{figures.rows.map((row) => <div key={row.label} className={`flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2 ${RULE}`}><dt className={`text-sm ${MUTED}`}>{row.label}</dt><dd className="text-right text-sm tabular-nums">{row.value}</dd></div>)}</dl>
  </>;
}

function Plan({ plan }: { plan: NonNullable<ReceiptFigures["plan"]> }) {
  return <section className={`mt-4 pt-4 ${RULE}`}>
    <h3 className={`text-xs font-medium ${MUTED}`}>{plan.heading}</h3>
    <div className="mt-2 flex flex-col gap-3">{plan.rows.map((row) => <div key={row.text}><p className="text-sm leading-relaxed">{row.text}</p>{row.exact && <p className={`mt-1 text-xs leading-relaxed ${MUTED}`}>{row.exact}</p>}</div>)}</div>
    {plan.assumptions.length > 0 && <ul className={`mt-3 space-y-1 text-xs leading-relaxed ${MUTED}`}>{plan.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>}
    {plan.footer && <p className={`mt-2 text-xs leading-relaxed ${MUTED}`}>{plan.footer}</p>}
  </section>;
}

function Answer({ answer, language }: { answer: string; language: ArgusLanguage }) {
  return <div lang={language} className="min-w-0 break-words text-[16px] leading-[1.6] tracking-[0.24px] [&_p]:mb-4 [&_p:last-child]:mb-0 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:my-1 [&_h2]:my-4 [&_h2]:font-medium [&_h3]:my-3 [&_h3]:font-medium [&_a]:underline [&_a]:underline-offset-4">
    <SafeMarkdown allowedElements={["img", "p", "strong", "em", "ul", "ol", "li", "a", "blockquote", "h2", "h3", "br", "code", "table", "thead", "tbody", "tr", "th", "td"]} unwrapDisallowed components={{
      a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
      table: ({ children }) => <div className="my-4 max-w-full overflow-x-auto"><table className="w-full border-collapse text-left text-sm leading-relaxed [&_th]:border-b [&_th]:border-black/15 [&_th]:px-3 [&_th]:py-2 [&_th]:font-medium [&_td]:border-b [&_td]:border-black/10 [&_td]:px-3 [&_td]:py-2 [&_td]:align-top dark:[&_th]:border-white/15 dark:[&_td]:border-white/10">{children}</table></div>,
    }}>{answer}</SafeMarkdown>
  </div>;
}

/** Frozen public facts only. Also used for carried cards in a receiver's chat. */
export default function ReceiptTurnContent({ entry, copy, language, includeAnswer = true }: {
  entry: ReceiptPresentation;
  copy: ReceiptCopy;
  language: ArgusLanguage;
  includeAnswer?: boolean;
}) {
  const answer = entry.research?.answer ?? entry.answer;
  const figures = !entry.research && !entry.textOnly;
  return <div data-receipt-answer="" className="flex min-w-0 flex-col gap-4 text-black dark:text-white">
    {includeAnswer && answer && <Answer answer={answer} language={entry.language} />}
    {figures && <div data-receipt-card="" className={CARD}>
      <div className={`mb-3 flex flex-wrap items-center justify-between gap-2 text-xs ${MUTED}`}><span>{copy.thread.read_only}</span>{entry.stamp && <span>{entry.stamp}</span>}</div>
      {entry.calculations ? entry.calculations.map((calculation, index) => <Fragment key={index}>
        <section className={index ? `mt-5 pt-5 ${RULE}` : undefined}><h3 className={`mb-3 text-sm ${MUTED}`}>{calculation.title}</h3><Figures figures={calculation} />{calculation.plan && <Plan plan={calculation.plan} />}</section>
      </Fragment>) : <Figures figures={entry} />}
      {entry.visual && entry.visual.series.length > 1 && <div className="mt-4"><ReceiptChart visual={entry.visual} /></div>}
      {entry.plan && <Plan plan={entry.plan} />}
    </div>}
    {entry.research && <section className={`text-xs ${MUTED}`}>
      {entry.stamp && <p className="mb-3">{entry.stamp}</p>}
      {entry.research.sources.length > 0 && <><h3 className="font-medium">{copy.research.sources}</h3><ul className="mt-2 space-y-3">{entry.research.sources.map((source) => <li key={source.url}><a href={source.url} target="_blank" rel="noopener noreferrer" lang={entry.language} className="inline-flex min-h-11 items-center text-sm text-black underline decoration-black/25 underline-offset-4 dark:text-white dark:decoration-white/25">{source.title}</a><p>{[source.domain, formatReceiptDay(source.source_date, language)].filter(Boolean).join(" · ")}</p></li>)}</ul></>}
      {entry.research.nextStep && <p className="mt-4 text-sm leading-relaxed">{entry.research.nextStep}</p>}
    </section>}
    <p className={`text-xs leading-relaxed ${MUTED}`}>{entry.framing}</p>
  </div>;
}
