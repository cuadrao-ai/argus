import type { ReactNode } from "react";
import type { PublicReceiptDocument } from "@/lib/public-receipt-turns";
import { receiptDocumentKind } from "@/lib/public-receipt-turns";
import { type ReceiptCopy, formatReceiptDate, interpolate } from "@/lib/receipt-copy";
import { receiptPresentations } from "@/lib/receipt-presentation";
import type { ArgusLanguage } from "@/lib/language-features";
import ReceiptFollowupBox from "./ReceiptFollowupBox";
import ReceiptTurnContent from "./ReceiptTurnContent";
import ReceiptViewBeacon from "./ReceiptViewBeacon";

type ReceiptBodyProps = {
  payload: PublicReceiptDocument;
  createdAt: string | null;
  copy: ReceiptCopy;
  language: ArgusLanguage;
  preview?: boolean;
  footer?: ReactNode;
};

/** One frozen chat presentation for public reading and the owner's exact preview. */
export default function ReceiptBody({ payload, createdAt, copy, language, preview = false, footer }: ReceiptBodyProps) {
  const entries = receiptPresentations(payload, createdAt, language);
  const notes = [...new Map(entries.filter((entry) => entry.ownerNote).map((entry) => [entry.ownerNote, entry])).values()];
  const date = formatReceiptDate(createdAt, language);
  return <main className="mx-auto flex w-full max-w-3xl flex-col px-4 pb-[max(2rem,env(safe-area-inset-bottom))] pt-6 text-black tablet:px-8 tablet:pt-9 dark:text-white">
    {!preview && <ReceiptViewBeacon kind={receiptDocumentKind(payload)} />}
    <header className="mb-8">
      <h1 className="font-display text-xl font-medium tracking-tight">Cuadrao</h1>
      <p className="mt-2 text-sm leading-relaxed text-black/55 dark:text-white/55">{date ? interpolate(copy.thread.notice, { date }) : copy.thread.preview_notice}</p>
      {notes.map((entry) => <aside key={entry.ownerNote} className="mt-5 rounded-2xl border border-black/10 px-4 py-3 dark:border-white/10"><h2 className="mb-1 text-xs font-medium text-black/50 dark:text-white/50">{copy.sections.note}</h2><p lang={entry.language} className="whitespace-pre-wrap break-words text-sm leading-relaxed">{entry.ownerNote}</p></aside>)}
    </header>
    <div className="flex min-w-0 flex-col gap-10">
      {entries.map((entry, index) => <article key={index} className="flex min-w-0 flex-col gap-6">
        <div data-receipt-question="" className="flex w-full justify-end">
          <p lang={entry.language} className="max-w-[85%] whitespace-pre-wrap break-words rounded-[24px] rounded-br-sm bg-black/5 px-5 py-3.5 text-[16px] font-normal leading-[1.5] tracking-[0.24px] dark:bg-white/10">{entry.title}</p>
        </div>
        <div className="min-w-0"><p className="mb-3 font-display text-sm font-medium">Cuadrao</p><ReceiptTurnContent entry={entry} copy={copy} language={language} /></div>
      </article>)}
    </div>
    <footer className="mt-10 w-full">{footer ?? <ReceiptFollowupBox copy={copy} />}</footer>
  </main>;
}
