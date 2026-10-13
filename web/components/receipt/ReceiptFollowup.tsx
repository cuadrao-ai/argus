"use client";

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import ReceiptFollowupBox from './ReceiptFollowupBox';
import { createReceiptFollowup, saveReceiptFollowup } from '@/lib/receipt-followup';
import { reportReceiptFunnelStage } from '@/lib/receipt-funnel';
import { captureLandingIntentFromLocation, signedInHomePath } from '@/lib/landing-intent';
import type { ReceiptKind } from '@/lib/public-receipt-turns';
import type { ReceiptCopy } from '@/lib/receipt-copy';

/** Reading this component has no auth, chat or provider side effects. */
export default function ReceiptFollowup({ publicId, copy, language, kind }: { publicId: string; copy: ReceiptCopy; language: string; kind: ReceiptKind }) {
  const router = useRouter();
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  return <ReceiptFollowupBox copy={copy} value={value} onChange={setValue} disabled={false} busy={busy} onSubmit={event => {
    event.preventDefault();
    if (!value.trim() || busy) return;
    captureLandingIntentFromLocation();
    if (!saveReceiptFollowup(createReceiptFollowup(publicId, value, language))) { setFailed(true); return; }
    setBusy(true);
    reportReceiptFunnelStage('try_argus', kind);
    router.push(signedInHomePath());
  }}>{failed ? <p role="alert">{copy.followup.error}</p> : null}</ReceiptFollowupBox>;
}
