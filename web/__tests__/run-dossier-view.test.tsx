import { describe, expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";

import {
  DecisionEditor,
  decisionEditorKeyboardAction,
} from "../components/sidebar/command-palette/DecisionEditor";
import { decisionNoteElementOverflows } from "../components/sidebar/command-palette/DecisionNoteDisplay";
import {
  matchingDecisionResumeDraft,
  resolveDecisionSaveLifecycle,
  RunDossierView,
} from "../components/sidebar/command-palette/RunDossierView";
import { refreshCanonicalMutation } from "../lib/canonical-mutation-refresh";
import { formatRunDossierSetup } from "../lib/run-dossier-items";
import { withDossierResultFacts } from "../test-fixtures/dossier-result-facts";
import type {
  RunDossier,
  SearchDecisionAction,
  SearchRetestAction,
} from "../lib/run-dossier-contract";

const decisionAction: SearchDecisionAction = {
  type: "decision",
  availability: "available",
  evidence_artifact_id: "evidence-7",
  decision_state: "watching",
  note: "Hold through earnings.\nReview risk first.",
  run_label: "Weekly GLD pullback",
};

const dossierWithWatchingDecisionAndMultilineNote: RunDossier = withDossierResultFacts({
  run_id: "run-7",
  run_label: "Weekly GLD pullback",
  completed_at: "2026-07-31T14:30:00.000Z",
  result_message_id: "message-7",
  tested: {
    symbols: ["GLD"],
    strategy_family: "buy_and_hold",
    cadence: "weekly",
    timeframe: "1D",
    start_date: "2025-01-01",
    end_date: "2025-12-31",
  },
  outcome: {
    run_label: "Weekly GLD pullback",
    completed_at: "2026-07-31T14:30:00.000Z",
    benchmark_symbol: "SPY",
    metrics: [
      { name: "total_return_pct", value: 8.4 },
      { name: "benchmark_return_pct", value: 6.1 },
      { name: "delta_vs_benchmark_pct", value: 2.3 },
      { name: "max_drawdown_pct", value: -6.2 },
    ],
  },
  decision: {
    state: "watching",
    note: "Hold through earnings.\nReview risk first.",
    run_label: "Weekly GLD pullback",
  },
  actions: [
    {
      type: "retest_run",
      source_run_id: "run-7",
      run_label: "Weekly GLD pullback",
      window_policy: "preserve_start_ending_latest_available",
      contract_version: "argus_retest_run/v2",
      state: "new_data_available",
      reason_code: null,
      repair: null,
    },
    decisionAction,
  ],
});

const baseRetestAction = dossierWithWatchingDecisionAndMultilineNote
  .actions[0] as SearchRetestAction;

function retestAction(
  overrides: Partial<SearchRetestAction>,
): SearchRetestAction {
  return { ...baseRetestAction, ...overrides };
}

function visibleText(html: string): string {
  return html
    .replace(
      /<span[^>]*class="[^"]*sr-only[^"]*"[^>]*>[\s\S]*?<\/span>/g,
      "",
    )
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function retestButtonMarkup(html: string): string {
  return (
    html.match(
      /<button[^>]*data-retest-location="card-header"[^>]*>[\s\S]*?<\/button>/,
    )?.[0] ?? ""
  );
}

function retestDetailId(html: string): string | null {
  return (
    html.match(
      /<p[^>]*id="([^"]+)"[^>]*data-retest-state="(?:no_new_data|cant_do_it)"/,
    )?.[1] ?? null
  );
}

describe("single-run dossier view", () => {
  const renderRetestState = (action: SearchRetestAction) =>
    renderToStaticMarkup(
      <RunDossierView
        dossier={{
          ...dossierWithWatchingDecisionAndMultilineNote,
          actions: [action, decisionAction],
        }}
        totalRuns={7}
        decidedRuns={5}
        onOpenConversation={() => {}}
        onRetest={() => {}}
        onSaveDecision={async () => {}}
      />,
    );

  test("offers a normal Retest only when new data is available", () => {
    const html = renderRetestState(retestAction({
      state: "new_data_available",
    }));

    expect(html).toContain("Retest with current data");
    expect(html).not.toContain('data-retest-location="card-header" disabled=""');
  });

  test("shows same-period truth before click and disables Retest", () => {
    const html = renderRetestState(retestAction({
      state: "no_new_data",
    }));

    expect(html).toContain("Already up to date");
    expect(html).toContain("No new market data is available since this run.");
    expect(retestButtonMarkup(html)).toContain('disabled=""');
  });

  test("offers the exact server repair and leaves timeframe failures disabled", () => {
    const repairable = renderRetestState(retestAction({
      state: "cant_do_it",
      reason_code: "provider_history_start_unavailable",
      repair: {
        kind: "clamp_start",
        start_date: "2016-01-01",
        end_date: "2026-07-30",
      },
    }));
    const deadEnd = renderRetestState(retestAction({
      state: "cant_do_it",
      reason_code: "provider_timeframe_unavailable",
      repair: null,
    }));

    expect(repairable).toContain("Use available dates");
    expect(repairable).toContain("Jan 1, 2016");
    expect(repairable).toContain("Jul 30, 2026");
    expect(retestButtonMarkup(repairable)).not.toContain('disabled=""');
    expect(deadEnd).toContain("Retest unavailable");
    expect(deadEnd).toContain(
      "This run’s timeframe is not available for this market.",
    );
    expect(retestButtonMarkup(deadEnd)).toContain('disabled=""');
  });

  test("reserves generic hover help for the actionable current-data state", () => {
    const normal = renderRetestState(retestAction({
      state: "new_data_available",
    }));
    const samePeriod = renderRetestState(retestAction({
      state: "no_new_data",
    }));
    const repairable = renderRetestState(retestAction({
      state: "cant_do_it",
      reason_code: "kraken_ohlc_window_exceeded",
      repair: {
        kind: "clamp_start",
        start_date: "2024-08-01",
        end_date: "2026-07-30",
      },
    }));
    const unavailable = renderRetestState(retestAction({
      state: "cant_do_it",
      reason_code: "provider_timeframe_unavailable",
      repair: null,
    }));

    // Only the actionable state gets hover help; the tooltip no longer forces a cursor (buttons already have one).
    expect(retestButtonMarkup(normal)).not.toMatch(/<button[^>]*\sdisabled[\s=>]/);
    expect(retestButtonMarkup(samePeriod)).not.toContain("cursor:pointer");
    expect(retestButtonMarkup(repairable)).not.toContain("cursor:pointer");
    expect(retestButtonMarkup(unavailable)).not.toContain("cursor:pointer");
  });

  test("connects every visible Retest reason to its button", () => {
    const samePeriod = renderRetestState(retestAction({
      state: "no_new_data",
    }));
    const repairable = renderRetestState(retestAction({
      state: "cant_do_it",
      reason_code: "provider_history_start_unavailable",
      repair: {
        kind: "clamp_start",
        start_date: "2016-01-01",
        end_date: "2026-07-30",
      },
    }));
    const unavailable = renderRetestState(retestAction({
      state: "cant_do_it",
      reason_code: "provider_timeframe_unavailable",
      repair: null,
    }));

    for (const html of [samePeriod, repairable, unavailable]) {
      const detailId = retestDetailId(html);
      expect(detailId).not.toBeNull();
      expect(retestButtonMarkup(html)).toContain(
        `aria-describedby="${detailId}"`,
      );
    }
  });

  test("never inserts an empty strategy segment when a locale key is missing", () => {
    const missingTranslation = (() => "") as Parameters<
      typeof formatRunDossierSetup
    >[1];
    const setup = formatRunDossierSetup(
      {
        ...dossierWithWatchingDecisionAndMultilineNote,
        tested: {
          ...dossierWithWatchingDecisionAndMultilineNote.tested,
          strategy_family: "future_signal_strategy",
          cadence: null,
          start_date: null,
          end_date: null,
        },
      },
      missingTranslation,
      "en",
    );

    expect(setup).toEqual(["GLD", "Future signal strategy", "1D"]);
    expect(setup).not.toContain("");
  });

  test("makes the desktop dossier body the scroll region", () => {
    const html = renderToStaticMarkup(
      <RunDossierView
        dossier={dossierWithWatchingDecisionAndMultilineNote}
        totalRuns={7}
        decidedRuns={5}
        onOpenHistory={() => {}}
        onOpenConversation={() => {}}
        onRetest={() => {}}
        onSaveDecision={async () => {}}
      />,
    );

    expect(html).toMatch(
      /data-dossier-scroll-region="true"[^>]*class="[^"]*md:overflow-y-auto/,
    );
  });

  test("keeps all metrics in one compact separator-based definition grid", () => {
    const html = renderToStaticMarkup(
      <RunDossierView
        dossier={dossierWithWatchingDecisionAndMultilineNote}
        totalRuns={7}
        decidedRuns={5}
        onOpenHistory={() => {}}
        onOpenConversation={() => {}}
        onRetest={() => {}}
        onSaveDecision={async () => {}}
      />,
    );
    const metricsMarkup = html.match(
      /<dl[^>]*data-dossier-metrics-layout="compact"[^>]*>[\s\S]*?<\/dl>/,
    )?.[0];

    expect(metricsMarkup).toBeDefined();
    expect(metricsMarkup?.match(/<dt/g)).toHaveLength(4);
    expect(metricsMarkup?.match(/<dd/g)).toHaveLength(4);
    expect(metricsMarkup).toContain("border-l");
    expect(metricsMarkup).toContain("border-t");
    expect(metricsMarkup).not.toContain("bg-black/[0.025]");
  });

  test("uses the full final row for odd metric counts without changing even grids", () => {
    const renderWithMetricCount = (count: number) =>
      renderToStaticMarkup(
        <RunDossierView
          dossier={{
            ...dossierWithWatchingDecisionAndMultilineNote,
            outcome: {
              ...dossierWithWatchingDecisionAndMultilineNote.outcome,
              metrics:
                dossierWithWatchingDecisionAndMultilineNote.outcome.metrics.slice(
                  0,
                  count,
                ),
            },
          }}
          totalRuns={7}
          decidedRuns={5}
          onOpenHistory={() => {}}
          onOpenConversation={() => {}}
          onRetest={() => {}}
          onSaveDecision={async () => {}}
        />,
      );

    const oneMetric = renderWithMetricCount(1);
    const threeMetrics = renderWithMetricCount(3);
    const fourMetrics = renderWithMetricCount(4);

    expect(oneMetric.match(/data-dossier-metric-span="full"/g)).toHaveLength(1);
    expect(oneMetric).toMatch(
      /data-dossier-metric-span="full"[^>]*class="[^"]*col-span-2/,
    );
    expect(threeMetrics.match(/data-dossier-metric-span="full"/g)).toHaveLength(
      1,
    );
    expect(threeMetrics).toMatch(
      /data-dossier-metric-span="full"[^>]*class="[^"]*col-span-2/,
    );
    expect(fourMetrics).not.toContain('data-dossier-metric-span="full"');
  });

  test("shows one run decision beside its verbatim note without repeated headings", () => {
    const html = renderToStaticMarkup(
      <RunDossierView
        dossier={dossierWithWatchingDecisionAndMultilineNote}
        totalRuns={7}
        decidedRuns={5}
        onOpenHistory={() => {}}
        onOpenConversation={() => {}}
        onRetest={() => {}}
        onSaveDecision={async () => {}}
      />,
    );
    const text = visibleText(html);

    expect(text.match(/\bWatching\b/g)).toHaveLength(1);
    expect(html).toContain("Hold through earnings.\nReview risk first.");
    expect(html).toContain("whitespace-pre-wrap");
    expect(text).not.toContain("What you tested");
    expect(text).not.toContain("How it went");
    expect(html).not.toMatch(/>Decision</);
    expect(text).not.toContain("Your note");
    expect(text).toContain("Backtest");
    expect(html).not.toContain('data-decision-chip="true"');
    expect(text).toContain("5 of 7 decided");
    expect(text).toContain("Decision history");
    expect(text.lastIndexOf("Decision history")).toBeGreaterThan(
      text.lastIndexOf("Open in conversation"),
    );
    expect(text).toContain("Edit");
    expect(text).not.toContain("Change decision");
    expect(html).toMatch(/data-decision-state-row="true"/);
    expect(html).toMatch(/data-decision-edit="true"[^>]*class="[^"]*h-8/);
  });

  test("keeps a long note in panel flow behind an accessible disclosure", () => {
    const longNote = `${"Review the downside before increasing conviction. ".repeat(9)}\nNext review: after earnings.`;
    const html = renderToStaticMarkup(
      <RunDossierView
        dossier={{
          ...dossierWithWatchingDecisionAndMultilineNote,
          decision: {
            ...dossierWithWatchingDecisionAndMultilineNote.decision!,
            note: longNote,
          },
        }}
        totalRuns={7}
        decidedRuns={5}
        onOpenHistory={() => {}}
        onOpenConversation={() => {}}
        onRetest={() => {}}
        onSaveDecision={async () => {}}
      />,
    );

    expect(html).toContain(longNote);
    expect(html).toContain("Show full note");
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain("line-clamp-5");
    const noteMarkup = html.match(
      /<p[^>]*data-decision-note="true"[^>]*>[\s\S]*?<\/p>/,
    )?.[0];
    expect(noteMarkup).toBeDefined();
    expect(noteMarkup).not.toContain("overflow-y-auto");
  });

  test("clamps before measuring narrow-screen note overflow", () => {
    const potentiallyWrappedNote = "Wide words can wrap on a narrow mobile dossier.";
    const html = renderToStaticMarkup(
      <RunDossierView
        dossier={{
          ...dossierWithWatchingDecisionAndMultilineNote,
          decision: {
            ...dossierWithWatchingDecisionAndMultilineNote.decision!,
            note: potentiallyWrappedNote,
          },
        }}
        totalRuns={7}
        decidedRuns={5}
        onOpenHistory={() => {}}
        onOpenConversation={() => {}}
        onRetest={() => {}}
        onSaveDecision={async () => {}}
      />,
    );

    expect(html).toMatch(/data-decision-note="true"[^>]*line-clamp-5/);
    expect(
      decisionNoteElementOverflows({ scrollHeight: 101, clientHeight: 100 }),
    ).toBeTrue();
    expect(
      decisionNoteElementOverflows({ scrollHeight: 100, clientHeight: 100 }),
    ).toBeFalse();
  });

  test("puts the existing retest action in the card header with honest copy", () => {
    const html = renderToStaticMarkup(
      <RunDossierView
        dossier={dossierWithWatchingDecisionAndMultilineNote}
        totalRuns={7}
        decidedRuns={5}
        onOpenHistory={() => {}}
        onOpenConversation={() => {}}
        onRetest={() => {}}
        onSaveDecision={async () => {}}
      />,
    );
    const text = visibleText(html);

    expect(text).toContain("Retest with current data");
    expect(text).not.toContain("Run it fresh");
    expect(html.indexOf("Retest with current data")).toBeLessThan(
      html.indexOf("Weekly GLD pullback"),
    );
    expect(html).toContain('data-retest-location="card-header"');
  });

  test("shows one quiet undecided state and an add action", () => {
    const html = renderToStaticMarkup(
      <RunDossierView
        dossier={{
          ...dossierWithWatchingDecisionAndMultilineNote,
          decision: null,
          actions: [
            {
              ...decisionAction,
              decision_state: null,
              note: null,
            },
          ],
        }}
        totalRuns={7}
        decidedRuns={5}
        onOpenHistory={() => {}}
        onOpenConversation={() => {}}
        onRetest={() => {}}
        onSaveDecision={async () => {}}
      />,
    );
    const text = visibleText(html);

    expect(text.match(/No decision saved/g)).toHaveLength(1);
    expect(text).toContain("Add decision");
  });

  test("keeps a conversion-gated decision action visibly available", () => {
    const html = renderToStaticMarkup(
      <RunDossierView
        dossier={{
          ...dossierWithWatchingDecisionAndMultilineNote,
          decision: null,
          actions: [
            {
              ...decisionAction,
              availability: "account_conversion_required",
              decision_state: null,
              note: null,
            },
          ],
        }}
        totalRuns={7}
        decidedRuns={5}
        onOpenHistory={() => {}}
        onOpenConversation={() => {}}
        onRetest={() => {}}
        onSaveDecision={async () => {
          throw new Error("guest mutation must stay unreachable");
        }}
      />,
    );

    expect(visibleText(html)).toContain("Add decision");
  });

  test("resumes only the exact available dossier action with its preserved note", () => {
    const target = {
      artifactId: "evidence-7",
      runId: "run-7",
      decisionState: "watching" as const,
      note: "Keep this exact note",
    };

    expect(
      matchingDecisionResumeDraft({
        action: decisionAction,
        runId: "run-7",
        target,
      }),
    ).toEqual({ state: "watching", note: "Keep this exact note" });
    expect(
      matchingDecisionResumeDraft({
        action: decisionAction,
        runId: "another-run",
        target,
      }),
    ).toBeNull();
    expect(
      matchingDecisionResumeDraft({
        action: { ...decisionAction, availability: "account_conversion_required" },
        runId: "run-7",
        target,
      }),
    ).toBeNull();
  });

  test("accessibly disables transcript navigation without a result anchor", () => {
    const html = renderToStaticMarkup(
      <RunDossierView
        dossier={{
          ...dossierWithWatchingDecisionAndMultilineNote,
          result_message_id: null,
        }}
        totalRuns={7}
        decidedRuns={5}
        onOpenHistory={() => {}}
        onOpenConversation={() => {}}
        onRetest={() => {}}
        onSaveDecision={async () => {}}
      />,
    );

    expect(html).toMatch(
      /<button[^>]*aria-label="Open in conversation"[^>]*disabled=""/,
    );
  });

  test("uses an accessible icon-only return to the latest run", () => {
    const html = renderToStaticMarkup(
      <RunDossierView
        dossier={dossierWithWatchingDecisionAndMultilineNote}
        totalRuns={7}
        decidedRuns={5}
        onBackToLatest={() => {}}
        onOpenHistory={() => {}}
        onOpenConversation={() => {}}
        onRetest={() => {}}
        onSaveDecision={async () => {}}
      />,
    );

    expect(visibleText(html)).not.toContain("Dossier");
    expect(html).toMatch(
      /<button[^>]*aria-label="Back to latest run"[^>]*class="[^"]*h-11[^"]*w-11/,
    );
  });
});

describe("decision editor", () => {
  const draft = {
    state: "watching" as const,
    note: "First line\nSecond line",
  };

  test("collapses and acknowledges only after mutation and canonical refresh succeed", async () => {
    const events: string[] = [];

    const outcome = await resolveDecisionSaveLifecycle({
      draft,
      commit: async () => {
        events.push("mutation");
        await Promise.resolve();
        events.push("canonical_refresh");
      },
    });

    expect(events).toEqual(["mutation", "canonical_refresh"]);
    expect(outcome).toEqual({ draft: null, error: false, saved: true });
  });

  test("preserves the exact draft and reports error when mutation rejects", async () => {
    const events: string[] = [];

    const outcome = await resolveDecisionSaveLifecycle({
      draft,
      commit: async () => {
        events.push("mutation");
        throw new Error("mutation failed");
      },
    });

    expect(events).toEqual(["mutation"]);
    expect(outcome).toEqual({ draft, error: true, saved: false });
  });

  test("preserves the exact draft and reports error when canonical refresh rejects", async () => {
    const events: string[] = [];

    const outcome = await resolveDecisionSaveLifecycle({
      draft,
      commit: async () => {
        events.push("mutation");
        await Promise.resolve();
        events.push("canonical_refresh");
        throw new Error("canonical refresh failed");
      },
    });

    expect(events).toEqual(["mutation", "canonical_refresh"]);
    expect(outcome).toEqual({ draft, error: true, saved: false });
  });

  test("canonical refresh error treatment preserves the rejected promise", async () => {
    let readErrorWasMarked = false;
    let rejected = false;
    try {
      await refreshCanonicalMutation({
        refresh: async () => {
          throw new Error("canonical refresh failed");
        },
        onFailure: () => {
          readErrorWasMarked = true;
        },
      });
    } catch {
      rejected = true;
    }

    expect(readErrorWasMarked).toBe(true);
    expect(rejected).toBe(true);
  });

  test("reserves save and prevent-default for modified Enter", () => {
    expect(
      decisionEditorKeyboardAction({
        key: "Enter",
        metaKey: false,
        ctrlKey: false,
      }),
    ).toEqual({ save: false, preventDefault: false });
    expect(
      decisionEditorKeyboardAction({
        key: "Enter",
        metaKey: true,
        ctrlKey: false,
      }),
    ).toEqual({ save: true, preventDefault: true });
    expect(
      decisionEditorKeyboardAction({
        key: "Enter",
        metaKey: false,
        ctrlKey: true,
      }),
    ).toEqual({ save: true, preventDefault: true });
    expect(
      decisionEditorKeyboardAction({
        key: "Escape",
        metaKey: true,
        ctrlKey: false,
      }),
    ).toEqual({ save: false, preventDefault: false });
  });

  test("keeps visible cancel/save controls and preserves an errored draft", () => {
    const html = renderToStaticMarkup(
      <DecisionEditor
        action={decisionAction}
        decisionState="watching"
        note="First line\nSecond line"
        saving={false}
        error
        onDecisionStateChange={() => {}}
        onNoteChange={() => {}}
        onCancel={() => {}}
        onSave={() => {}}
      />,
    );
    const text = visibleText(html);

    expect(text).toContain("Cancel");
    expect(text).toContain("Save");
    expect(text).toContain("Something went wrong. Please try again.");
    // React's server renderer serializes a controlled textarea newline as
    // the two-character escape sequence; the controlled value is unchanged.
    expect(html).toContain("First line\\nSecond line");
  });

  test("caps authored notes at 500 characters and shows a near-limit count", () => {
    const html = renderToStaticMarkup(
      <DecisionEditor
        action={decisionAction}
        decisionState="watching"
        note={"x".repeat(480)}
        saving={false}
        error={false}
        onDecisionStateChange={() => {}}
        onNoteChange={() => {}}
        onCancel={() => {}}
        onSave={() => {}}
      />,
    );

    expect(html).not.toMatch(/<textarea[^>]*maxLength=/);
    expect(visibleText(html)).toContain("480 / 500");
  });

  test("lets a legacy long note be canceled but not resaved unchanged", () => {
    const html = renderToStaticMarkup(
      <DecisionEditor
        action={decisionAction}
        decisionState="watching"
        note={"x".repeat(501)}
        saving={false}
        error={false}
        onDecisionStateChange={() => {}}
        onNoteChange={() => {}}
        onCancel={() => {}}
        onSave={() => {}}
      />,
    );

    expect(html).toMatch(/<button[^>]*>Cancel<\/button>/);
    expect(html).not.toMatch(/<button[^>]*disabled=""[^>]*>Cancel<\/button>/);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>[\s\S]*Save decision/);
    expect(visibleText(html)).toContain("501 / 500");
  });

  test("associates the decision note textarea with an explicit label", () => {
    const html = renderToStaticMarkup(
      <DecisionEditor
        action={decisionAction}
        decisionState="watching"
        note=""
        saving={false}
        error={false}
        onDecisionStateChange={() => {}}
        onNoteChange={() => {}}
        onCancel={() => {}}
        onSave={() => {}}
      />,
    );

    expect(html).toContain(
      '<label for="command-palette-decision-note" class="sr-only">Decision note</label>',
    );
    expect(html).toMatch(
      /<textarea[^>]*id="command-palette-decision-note"[^>]*placeholder="Optional note for future you"/,
    );
  });
});
