"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@/components/ui/Tooltip";
import {
  createEmailSenderStub,
  emailSenderPreview,
  emailSendersUseStub,
  groupSenders,
  liveEmailSenderClient,
  senderForView,
  senderTagView,
  type EmailSender,
  type EmailSenderClient,
  type EmailSenderUpdate,
  type EmailSenderView,
  type SenderTagView,
  EmailSenderRequestError,
} from "@/lib/business-email";
import { quietButtonClass, secondaryButtonClass } from "./business-ui";
import { FOCUS_RING } from "./foundation/presentation";

const copy = (key: string) => `business.reception.senders.${key}`;

function requestStatus(error: unknown): number {
  return error instanceof EmailSenderRequestError ? error.status : 0;
}

function SenderTag({ view }: { view: SenderTagView }) {
  const { t } = useTranslation();
  if (view === "none") return null;
  const name = view === "verified" ? "tag_verified" : "tag_unverified";
  const tip = view === "verified" ? "tag_verified_tip" : "tag_unverified_tip";
  return (
    <Tooltip content={t(copy(tip))} side="top">
      <button type="button" data-testid="email-sender-tag" data-verification={view} className={`inline-flex min-h-11 w-fit items-center self-start rounded-full border border-[color:var(--surface-divider)] px-3 text-[13px] ${FOCUS_RING} ${view === "verified" ? "text-[var(--cuadrao-green)]" : "text-[#56635e]"}`}>
        {t(copy(name))}
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
  return (
    <li data-testid="email-sender-row" data-status={sender.status} className="border-t border-[#EEF0EC] py-3 dark:border-white/[0.06]">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <span className="min-w-0 flex-1 break-all text-[16px] text-[#172b26] dark:text-white">{sender.value}</span>
        <SenderTag view={senderTagView(sender.tag)} />
        <div className="flex flex-wrap gap-2">
          <button type="button" className={secondaryButtonClass} disabled={disabled} onClick={() => onChange("authorized")}>{t(copy("authorize"))}</button>
          <button type="button" className={secondaryButtonClass} disabled={disabled} onClick={() => onChange("blocked")}>{t(copy("block"))}</button>
        </div>
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
  const sectionClass = "border-t border-[color:var(--surface-divider)] pt-1";
  const headingClass = "px-2 text-[14px] text-[#56635e] dark:text-white/70";

  return (
    <section data-testid="email-senders" aria-labelledby="email-senders-title" className="mt-4">
      <h3 id="email-senders-title" className="text-[16px] font-medium text-[#172b26] dark:text-white">{t(copy("list_title"))}</h3>
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
          <details open data-testid="email-senders-pending" className={`mt-3 ${sectionClass}`}>
            <summary className={`min-h-11 cursor-pointer content-center rounded-md px-2 text-[14px] text-[#56635e] dark:text-white/70 ${FOCUS_RING}`}>
              <span>{t(copy("pending_heading"))}</span>
              {pending.length ? <span data-testid="email-senders-pending-count" className="ml-2">{t(copy("pending_count"), { count: pending.length })}</span> : null}
            </summary>
            {pending.length ? (
              <ul>{pending.map((sender) => <SenderRow key={sender.id} sender={sender} busy={busyId === sender.id} refused={refused} failed={rowError === sender.id} onChange={(status) => void change(sender, status)} />)}</ul>
            ) : (
              <p className="px-2 py-2 text-[14px] text-[#56635e] dark:text-white/70">{t(copy("pending_empty"))}</p>
            )}
          </details>
          {grouped.authorized.length ? (
            <section aria-labelledby="email-senders-authorized" className={`mt-3 ${sectionClass}`}>
              <h4 id="email-senders-authorized" className={`flex min-h-11 items-center ${headingClass}`}>{t(copy("authorized_heading"))}</h4>
              <ul>{grouped.authorized.map((sender) => <SenderRow key={sender.id} sender={sender} busy={busyId === sender.id} refused={refused} failed={rowError === sender.id} onChange={(status) => void change(sender, status)} />)}</ul>
            </section>
          ) : null}
          {grouped.blocked.length ? (
            <section aria-labelledby="email-senders-blocked" className={`mt-3 ${sectionClass}`}>
              <h4 id="email-senders-blocked" className={`flex min-h-11 items-center ${headingClass}`}>{t(copy("blocked_heading"))}</h4>
              <ul>{grouped.blocked.map((sender) => <SenderRow key={sender.id} sender={sender} busy={busyId === sender.id} refused={refused} failed={rowError === sender.id} onChange={(status) => void change(sender, status)} />)}</ul>
            </section>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
