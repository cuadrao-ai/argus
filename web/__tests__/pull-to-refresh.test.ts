import { describe, expect, test } from "bun:test";
import { dampPull, PULL_HOLD, PULL_IDLE, PULL_THRESHOLD, pullFrame, pullStep, type PullEvent, type PullPhase } from "@/components/ui/pull-to-refresh";
import { createReloadWaits } from "@/components/business-app/list-reload";

const run = (events: PullEvent[], from: PullPhase = PULL_IDLE) => {
  const kinds: string[] = [];
  let phase = from;
  for (const event of events) {
    phase = pullStep(phase, event);
    kinds.push(phase.kind);
  }
  return { phase, kinds };
};

describe("pull to refresh, the state machine", () => {
  test("a pull past the threshold goes pulling, armed, refreshing, settling, then idle", () => {
    const { kinds } = run([
      { kind: "move", distance: 20 },
      { kind: "move", distance: PULL_THRESHOLD },
      { kind: "release" },
      { kind: "settled", outcome: "updated" },
      { kind: "rested" },
    ]);
    expect(kinds).toEqual(["pulling", "armed", "refreshing", "settling", "idle"]);
  });

  test("the threshold is the damped travel: just short stays pulling, at it arms", () => {
    expect(pullStep(PULL_IDLE, { kind: "move", distance: PULL_THRESHOLD - 0.5 }).kind).toBe("pulling");
    expect(pullStep(PULL_IDLE, { kind: "move", distance: PULL_THRESHOLD }).kind).toBe("armed");
  });

  test("pulling back under the threshold disarms, so that release only springs back", () => {
    const { kinds, phase } = run([{ kind: "move", distance: 80 }, { kind: "move", distance: 30 }, { kind: "release" }]);
    expect(kinds).toEqual(["armed", "pulling", "settling"]);
    expect(phase).toEqual({ kind: "settling", outcome: null });
  });

  test("a gesture the browser took away springs back, armed or not, and never refreshes", () => {
    expect(run([{ kind: "move", distance: 90 }, { kind: "cancel" }]).phase).toEqual({ kind: "settling", outcome: null });
    expect(run([{ kind: "move", distance: 10 }, { kind: "cancel" }]).phase).toEqual({ kind: "settling", outcome: null });
  });

  test("while refreshing, more travel, another release or a cancel change nothing until the reload answers", () => {
    const refreshing: PullPhase = { kind: "refreshing" };
    for (const event of [{ kind: "move", distance: 200 }, { kind: "release" }, { kind: "cancel" }, { kind: "rested" }] as PullEvent[]) {
      expect(pullStep(refreshing, event)).toBe(refreshing);
    }
    expect(pullStep(refreshing, { kind: "settled", outcome: "failed" })).toEqual({ kind: "settling", outcome: "failed" });
  });

  test("an answer that arrives outside a refresh is ignored", () => {
    expect(pullStep(PULL_IDLE, { kind: "settled", outcome: "updated" })).toBe(PULL_IDLE);
    const pulling: PullPhase = { kind: "pulling", distance: 12 };
    expect(pullStep(pulling, { kind: "settled", outcome: "updated" })).toBe(pulling);
  });

  test("a release with no pull under way is not a refresh", () => {
    expect(pullStep(PULL_IDLE, { kind: "release" })).toBe(PULL_IDLE);
  });
});

describe("pull to refresh, the rubber band", () => {
  test("travel follows the finger at first, gives less and less, and the threshold takes more than 64px of finger", () => {
    expect(dampPull(0)).toBe(0);
    expect(dampPull(-40)).toBe(0);
    expect(dampPull(10)).toBeGreaterThan(5);
    expect(dampPull(100)).toBeLessThan(100);
    expect(dampPull(200) - dampPull(150)).toBeLessThan(dampPull(50) - dampPull(0));
    expect(dampPull(64)).toBeLessThan(PULL_THRESHOLD);
    expect(dampPull(170)).toBeGreaterThan(PULL_THRESHOLD);
  });
});

describe("pull to refresh, what it paints", () => {
  test("the content follows the pull and waits at the hold while the reload runs", () => {
    expect(pullFrame({ kind: "pulling", distance: 40 }, false).content).toBe(40);
    const refreshing = pullFrame({ kind: "refreshing" }, false);
    expect(refreshing.content).toBe(PULL_HOLD);
    expect(refreshing.spinning).toBe(true);
    expect(pullFrame(PULL_IDLE, false).content).toBe(0);
  });

  test("the arc turns and fills with progress, full at the threshold", () => {
    const half = pullFrame({ kind: "pulling", distance: PULL_THRESHOLD / 2 }, false);
    const armed = pullFrame({ kind: "armed", distance: PULL_THRESHOLD + 30 }, false);
    expect(half.progress).toBeCloseTo(0.5);
    expect(half.turn).toBeGreaterThan(0);
    expect(armed.progress).toBe(1);
    expect(armed.turn).toBeGreaterThan(half.turn);
  });

  test("with reduced motion nothing travels or turns: the indicator fades in at its place", () => {
    for (const phase of [{ kind: "pulling", distance: 40 }, { kind: "armed", distance: 90 }, { kind: "refreshing" }] as PullPhase[]) {
      const frame = pullFrame(phase, true);
      expect(frame.content).toBe(0);
      expect(frame.turn).toBe(0);
      expect(frame.indicator).toBe(pullFrame(PULL_IDLE, true).indicator);
    }
    expect(pullFrame({ kind: "pulling", distance: 32 }, true).opacity).toBeCloseTo(0.5);
  });
});

describe("a workspace reload waits for every list", () => {
  test("it settles once records, notes and emails have all answered at its revision", async () => {
    const waits = createReloadWaits();
    waits.committed(3);
    let outcome: string | null = null;
    void waits.next().then((value) => { outcome = value; });
    waits.answered("records", 4, true);
    waits.answered("notes", 4, true);
    await Promise.resolve();
    expect(outcome).toBeNull();
    waits.answered("emails", 4, true);
    await Promise.resolve();
    expect(outcome as string | null).toBe("updated");
  });

  test("an answer from a load that started before the reload never settles it", async () => {
    const waits = createReloadWaits();
    waits.committed(3);
    let outcome: string | null = null;
    void waits.next().then((value) => { outcome = value; });
    for (const list of ["records", "notes", "emails"] as const) waits.answered(list, 3, true);
    await Promise.resolve();
    expect(outcome).toBeNull();
  });

  test("one list that failed makes the reload a failure, and a later revision answers for an earlier wait", async () => {
    const waits = createReloadWaits();
    waits.committed(0);
    let outcome: string | null = null;
    void waits.next().then((value) => { outcome = value; });
    waits.answered("records", 2, true);
    waits.answered("notes", 2, false);
    waits.answered("emails", 2, true);
    await Promise.resolve();
    expect(outcome as string | null).toBe("failed");
  });
});
