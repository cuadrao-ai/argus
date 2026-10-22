"use client";

import { useEffect, useState, type ReactNode, type RefObject } from "react";
import { Check } from "lucide-react";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { formatDay, formatTimestamp } from "../business-format";
import { primaryButtonClass, quietButtonClass, secondaryButtonClass } from "../business-ui";
import { NO_COMPROBANTE_REASONS, type DocumentSummary, type HistoryEntry, type Movement } from "./transacciones-model";
import { AccountLabel, KeyHint, PlainAmount, SignedAmount, StateIcon, Unknown } from "./transacciones-parts";
import { useRowCommands, type Command } from "./transacciones-commands";
import { useTransaccionesWords } from "./transacciones-words";
import { movementName, type TransaccionesController } from "./useTransacciones";

/** Igualar is the tray's one primary; the others are alternatives. Read at render: business-ui sits in an import cycle with the workspace. */
const level = (id: Command["id"]) => (id === "igualar" ? primaryButtonClass : id === "sin_comprobante" ? quietButtonClass : secondaryButtonClass);

/**
 * The record beside the list: the bank's side, the proof's side, why the
 * pair was offered, and the decisions. No scrim, so the next row opens
 * straight away; on a phone it is a full page with a way back.
 */
export function TransaccionesTray({ controller, movement, phone, returnFocusRef }: { controller: TransaccionesController; movement: Movement; phone: boolean; returnFocusRef: RefObject<HTMLElement | null> }) {
  const { t, locale, stateWord, reason } = useTransaccionesWords();
  const commands = useRowCommands(controller)(movement);
  const tray = controller.tray!;
  const run = tray.run;
  const step = run ? run.indexOf(movement.id) + 1 : 0;
  const failure = controller.failure?.movement.id === movement.id ? controller.failure : null;
  const busy = controller.busy === movement.id;
  const match = movement.match;
  const document: DocumentSummary | null = match.state === "sugerencia" ? match.suggestion.document : match.state === "igualada" || match.state === "sin_movimiento" ? match.document : null;
  const documentKind = document?.kind ?? null;
  const footer = tray.mode === "record" && commands.length ? (
    <div className="flex flex-wrap items-center gap-2" data-testid="transacciones-tray-actions">
      {commands.map((command) => (
        <button key={command.id} type="button" data-tray-action={command.id} disabled={busy} onClick={command.run} className={level(command.id)}>
          {command.label}<KeyHint>{command.key}</KeyHint>
        </button>
      ))}
    </div>
  ) : undefined;
  return (
    <AdaptivePanel
      modal={false}
      width="md"
      snaps={["full"]}
      title={t("business.transactions.tray.title")}
      closeLabel={t("common.close", "Cerrar")}
      onClose={() => { returnFocusRef.current?.focus(); controller.close(); }}
      returnFocusRef={returnFocusRef}
      initialFocusRef={phone ? undefined : returnFocusRef}
      footer={footer}
    >
      <div data-testid="transacciones-tray" className="space-y-5 px-5 py-5 text-[14px] text-[#172b26] dark:text-white">
        {run && step > 0 ? <p className="text-[13px] text-[#56635e] dark:text-white/65">{t("business.transactions.tray.step", { index: step, count: run.length })} <span className="hidden desktop:inline"><KeyHint>↑</KeyHint><KeyHint>↓</KeyHint> {t("business.transactions.tray.move")} · <KeyHint>Esc</KeyHint> {t("business.transactions.tray.close")}</span></p> : null}
        <div>
          <p className="flex items-center gap-2 text-[13px] text-[#56635e] dark:text-white/65"><StateIcon state={match.state} />{stateWord(match.state)}</p>
          <h3 className="mt-1 font-display text-[21px] font-medium leading-tight">{movementName(movement)}</h3>
          <p className="mt-1 text-[17px] font-medium"><SignedAmount money={movement.money} header={null} /></p>
        </div>
        {failure ? (
          <div role="alert" data-testid="transacciones-decision-error" className="rounded-item border border-[#9e2f39]/30 bg-[#f6dfe0]/50 px-3.5 py-3 text-[#9e2f39] dark:border-[#ec9aa0]/30 dark:bg-[#ec9aa0]/10 dark:text-[#ec9aa0]">
            <p>{t(`business.transactions.error.codes.${failure.problem.code}`)}</p>
            {failure.problem.action === "retry" ? <p className="mt-1"><ReferenceCode reference={failure.reference} /></p> : null}
            {failure.problem.action === "none" ? null : (
              <button type="button" data-recover={failure.problem.action} onClick={controller.recover} disabled={busy} className={`${quietButtonClass} -ml-1 mt-1`}>{failure.problem.action === "retry" ? t("common.retry", "Reintentar") : t("business.transactions.error.reload")}</button>
            )}
          </div>
        ) : null}
        {tray.mode === "reasons" ? (
          <section>
            <h4 className="mb-2 text-[13px] font-medium text-[#56635e] dark:text-white/65">{t("business.transactions.reasons.title")}</h4>
            <div className="flex flex-col gap-2">
              {NO_COMPROBANTE_REASONS.map((item) => (
                <button key={item} type="button" data-reason={item} disabled={busy} onClick={() => void controller.decide({ kind: "sin_comprobante", movementId: movement.id, reason: item })} className={`${secondaryButtonClass} justify-start`}>
                  {t(`business.transactions.reasons.${item}`)}
                </button>
              ))}
            </div>
          </section>
        ) : null}
        {movement.bankText !== null || match.state !== "sin_movimiento" ? (
          <Facts title={t("business.transactions.tray.movement")}>
            <Fact label={t("business.transactions.tray.date")}>{formatDay(movement.occurredOn, locale)}</Fact>
            <Fact label={t("business.transactions.tray.account")}><AccountLabel account={movement.account} /></Fact>
            <Fact label={t("business.transactions.tray.bank_text")}>{movement.bankText ?? <Unknown />}</Fact>
          </Facts>
        ) : null}
        {documentKind ? (
          <Facts title={match.state === "sugerencia" ? t("business.transactions.tray.suggested") : t("business.transactions.tray.matched")}>
            <Fact label={t(`business.transactions.tray.${documentKind}`)}>{document?.counterparty ?? <Unknown />}</Fact>
            <Fact label={t("business.transactions.tray.date")}>{document?.occurredOn ? formatDay(document.occurredOn, locale) : <Unknown />}</Fact>
            <Fact label={t("business.transactions.tray.rnc")}>{document?.rnc ?? <Unknown />}</Fact>
            <Fact label={t("business.transactions.tray.ncf")}>{document?.ncf ?? <Unknown />}</Fact>
            <Fact label={t("business.transactions.tray.itbis")}>{document?.itbis ? <PlainAmount money={document.itbis} /> : <Unknown />}</Fact>
            <Fact label={t("business.transactions.tray.total")} strong>{document?.total ? <PlainAmount money={document.total} /> : <Unknown />}</Fact>
          </Facts>
        ) : null}
        <History controller={controller} movement={movement} />
        {match.state === "sugerencia" && match.suggestion.reasons.length ? (
          <section>
            <h4 className="mb-2 text-[13px] font-medium text-[#56635e] dark:text-white/65">{t("business.transactions.why.title")}</h4>
            <ul className="space-y-1.5">
              {match.suggestion.reasons.map((item) => (
                <li key={item.kind} className="flex items-center gap-2"><Check className="h-3.5 w-3.5 text-[#56635e] dark:text-white/60" aria-hidden="true" />{reason(item)}</li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </AdaptivePanel>
  );
}

/** What the line went through: each outcome it had, ended ones included, as the server keeps them. Quiet while it reads, and absent when it cannot. */
function History({ controller, movement }: { controller: TransaccionesController; movement: Movement }) {
  const { t, locale } = useTransaccionesWords();
  const [entries, setEntries] = useState<readonly HistoryEntry[] | null>(null);
  const bankLine = movement.bankText !== null;
  const state = movement.match.state;
  useEffect(() => {
    let cancelled = false;
    setEntries(null);
    if (!bankLine) return undefined;
    controller.source.history(movement.id).then((read) => { if (!cancelled) setEntries(read); }, () => undefined);
    return () => { cancelled = true; };
  }, [bankLine, controller.source, movement.id, state]);
  if (!entries?.some((entry) => entry.until !== null)) return null;
  return (
    <section data-testid="transacciones-history">
      <h4 className="mb-2 text-[13px] font-medium text-[#56635e] dark:text-white/65">{t("business.transactions.history.title")}</h4>
      <ol className="space-y-1.5 text-[13px] text-[#56635e] dark:text-white/65">
        {entries.map((entry) => (
          <li key={entry.id}>
            {entry.outcome === "match" ? t(`business.transactions.history.match_${entry.documentKind ?? "recibo"}`) : t("business.transactions.history.no_receipt", { reason: entry.reason ? t(`business.transactions.reasons.${entry.reason}`) : "" })}
            {" "}
            <span className="tabular-nums">{entry.until ? t("business.transactions.history.between", { from: formatTimestamp(entry.from, locale), until: formatTimestamp(entry.until, locale) }) : t("business.transactions.history.since", { from: formatTimestamp(entry.from, locale) })}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Facts({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h4 className="mb-2 text-[13px] font-medium text-[#56635e] dark:text-white/65">{title}</h4>
      <dl className="divide-y divide-[#DCE0DA] rounded-item border border-[#DCE0DA] dark:divide-white/10 dark:border-white/10">{children}</dl>
    </section>
  );
}

function Fact({ label, children, strong = false }: { label: string; children: ReactNode; strong?: boolean }) {
  return (
    <div className="flex min-h-10 items-center justify-between gap-4 px-3.5 py-2">
      <dt className="text-[#56635e] dark:text-white/65">{label}</dt>
      <dd className={`min-w-0 text-right ${strong ? "font-medium" : ""}`}>{children}</dd>
    </div>
  );
}
