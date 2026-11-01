// One scroll position drives the whole product scene. Progress `p` runs from 0
// to 1. Moving parts become CSS variables, and text changes become beats.

export const NARROW_WIDTH = 900;

const BOARD_WIDTH = 1290;
const BOARD_HEIGHT = 760;
const FRAME_INSET = 114;

export type IslandStep = "waiting" | "incoming" | "reading" | "ready" | "approved" | "accountant";
export type InvoiceState = "reading" | "ready" | "approved";
export type DockStage = 0 | 1 | 2;

export type SceneBeat = {
  island: IslandStep;
  arrived: boolean;
  invoice: InvoiceState;
  checks: number;
  exported: boolean;
  dock: DockStage;
};

const ISLAND: readonly (readonly [number, IslandStep])[] = [
  [0, "waiting"],
  [0.28, "incoming"],
  [0.4, "reading"],
  [0.56, "ready"],
  [0.655, "approved"],
  [0.76, "accountant"],
];

const ARRIVED = 0.46;
const READY = 0.56;
const APPROVED = 0.655;
const CHECKS = [0.74, 0.79, 0.84, 0.89];
const EXPORTED = 0.935;
const DOCK = [0.34, 0.72];

const BEAT_POINTS = [
  ...new Set([...ISLAND.map(([at]) => at), ARRIVED, READY, APPROVED, ...CHECKS, EXPORTED, ...DOCK]),
].sort((a, b) => a - b);

const clamp = (value: number) => Math.min(1, Math.max(0, value));
const lerp = (from: number, to: number, t: number) => from + (to - from) * t;

function seg(p: number, from: number, to: number): number {
  const t = clamp((p - from) / (to - from));
  return t * t * (3 - 2 * t);
}

export function scrollProgress(top: number, height: number, viewport: number): number {
  const travel = height - viewport;
  return travel > 0 ? clamp(-top / travel) : 1;
}

// The last point where a beat changed. Scrolling between two points keeps the
// same number, so the page renders only when the text changes.
export function beatPoint(p: number): number {
  return BEAT_POINTS.findLast((point) => point <= p) ?? 0;
}

export function beatAt(p: number): SceneBeat {
  return {
    island: ISLAND.findLast(([at]) => at <= p)?.[1] ?? "waiting",
    arrived: p >= ARRIVED,
    invoice: p >= APPROVED ? "approved" : p >= READY ? "ready" : "reading",
    checks: CHECKS.filter((at) => at <= p).length,
    exported: p >= EXPORTED,
    dock: p < DOCK[0] ? 0 : p < DOCK[1] ? 1 : 2,
  };
}

function frameVars(p: number, width: number, height: number): Record<string, string> {
  if (width <= NARROW_WIDTH) return { "--k": String((width - 24) / BOARD_WIDTH) };
  const grow = seg(p, 0, 0.16);
  const frameWidth = lerp(Math.min(1160, width - 48), width - 28, grow);
  const frameHeight = lerp(Math.min(640, height - FRAME_INSET), height - FRAME_INSET, grow);
  return {
    "--fw": `${frameWidth}px`,
    "--fh": `${frameHeight}px`,
    "--fr": `${lerp(28, 22, grow)}px`,
    "--k": String(Math.min(frameWidth / BOARD_WIDTH, frameHeight / BOARD_HEIGHT)),
  };
}

export function sceneVars(p: number, width: number, height: number): Record<string, string> {
  const travel = seg(p, 0.34, 0.46);
  const toApprove = seg(p, 0.58, 0.645);
  const toExport = seg(p, 0.86, 0.925);
  const exporting = p > 0.76;
  const pressed = (p > 0.645 && p < 0.665) || (p > 0.925 && p < 0.945);
  const moving = {
    "--grow": seg(p, 0, 0.16),
    "--glow": seg(p, 0.02, 0.18),
    "--chrome": seg(p, 0.12, 0.2),
    "--device": seg(p, 0.16, 0.26),
    "--note": seg(p, 0.27, 0.32),
    "--fly": seg(p, 0.33, 0.345) * (1 - seg(p, 0.45, 0.48)),
    "--fly-x": lerp(34, 318, travel),
    "--fly-y": lerp(436, 120, travel) - Math.sin(travel * Math.PI) * 70,
    "--fly-turn": lerp(-4, 2, travel),
    "--fly-size": lerp(1, 0.55, travel),
    "--row": seg(p, 0.46, 0.5),
    "--inbox": seg(p, 0.5, 0.54),
    "--rise": seg(p, 0.5, 0.6),
    "--leave": seg(p, 0.72, 0.8),
    "--mark": seg(p, 0.6, 0.64) * (1 - seg(p, 0.72, 0.76)),
    "--acct": seg(p, 0.7, 0.79),
    "--cursor": seg(p, 0.57, 0.6) * (1 - seg(p, 0.68, 0.71)) + seg(p, 0.83, 0.86) * (1 - seg(p, 0.95, 0.98)),
    "--cursor-x": exporting ? lerp(1190, 1012, toExport) : lerp(812, 1016, toApprove),
    "--cursor-y": exporting ? lerp(600, 345, toExport) : lerp(690, 382, toApprove),
    "--press": pressed ? 0.9 : 1,
  };
  const values = Object.entries(moving).map(([name, value]) => [name, String(value)]);
  return { ...Object.fromEntries(values), ...frameVars(p, width, height) };
}
