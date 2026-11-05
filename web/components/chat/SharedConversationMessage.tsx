"use client";

import SafeMarkdown from "@/components/chat/SafeMarkdown";
import { useTranslation } from 'react-i18next';
import ReceiptTurnContent from '@/components/receipt/ReceiptTurnContent';
import { receiptPresentations } from '@/lib/receipt-presentation';
import { formatReceiptDate, receiptCopy } from '@/lib/receipt-copy';
import { normalizeEnabledLanguage } from '@/lib/language-features';
import type { Message } from './types';

/** Frozen public presentation has no live artifact identity or action handlers. */
export default function SharedConversationMessage({ message }: { message: Message }) {
  const { i18n } = useTranslation();
  const language = normalizeEnabledLanguage(i18n.resolvedLanguage ?? i18n.language);
  const copy = receiptCopy(language);
  const shared = message.sharedConversation!;
  const entry = shared.card ? receiptPresentations('schema_version' in shared.card ? shared.card : { schema_version: 2, kind: 'turns', turns: [shared.card] }, shared.snapshot_at, language)[0] : null;
  return <div className={message.role === 'user' ? 'flex w-full flex-col items-end gap-2' : 'flex w-full flex-col gap-2'}>
    <p className="text-xs text-black/50 dark:text-white/50">{copy.thread.carried.replace('{{date}}', formatReceiptDate(shared.snapshot_at, language) ?? shared.snapshot_at)}</p>
    {message.role === 'user' ? <div className="max-w-[85%] rounded-[24px] rounded-br-sm bg-black/5 px-5 py-3.5 text-base leading-normal dark:bg-white/10">{message.content}</div>
      : entry ? <ReceiptTurnContent entry={entry} copy={copy} language={language} />
      : <SafeMarkdown>{message.content}</SafeMarkdown>}
  </div>;
}
