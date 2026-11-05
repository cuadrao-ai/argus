"use client";

import { ArrowLeft, ChevronRight, PencilLine, RotateCcw } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  commandPaletteDecisionStateFallback,
  commandPaletteDecisionVerb,
} from "@/lib/command-palette-items";
import type {
  DecisionState,
  RunDossier,
  SearchDecisionAction,
  SearchRetestAction,
} from "@/lib/run-dossier-contract";
import {
  formatRunDossierMetrics,
  formatRunDossierSetup,
} from "@/lib/run-dossier-items";
import type { GuestDossierDecisionResumeTarget } from "@/lib/guest-conversion";
import { Tooltip } from "@/components/ui/Tooltip";
import { compactDateDisplay } from "@/lib/date-range-display";
import { resultReadoutFacts } from "@/lib/result-readout-facts";
import { resultQuickTakeText } from "@/lib/result-readout-display";

import { DecisionEditor } from "./DecisionEditor";
import { DecisionNoteDisplay } from "./DecisionNoteDisplay";

type RunDossierViewProps = {
  dossier: RunDossier;
  totalRuns: number;
  decidedRuns: number;
  onBackToLatest?: () => void;
  onOpenHistory?: () => void;
  /**
   * Opens the conversation from inside the body.
   *
   * Omitted when the host pins that action itself, as the sheet does, so the
   * two do not both appear. The pane has no footer, so it passes one.
   */
  onOpenConversation?: () => void;
  onRetest: (sourceRunId: string) => Promise<void> | void;
  onSaveDecision: (
    action: SearchDecisionAction,
    draft: { decision_state: DecisionState; note: string },
  ) => Promise<void>;
  onDecisionUnavailable?: (target: DossierDecisionResumeTarget) => void;
  resumeDecisionTarget?: DossierDecisionResumeTarget | null;
  onDecisionResumeHandled?: () => void;
  openConversationDisabled?: boolean;
  retestDisabled?: boolean;
};

export type DecisionDraft = {
  state: DecisionState | null;
  note: string;
};

export type DossierDecisionResumeTarget = GuestDossierDecisionResumeTarget;

export function matchingDecisionResumeDraft({
  action,
  runId,
  target,
}: {
  action: SearchDecisionAction | undefined;
  runId: string;
  target: DossierDecisionResumeTarget | null | undefined;
}): DecisionDraft | null {
  if (
    !action ||
    !target ||
    action.availability !== "available" ||
    action.evidence_artifact_id !== target.artifactId ||
    runId !== target.runId
  ) {
    return null;
  }
  return { state: target.decisionState, note: target.note };
}

export type DecisionSaveLifecycleOutcome = {
  draft: DecisionDraft | null;
  error: boolean;
  saved: boolean;
};

export async function resolveDecisionSaveLifecycle({
  draft,
  commit,
}: {
  draft: DecisionDraft;
  commit: () => Promise<void>;
}): Promise<DecisionSaveLifecycleOutcome> {
  try {
    await commit();
    return { draft: null, error: false, saved: true };
  } catch {
    return { draft, error: true, saved: false };
  }
}

function formatCompletedAt(value: string, locale: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function RunDossierView({
  dossier,
  totalRuns,
  decidedRuns,
  onBackToLatest,
  onOpenHistory,
  onOpenConversation,
  onRetest,
  onSaveDecision,
  onDecisionUnavailable,
  resumeDecisionTarget,
  onDecisionResumeHandled,
  openConversationDisabled = false,
  retestDisabled = false,
}: RunDossierViewProps) {
  const { t, i18n } = useTranslation();
  const retestDetailId = useId();
  const locale = i18n.resolvedLanguage ?? i18n.language ?? "en";
  const quickTake = resultQuickTakeText(resultReadoutFacts(dossier.outcome.result_fact_bank), t, locale);
  const decisionAction = dossier.actions.find(
    (action): action is SearchDecisionAction => action.type === "decision",
  );
  const retestAction = dossier.actions.find(
    (action): action is SearchRetestAction => action.type === "retest_run",
  );
  const [draft, setDraft] = useState<DecisionDraft | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
  const [saved, setSaved] = useState(false);
  const activeRunIdRef = useRef(dossier.run_id);

  useEffect(() => {
    activeRunIdRef.current = dossier.run_id;
    setDraft(null);
    setSaving(false);
    setSaveFailed(false);
    setSaved(false);
  }, [decisionAction?.evidence_artifact_id, dossier.run_id]);

  useEffect(() => {
    const resumedDraft = matchingDecisionResumeDraft({
      action: decisionAction,
      runId: dossier.run_id,
      target: resumeDecisionTarget,
    });
    if (!resumedDraft) return;
    setSaved(false);
    setSaveFailed(false);
    setDraft(resumedDraft);
    onDecisionResumeHandled?.();
  }, [
    decisionAction,
    dossier.run_id,
    onDecisionResumeHandled,
    resumeDecisionTarget,
  ]);

  useEffect(() => {
    if (!saved) return;
    const timeout = window.setTimeout(() => setSaved(false), 2000);
    return () => window.clearTimeout(timeout);
  }, [saved]);

  const setup = useMemo(
    () => formatRunDossierSetup(dossier, t, locale),
    [dossier, locale, t],
  );
  const metrics = useMemo(
    () => formatRunDossierMetrics(dossier, t, locale),
    [dossier, locale, t],
  );
  const completedAt = formatCompletedAt(dossier.completed_at, locale);

  const startDecisionEdit = () => {
    if (!decisionAction) return;
    const nextDraft = {
      state: decisionAction.decision_state ?? null,
      note: decisionAction.note ?? "",
    };
    if (decisionAction.availability === "account_conversion_required") {
      onDecisionUnavailable?.({
        surface: "omnisearch_dossier",
        artifactId: decisionAction.evidence_artifact_id,
        runId: dossier.run_id,
        decisionState: nextDraft.state,
        note: nextDraft.note,
      });
      return;
    }
    setSaved(false);
    setSaveFailed(false);
    setDraft(nextDraft);
  };

  const saveDecision = async (
    action: SearchDecisionAction,
    nextDraft: { decision_state: DecisionState; note: string },
  ) => {
    if (saving) return;
    const runId = dossier.run_id;
    const lifecycleDraft = {
      state: nextDraft.decision_state,
      note: nextDraft.note,
    };
    setSaving(true);
    setSaveFailed(false);
    try {
      const outcome = await resolveDecisionSaveLifecycle({
        draft: lifecycleDraft,
        commit: () => onSaveDecision(action, nextDraft),
      });
      if (activeRunIdRef.current !== runId) return;
      setDraft(outcome.draft);
      setSaveFailed(outcome.error);
      setSaved(outcome.saved);
    } finally {
      if (activeRunIdRef.current === runId) setSaving(false);
    }
  };

  const conversationUnavailable =
    openConversationDisabled || dossier.result_message_id === null;
  const retestRepair = retestAction?.repair ?? null;
  const retestUnavailable =
    retestAction?.state === "no_new_data" ||
    (retestAction?.state === "cant_do_it" && retestRepair === null);
  const retestButtonDisabled = retestDisabled || retestUnavailable;
  const repairStart = compactDateDisplay(retestRepair?.start_date, locale);
  const repairEnd = compactDateDisplay(retestRepair?.end_date, locale);
  const retestLabel =
    retestAction?.state === "no_new_data"
      ? t("command_palette.retest_already_current", "Already up to date")
      : retestRepair
        ? t("command_palette.retest_available_dates", "Use available dates")
        : retestAction?.state === "cant_do_it"
          ? t("command_palette.retest_unavailable", "Retest unavailable")
          : t("command_palette.retest_current_data", "Retest with current data");
  const retestDetail =
    retestAction?.state === "no_new_data"
      ? t(
          "command_palette.retest_no_new_data",
          "No new market data is available since this run.",
        )
      : retestRepair && repairStart && repairEnd
        ? t(
            "command_palette.retest_repaired_period",
            "Retest from {{start}} through {{end}}.",
          )
            .replace("{{start}}", repairStart)
            .replace("{{end}}", repairEnd)
        : retestAction?.reason_code === "provider_timeframe_unavailable"
          ? t(
              "command_palette.retest_timeframe_unavailable",
              "This run’s timeframe is not available for this market.",
            )
          : null;
  const retestButton = retestAction ? (
    <button
      type="button"
      data-retest-location="card-header"
      aria-describedby={retestDetail ? retestDetailId : undefined}
      disabled={retestButtonDisabled}
      onClick={() => void onRetest(retestAction.source_run_id)}
      className="inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-full border border-black/10 bg-white/60 px-3 text-[11px] font-medium text-black/65 transition-colors hover:bg-black/[0.03] disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/10 dark:bg-white/[0.04] dark:text-white/65 dark:hover:bg-white/[0.08]"
    >
      <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
      {retestLabel}
    </button>
  ) : null;

  return (
    <div
      data-dossier-scroll-region="true"
      className="flex min-h-0 flex-1 flex-col md:overflow-y-auto"
    >
      {onBackToLatest ? (
        <button
          type="button"
          aria-label={t(
            "command_palette.back_to_latest_run",
            "Back to latest run",
          )}
          onClick={onBackToLatest}
          className="mb-3 inline-flex h-11 w-11 items-center justify-center rounded-full text-black/55 transition-colors hover:bg-black/[0.03] hover:text-black dark:text-white/55 dark:hover:bg-white/[0.05] dark:hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </button>
      ) : null}
      <div className="rounded-[14px] border border-black/5 bg-white/70 p-4 dark:border-white/10 dark:bg-[#1f2225]/70">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="inline-flex rounded-full border border-black/8 bg-white/50 px-2.5 py-1 text-[11px] font-semibold text-black/45 dark:border-white/10 dark:bg-white/[0.03] dark:text-white/45">
              {t("command_palette.type.backtest", "Backtest")}
            </span>
            {completedAt && (
              <span className="text-[11px] text-black/35 dark:text-white/35">
                {completedAt}
              </span>
            )}
          </div>
          {retestButton &&
          retestAction?.state === "new_data_available" &&
          !retestButtonDisabled ? (
            <Tooltip
              content={t(
                "command_palette.retest_tooltip",
                "Reuse this setup with the latest data.",
              )}
              side="bottom"
            >
              {retestButton}
            </Tooltip>
          ) : (
            retestButton
          )}
        </div>

        {retestDetail ? (
          <p
            id={retestDetailId}
            data-retest-state={retestAction?.state}
            className="mt-2 text-[11px] leading-relaxed text-black/45 dark:text-white/45"
          >
            {retestDetail}
          </p>
        ) : null}

        <h3 className="mt-3 font-display text-[20px] font-medium leading-tight text-black dark:text-white">
          {dossier.run_label}
        </h3>

        {setup.length > 0 && (
          <p className="mt-3 text-[12px] leading-relaxed text-black/50 dark:text-white/50">
            {setup.join(" · ")}
          </p>
        )}

        {(quickTake || metrics.length > 0) && (
          <div className="mt-4 border-t border-black/5 pt-4 dark:border-white/5">
            {quickTake && (
              <p className="text-[13px] leading-relaxed text-black/65 dark:text-white/65">
                {quickTake}
              </p>
            )}
            {metrics.length > 0 && (
              <dl
                data-dossier-metrics-layout="compact"
                className="mt-3 grid grid-cols-2 border-t border-black/[0.06] dark:border-white/[0.08]"
              >
                {metrics.map((metric, index) => {
                  const spansFullRow =
                    metrics.length % 2 === 1 && index === metrics.length - 1;
                  return (
                    <div
                      key={metric.name}
                      data-dossier-metric-span={
                        spansFullRow ? "full" : undefined
                      }
                      className={`flex min-w-0 items-baseline justify-between gap-2 py-2 ${
                        spansFullRow
                          ? "col-span-2"
                          : index % 2 === 0
                            ? "pr-3"
                            : "border-l border-black/[0.06] pl-3 dark:border-white/[0.08]"
                      } ${
                        index >= 2
                          ? "border-t border-black/[0.06] dark:border-white/[0.08]"
                          : ""
                      }`}
                    >
                      <dt className="min-w-0 text-[9px] font-semibold uppercase tracking-wider text-black/35 dark:text-white/35">
                        {metric.name}
                      </dt>
                      <dd className="shrink-0 text-[13px] font-medium text-black/70 dark:text-white/70">
                        {metric.value}
                      </dd>
                    </div>
                  );
                })}
              </dl>
            )}
          </div>
        )}

        <div className="mt-4 border-t border-black/5 pt-4 dark:border-white/5">
          {draft && decisionAction ? (
            <DecisionEditor
              action={decisionAction}
              decisionState={draft.state}
              note={draft.note}
              saving={saving}
              error={saveFailed}
              onDecisionStateChange={(state) => {
                setSaveFailed(false);
                setDraft((current) =>
                  current ? { ...current, state } : current,
                );
              }}
              onNoteChange={(note) => {
                setSaveFailed(false);
                setDraft((current) =>
                  current ? { ...current, note } : current,
                );
              }}
              onCancel={() => {
                setDraft(null);
                setSaveFailed(false);
              }}
              onSave={saveDecision}
            />
          ) : (
            <div className="min-w-0">
              <div
                data-decision-state-row="true"
                className="flex min-h-8 items-center gap-2"
              >
                {dossier.decision ? (
                  <span className="inline-flex h-8 items-center rounded-full border border-black/8 px-2.5 text-[11px] font-semibold text-black/55 dark:border-white/10 dark:text-white/55">
                    {t(
                      `chat.result_card.decision_states.${dossier.decision.state}`,
                      commandPaletteDecisionStateFallback(
                        dossier.decision.state,
                      ),
                    )}
                  </span>
                ) : (
                  <p className="text-[13px] text-black/40 dark:text-white/40">
                    {t(
                      "command_palette.no_decision_saved",
                      "No decision saved",
                    )}
                  </p>
                )}
              {decisionAction && (
                <button
                  type="button"
                  data-decision-edit="true"
                  onClick={startDecisionEdit}
                  className="relative inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border border-black/10 px-2.5 text-[11px] font-medium text-black/60 transition-colors before:absolute before:-inset-y-1.5 before:inset-x-0 hover:bg-black/[0.03] dark:border-white/10 dark:text-white/60 dark:hover:bg-white/[0.05]"
                >
                  <PencilLine className="h-3.5 w-3.5" aria-hidden="true" />
                  {commandPaletteDecisionVerb(decisionAction) === "add"
                    ? t("command_palette.add_decision_short", "Add decision")
                    : t(
                        "command_palette.change_decision_short",
                        "Edit",
                      )}
                </button>
              )}
              </div>
              {dossier.decision?.note ? (
                <DecisionNoteDisplay
                  key={`${dossier.run_id}:${dossier.decision.note}`}
                  note={dossier.decision.note}
                />
              ) : null}
            </div>
          )}
          {saved && (
            <p
              className="mt-2 text-[12px] text-[#3f816f] dark:text-[#7bc1ad]"
              aria-live="polite"
            >
              {t("command_palette.decision_saved", "Saved")}
            </p>
          )}
        </div>
      </div>

      {onOpenConversation ? (
        <button
          type="button"
          aria-label={t(
            "command_palette.open_in_conversation",
            "Open in conversation",
          )}
          disabled={conversationUnavailable}
          onClick={onOpenConversation}
          className="mt-auto flex min-h-11 shrink-0 items-center justify-between pt-4 text-left text-[12px] text-black/35 transition-colors hover:text-black disabled:cursor-not-allowed disabled:opacity-50 dark:text-white/35 dark:hover:text-white"
        >
          <span>
            {t(
              "command_palette.open_in_conversation",
              "Open in conversation",
            )}
          </span>
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
      ) : null}

      <button
        type="button"
        disabled={!onOpenHistory}
        onClick={onOpenHistory}
        className="flex min-h-11 shrink-0 items-center justify-between border-t border-black/5 text-left text-[12px] text-black/45 transition-colors hover:text-black disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/5 dark:text-white/45 dark:hover:text-white"
      >
        <span>{t("command_palette.decision_history", "Decision history")}</span>
        <span className="inline-flex items-center gap-1">
          {t("command_palette.decision_history_count", {
            decided: decidedRuns,
            total: totalRuns,
            defaultValue: `${decidedRuns} of ${totalRuns} decided`,
          })}
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </span>
      </button>
    </div>
  );
}
