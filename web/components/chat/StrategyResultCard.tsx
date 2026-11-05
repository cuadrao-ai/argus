import { useEffect, useState } from "react";
import { ListTree, PencilLine } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ExecutionDetails } from "./ExecutionDetails";
import type { DecisionState } from "@/lib/argus-api";
import {
  confirmMemoryCandidate,
  declineMemoryCandidate,
  proposeSavedDecisionMemory,
  type MemoryCandidate,
} from "@/lib/memory-api";
import { displayResultActionLabel } from "@/lib/result-card-display";
import { resultCardViewModel } from "@/lib/result-card-view-model";
import { degradedValueClass } from "@/lib/failure-treatment";
import { isVisibleResultAction } from "@/lib/chat-result-actions";
import {
  AddDecisionButton,
  DecisionEditorPanel,
  CurrentDecisionChip,
  decisionActionClassName as actionClassName,
  decisionStateLabel,
  useDecisionDraft,
} from "./DecisionAffordance";
import ResultEquityChart from "./ResultEquityChart";
import { EntityToken } from "./entity-token";
import type { ChatActionOption, StrategyResultPayload } from "./types";

type StrategyResultCardProps = {
  result: StrategyResultPayload;
  onAction?: (action: ChatActionOption) => void;
  appearance?: "light" | "dark";
  canSaveDecision?: boolean;
  onDecisionUnavailable?: (artifactId: string) => void;
  onDecisionSaved?: (decisionState: DecisionState) => void;
  resumeDecisionArtifactId?: string | null;
  onDecisionResumeHandled?: () => void;
  /** Earned memory moment after a saved decision; backend policy still owns
   * cooldowns, consent, and sensitivity. */
  memoryProposalEnabled?: boolean;
};

export default function StrategyResultCard({
  appearance,
  canSaveDecision = true,
  onDecisionUnavailable,
  onDecisionSaved,
  resumeDecisionArtifactId,
  onDecisionResumeHandled,
  onAction,
  result,
  memoryProposalEnabled = false,
}: StrategyResultCardProps) {
  const { t, i18n } = useTranslation();
  const [memoryProposal, setMemoryProposal] = useState<MemoryCandidate | null>(
    null,
  );
  const [memoryProposalState, setMemoryProposalState] = useState<
    "idle" | "confirming" | "confirmed" | "failed"
  >("idle");
  const [savedDecisionState, setSavedDecisionState] =
    useState<DecisionState | null>(result.decisionState ?? null);
  useEffect(() => {
    setSavedDecisionState(result.decisionState ?? null);
  }, [result.decisionState]);
  const draft = useDecisionDraft({
    attachment: result.evidenceArtifactId
      ? { kind: "evidence_artifact", artifactId: result.evidenceArtifactId }
      : null,
    initialState: result.decisionState,
    onSaved: async (decision) => {
      setSavedDecisionState(decision.decision_state);
      onDecisionSaved?.(decision.decision_state);
      if (!memoryProposalEnabled) return;
      // Earned moment (memo 15.3): ask only after a saved decision, and
      // only if backend policy admits it.
      const savedNote = (decision.note ?? "").trim();
      const stateLabel = decisionStateLabel(decision.decision_state, t);
      try {
        const proposal = await proposeSavedDecisionMemory({
          label: `${result.strategyName}: ${stateLabel}`.slice(0, 120),
          value:
            savedNote || `${result.strategyName}: ${stateLabel}`.slice(0, 120),
          provenance: {
            source_kind: "decision_note",
            source_id: decision.id,
            source_version: decision.updated_at,
          },
        });
        if (proposal.created && proposal.candidate) {
          setMemoryProposal(proposal.candidate);
          setMemoryProposalState("idle");
        }
      } catch {
        // A quiet moment: proposal failures never surface here.
      }
    },
  });
  const viewModel = resultCardViewModel(result, { t, locale: i18n.language });
  const { copy: resultCardCopy, evidence: view, symbols } = viewModel;
  const resultActions = (result.actions ?? []).filter(isVisibleResultAction);
  const showBreakdownAction = resultActions.find(
    (action) => action.type === "show_breakdown",
  );
  const refineStrategyAction = resultActions.find(
    (action) => action.type === "refine_strategy",
  );
  const orderedActions: ChatActionOption[] = [];
  if (showBreakdownAction) orderedActions.push(showBreakdownAction);
  if (refineStrategyAction) orderedActions.push(refineStrategyAction);
  const renderedActions = orderedActions;
  const visibleDecisionState =
    savedDecisionState ?? result.decisionState ?? null;
  const canAddDecision =
    Boolean(result.evidenceArtifactId) && !visibleDecisionState;
  const { setOpen: openDecisionDraft } = draft;
  useEffect(() => {
    if (
      !canSaveDecision ||
      !canAddDecision ||
      !result.evidenceArtifactId ||
      resumeDecisionArtifactId !== result.evidenceArtifactId
    ) {
      return;
    }
    openDecisionDraft(true);
    onDecisionResumeHandled?.();
  }, [
    canAddDecision,
    canSaveDecision,
    openDecisionDraft,
    onDecisionResumeHandled,
    result.evidenceArtifactId,
    resumeDecisionArtifactId,
  ]);
  const showActionRail =
    renderedActions.length > 0 ||
    canAddDecision ||
    Boolean(visibleDecisionState);
  const revealClass =
    view.hero.tone === "negative"
      ? "argus-result-reveal-caution"
      : "argus-result-reveal-positive";
  const toneClassName =
    view.hero.tone === "positive"
      ? "text-[#5ba897]"
      : view.hero.tone === "negative"
        ? "text-[#d66d75]"
        : "text-[#5a677d] dark:text-[#7da0ca]";
  const trustGroups = view.trustGroups;
  const { periodDisplay, strategyLabel } = viewModel;

  return (
    <section
      aria-label="Hero + Delta Evidence Card"
      className={`argus-card-reveal ${revealClass} w-full overflow-hidden rounded-[20px] border border-[#c9c9cd] bg-white text-[#191c1f] dark:border-white/12 dark:bg-[#191c1f] dark:text-white`}
    >
      <div className="flex items-start justify-between gap-4 px-4 py-4 sm:px-5">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
            {symbols.length > 0 && <AssetSymbols symbols={symbols} />}
            <h3 className="font-display text-[18px] font-medium leading-tight tracking-[-0.18px] text-[#191c1f] dark:text-white">
              {strategyLabel}
            </h3>
          </div>
          <p className="mt-1.5 text-[13px] leading-snug tracking-[0.16px] text-[#8d969e]">
            {view.timeframeDisplay
              ? `${periodDisplay} · ${view.timeframeDisplay}`
              : periodDisplay}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {/* Passive status, not an action: plain muted text so it cannot be
              mistaken for another clickable pill (kept readable at 4.5:1). */}
          <span className="text-[11px] font-medium tracking-[0.16px] text-[#505a63] dark:text-white/65">
            {viewModel.statusLabel}
          </span>
        </div>
      </div>

      {result.chart && (
        <ResultEquityChart
          appearanceOverride={appearance}
          chart={result.chart}
          currencyFractionDigits={result.currencyFractionDigits}
          presentation="heroDeltaEvidence"
        />
      )}

      <div className="px-4 pb-4 pt-3 sm:px-5 sm:pb-4 sm:pt-3.5">
        <div>
          <p className="text-[14px] leading-snug tracking-[0.16px] text-[#505a63] dark:text-[#8d969e]">
            {view.hero.label}
          </p>
          {view.hero.unavailable ? (
            // Degraded data steps down: never a hero numeral, never a tone.
            <p className={`mt-1 text-[20px] leading-snug ${degradedValueClass}`}>
              {view.hero.value}
            </p>
          ) : (
            <p
              className={`mt-1 font-display text-[38px] font-medium leading-none tracking-[-0.38px] sm:text-[46px] ${toneClassName}`}
            >
              {view.hero.value}
            </p>
          )}
          <p className="mt-1.5 text-[15px] leading-snug tracking-[0.16px] text-[#505a63] dark:text-[#8d969e]">
            {view.hero.detail}
          </p>
        </div>

        <StatRail metrics={[view.benchmark, view.worstDrop]} />

        <TrustRail
          groups={trustGroups}
          label={t("chat.result_trust_strip_label", "Result trust context")}
        />

        <ExecutionDetails
          details={view.details}
          triggerLabel={t("chat.view_details", "View details")}
        />
      </div>

      {showActionRail && (
        <div className="flex flex-wrap gap-2 border-t border-[#c9c9cd]/30 px-4 py-3.5 dark:border-white/[0.06] sm:px-5">
          {renderedActions.map((action) => (
            <button
              key={action.id ?? action.type ?? action.label}
              type="button"
              onClick={() => onAction?.(action)}
              className={actionClassName}
            >
              <ResultActionIcon action={action} />
              {displayResultActionLabel(action, { copy: resultCardCopy })}
            </button>
          ))}
          {visibleDecisionState && <CurrentDecisionChip state={visibleDecisionState} />}
          {canAddDecision && (
            <AddDecisionButton
              onClick={() => {
                if (!canSaveDecision) {
                  onDecisionUnavailable?.(result.evidenceArtifactId!);
                  return;
                }
                draft.setOpen(!draft.open);
              }}
            />
          )}
        </div>
      )}

      {canAddDecision && draft.open && <DecisionEditorPanel draft={draft} />}
      {memoryProposal && memoryProposalState !== "confirmed" ? (
        <div className="mt-3 rounded-xl border border-black/[0.07] bg-black/[0.02] px-3.5 py-3 dark:border-white/[0.09] dark:bg-white/[0.03]">
          <p className="text-[13px] font-medium text-black dark:text-white">
            {t(
              "chat.memory.proposal_title",
              "Remember this saved decision?",
            )}
          </p>
          <p className="mt-1 text-[12.5px] leading-snug text-black/55 dark:text-white/55">
            {t("chat.memory.proposal_benefit", {
              label: memoryProposal.label,
              defaultValue:
                "Cuadrao would keep “{{label}}” so you can revisit and compare it later. You can inspect or remove it any time in Data Controls.",
            })}
          </p>
          {memoryProposalState === "failed" ? (
            <p
              role="alert"
              className="mt-1.5 text-[12px] text-[#b94c55] dark:text-[#e7a2a8]"
            >
              {t(
                "chat.memory.proposal_error",
                "Could not update memory. Try again.",
              )}
            </p>
          ) : null}
          <div className="mt-2.5 flex justify-end gap-2">
            <button
              type="button"
              disabled={memoryProposalState === "confirming"}
              onClick={() => {
                const candidateId = memoryProposal.id;
                setMemoryProposal(null);
                void declineMemoryCandidate(candidateId).catch(() => null);
              }}
              className="inline-flex min-h-9 items-center rounded-full border border-black/10 px-3 py-1.5 text-[12px] font-medium text-[#505a63] transition-colors hover:bg-black/[0.03] dark:border-white/10 dark:text-[#8d969e] dark:hover:bg-white/[0.05]"
            >
              {t("chat.memory.proposal_decline", "No thanks")}
            </button>
            <button
              type="button"
              disabled={memoryProposalState === "confirming"}
              onClick={async () => {
                setMemoryProposalState("confirming");
                try {
                  const confirmed = await confirmMemoryCandidate(
                    memoryProposal.id,
                  );
                  setMemoryProposalState(
                    confirmed.created ? "confirmed" : "failed",
                  );
                } catch {
                  setMemoryProposalState("failed");
                }
              }}
              className="inline-flex min-h-9 items-center gap-1.5 rounded-full bg-[#191c1f] px-3.5 py-1.5 text-[12px] font-medium text-white transition-colors hover:bg-black disabled:cursor-not-allowed disabled:opacity-55 dark:bg-white dark:text-[#191c1f] dark:hover:bg-white/90"
            >
              {t("chat.memory.proposal_confirm", "Remember")}
            </button>
          </div>
        </div>
      ) : null}
      {memoryProposalState === "confirmed" ? (
        <p className="mt-3 text-[12px] text-black/50 dark:text-white/50">
          {t(
            "chat.memory.proposal_saved",
            "Saved to memory. Manage it in Data Controls under Personalization.",
          )}
        </p>
      ) : null}
    </section>
  );
}

function StatRail({
  metrics,
}: {
  metrics: { label: string; value: string }[];
}) {
  return (
    <dl className="mt-3 grid gap-y-2.5 border-y border-[#c9c9cd]/22 py-2.5 dark:border-white/[0.04] sm:grid-cols-[minmax(0,1.55fr)_1px_minmax(104px,0.45fr)] sm:gap-x-5">
      <StatItem metric={metrics[0]} variant="benchmark" />
      <div
        aria-hidden="true"
        className="hidden h-8 self-center bg-[#c9c9cd]/18 dark:bg-white/[0.04] sm:block"
      />
      <StatItem metric={metrics[1]} />
    </dl>
  );
}

function StatItem({
  metric,
  variant = "default",
}: {
  metric?: { label: string; value: string; unavailable?: boolean };
  variant?: "default" | "benchmark";
}) {
  if (!metric) return null;
  const isBenchmark = variant === "benchmark";
  const valueClass = metric.unavailable
    ? degradedValueClass
    : isBenchmark
      ? "text-[15px] font-normal text-[#505a63] dark:text-[#8d969e] sm:whitespace-nowrap"
      : "text-[16px] font-medium text-[#191c1f] dark:text-white";

  return (
    <div className="min-w-0">
      <dt className="text-[13px] leading-snug tracking-[0.16px] text-[#8d969e]">
        {metric.label}
      </dt>
      <dd
        className={`mt-1.5 leading-snug tracking-[-0.08px] ${metric.unavailable ? "text-[15px] font-normal" : ""} ${valueClass}`}
      >
        {metric.value}
      </dd>
    </div>
  );
}

function TrustRail({ groups, label }: { groups: string[]; label: string }) {
  return (
    <div
      aria-label={label}
      className="mt-3 flex flex-col gap-1 text-[12px] leading-snug tracking-[0.16px] text-[#8d969e] sm:flex-row sm:flex-wrap sm:gap-x-4 sm:gap-y-1"
    >
      {groups.map((group) => (
        <p key={group}>{group}</p>
      ))}
    </div>
  );
}

function ResultActionIcon({ action }: { action: ChatActionOption }) {
  if (action.type === "show_breakdown") {
    return <ListTree className="h-3.5 w-3.5" />;
  }
  if (action.type === "refine_strategy") {
    return <PencilLine className="h-3.5 w-3.5" />;
  }
  return null;
}

function AssetSymbols({ symbols }: { symbols: string[] }) {
  return (
    <span className="flex flex-wrap gap-1.5">
      {symbols.map((symbol) => (
        <EntityToken key={symbol} kind="asset" surface="card">
          {symbol}
        </EntityToken>
      ))}
    </span>
  );
}
