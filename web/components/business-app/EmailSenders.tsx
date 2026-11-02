"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { fieldHintClass } from "@/components/ui/form-field";
import { Tooltip } from "@/components/ui/Tooltip";
import {
  createEmailSenderStub,
  emailSenderPreview,
  emailSendersUseStub,
  groupSenders,
  liveEmailSenderClient,
  senderCheckFailed,
  senderForView,
  senderMoves,
  type EmailSender,
  type EmailSenderClient,
  type EmailSenderUpdate,
  type EmailSenderView,
  EmailSenderRequestError,
} from "@/lib/business-email";
import { quietButtonClass } from "./business-ui";
import { RowAction, RowTextAction } from "./foundation/RowAction";
import { BUSINESS_STATUS, FOCUS_RING } from "./foundation/presentation";

const copy = (key: string) => `business.reception.senders.${key}`;

function requestStatus(error: unknown): number {
  return error instanceof EmailSenderRequestError ? error.status : 0;
}

function UnverifiedNote() {
  const { t } = useTranslation();
  return (
    <Tooltip content={t(copy("tag_unverified_tip"))} side="top">
      <button type="button" data-testid="email-sender-unverified" className={`inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-mark ${fieldHintClass} ${FOCUS_RING}`}>
        <span aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: BUSINESS_STATUS.needs_attention.ink }} />
        {t(copy("tag_unverified"))}
      </button>
    </Tooltip>
  );
}

function SenderRow({
  sender,
  busy,
  refused,
  failed,
  onChange,
}: {
  sender: EmailSenderView;
  busy: boolean;
  refused: boolean;
  failed: boolean;
  onChange: (status: EmailSenderUpdate["status"]) => void;
}) {
  const { t } = useTranslation();
  const disabled = busy || refused;
  const moves = senderMoves(sender);
  return (
    <li data-testid="email-sender-row" data-status={sender.status} className="border-t border-[#EEF0EC] py-1 dark:border-white/[0.06]">
      <div className="flex flex-col sm:flex-row sm:items-center sm:gap-3">
        <div className="flex min-h-11 min-w-0 flex-1 items-center gap-3">
          <span className="min-w-0 break-all text-[16px] text-[#172b26] dark:text-white">{sender.value}</span>
          {senderCheckFailed(sender.tag) ? <UnverifiedNote /> : null}
        </div>
        {moves.length ? (
          <div className="flex shrink-0 items-center justify-end gap-2">
            {moves.map((move) => move === "authorized"
              ? <RowAction key={move} disabled={disabled} onClick={() => onChange(move)}>{t(copy("authorize"))}</RowAction>
              : <RowTextAction key={move} disabled={disabled} onClick={() => onChange(move)}>{t(copy("block"))}</RowTextAction>)}
          </div>
        ) : null}
      </div>
      {failed ? <p role="alert" data-testid="email-sender-error" className="mt-2 text-[14px] text-[#9e2f39] dark:text-[#ec9aa0]">{t(copy("action_error"))}</p> : null}
    </li>
  );
}

export default function EmailSenders({ client }: { client?: EmailSenderClient }) {
  const { t } = useTranslation();
  const source = useRef<EmailSenderClient | null>(client ?? null);
  const [attempt, setAttempt] = useState(0);
  const [items, setItems] = useState<EmailSender[] | null>(null);
  const [failure, setFailure] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);
  const [refused, setRefused] = useState(false);

  useEffect(() => {
    if (!source.current) {
      source.current = emailSendersUseStub()
        ? createEmailSenderStub(emailSenderPreview(window.location.search))
        : liveEmailSenderClient;
    }
    const active = source.current;
    let current = true;
    const controller = new AbortController();
    setFailure(false);
    void active.list(controller.signal).then(
      (next) => { if (current) setItems(next); },
      () => { if (current && !controller.signal.aborted) { setItems(null); setFailure(true); } },
    );
    return () => { current = false; controller.abort(); };
  }, [attempt, client]);

  const change = async (sender: EmailSenderView, status: EmailSenderUpdate["status"]) => {
    if (refused || busyId || !source.current) return;
    setBusyId(sender.id);
    setRowError(null);
    try {
      const next = await source.current.update({ kind: sender.kind, value: sender.value, status });
      setItems((current) => current?.map((item) => item.id === sender.id ? next : item) ?? current);
    } catch (error) {
      if (requestStatus(error) === 403) setRefused(true);
      else setRowError(sender.id);
    } finally {
      setBusyId(null);
    }
  };

  const grouped = items ? groupSenders(items.map(senderForView)) : null;
  const pending = grouped?.pending ?? [];
  const summaryClass = `min-h-11 cursor-pointer content-center rounded-mark text-[14px] text-[#56635e] dark:text-white/70 ${FOCUS_RING}`;
  const rowsOf = (senders: EmailSenderView[]) => <ul>{senders.map((sender) => <SenderRow key={sender.id} sender={sender} busy={busyId === sender.id} refused={refused} failed={rowError === sender.id} onChange={(status) => void change(sender, status)} />)}</ul>;
  const settledGroup = (testId: string, heading: string, senders: EmailSenderView[]) => senders.length ? (
    <details data-testid={testId} className="mt-3">
      <summary className={summaryClass}>{t(copy(heading))} · {senders.length}</summary>
      {rowsOf(senders)}
    </details>
  ) : null;

  return (
    <section data-testid="email-senders" aria-labelledby="email-senders-title">
      <h2 id="email-senders-title" className="font-display text-[21px] font-medium text-[#172b26] dark:text-white">{t(copy("list_title"))}</h2>
      {failure ? (
        <div className="mt-3" role="alert" data-testid="email-senders-error">
          <p className="text-[14px] text-[#56635e] dark:text-white/70">{t(copy("error"))}</p>
          <button type="button" className={`${quietButtonClass} mt-3`} onClick={() => setAttempt((value) => value + 1)}>{t(copy("retry"))}</button>
        </div>
      ) : null}
      {!failure && !grouped ? (
        <div data-testid="email-senders-loading" aria-busy="true" className="mt-3 h-24 animate-pulse rounded-item bg-black/5 dark:bg-white/10">
          <span className="sr-only">{t(copy("loading"))}</span>
        </div>
      ) : null}
      {grouped && items?.length === 0 ? <p data-testid="email-senders-empty" className="mt-3 text-[14px] text-[#56635e] dark:text-white/70">{t(copy("empty"))}</p> : null}
      {grouped && items && items.length > 0 ? (
        <>
          {refused ? <p role="alert" data-testid="email-senders-forbidden" className="mt-3 text-[14px] text-[#9e2f39] dark:text-[#ec9aa0]">{t(copy("forbidden"))}</p> : null}
          {pending.length ? (
            <section data-testid="email-senders-pending" aria-labelledby="email-senders-pending-title" className="mt-3">
              <h3 id="email-senders-pending-title" className="flex min-h-11 items-center gap-1 text-[14px] text-[#56635e] dark:text-white/70">{t(copy("pending_heading"))} · <span data-testid="email-senders-pending-count">{t(copy("pending_count"), { count: pending.length })}</span></h3>
              {rowsOf(pending)}
            </section>
          ) : null}
          {settledGroup("email-senders-authorized", "authorized_heading", grouped.authorized)}
          {settledGroup("email-senders-blocked", "blocked_heading", grouped.blocked)}
        </>
      ) : null}
    </section>
  );
}
