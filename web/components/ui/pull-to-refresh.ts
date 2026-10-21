/**
 * Pull to refresh on a phone list, as one state machine: the finger pulls,
 * passes the threshold, lets go, the list's real reload runs, and the content
 * eases back once it has answered. A release short of the threshold, or a
 * gesture the browser took away, only eases back.
 */
export type RefreshOutcome = "updated" | "failed";

export type PullPhase =
  | { kind: "idle" }
  | { kind: "pulling"; distance: number }
  | { kind: "armed"; distance: number }
  | { kind: "refreshing" }
  | { kind: "settling"; outcome: RefreshOutcome | null };

export type PullEvent =
  | { kind: "move"; distance: number }
  | { kind: "release" }
  | { kind: "cancel" }
  | { kind: "settled"; outcome: RefreshOutcome }
  | { kind: "rested" };

export const PULL_IDLE: PullPhase = { kind: "idle" };
/** Damped travel that arms the reload. */
export const PULL_THRESHOLD = 64;
/** Where the content waits while the reload runs. */
export const PULL_HOLD = 52;
/** How long the content takes to ease back or to the hold. */
export const PULL_SETTLE_MS = 200;
/** Finger travel before the gesture picks an axis. */
export const PULL_SLOP = 6;
export const PULL_INDICATOR = 32;

export function pullStep(phase: PullPhase, event: PullEvent): PullPhase {
  switch (event.kind) {
    case "move":
      if (phase.kind !== "idle" && phase.kind !== "pulling" && phase.kind !== "armed") return phase;
      return { kind: event.distance >= PULL_THRESHOLD ? "armed" : "pulling", distance: Math.max(0, event.distance) };
    case "release":
      if (phase.kind === "armed") return { kind: "refreshing" };
      return phase.kind === "pulling" ? { kind: "settling", outcome: null } : phase;
    case "cancel":
      return phase.kind === "pulling" || phase.kind === "armed" ? { kind: "settling", outcome: null } : phase;
    case "settled":
      return phase.kind === "refreshing" ? { kind: "settling", outcome: event.outcome } : phase;
    case "rested":
      return phase.kind === "settling" ? PULL_IDLE : phase;
  }
}

/** The rubber band: travel follows the finger at first, then gives less and less. */
export function dampPull(raw: number): number {
  const reach = 200;
  const give = 0.6;
  return raw <= 0 ? 0 : reach * (1 - 1 / ((raw * give) / reach + 1));
}

/** What a phase paints: how far the content sits down, and the indicator above it. */
export type PullFrame = Readonly<{
  content: number;
  indicator: number;
  opacity: number;
  /** Turns of the arc, following the finger's progress to the threshold. */
  turn: number;
  /** 0 to 1: how much of the arc is drawn. */
  progress: number;
  spinning: boolean;
  /** Eased into place; while the finger is down it follows with no easing. */
  eased: boolean;
}>;

/** With reduced motion nothing travels: the content stays, the indicator fades in at its place, plain. */
export function pullFrame(phase: PullPhase, reduced: boolean): PullFrame {
  const gap = (content: number) => (reduced ? 8 : content / 2 - PULL_INDICATOR / 2);
  if (phase.kind === "pulling" || phase.kind === "armed") {
    const progress = Math.min(1, phase.distance / PULL_THRESHOLD);
    const content = reduced ? 0 : phase.distance;
    return { content, indicator: gap(content), opacity: progress, turn: reduced ? 0 : progress * 0.75, progress, spinning: false, eased: false };
  }
  if (phase.kind === "refreshing") {
    const content = reduced ? 0 : PULL_HOLD;
    return { content, indicator: gap(content), opacity: 1, turn: 0, progress: 1, spinning: true, eased: true };
  }
  return { content: 0, indicator: gap(0), opacity: 0, turn: 0, progress: phase.kind === "settling" ? 1 : 0, spinning: false, eased: phase.kind === "settling" };
}
