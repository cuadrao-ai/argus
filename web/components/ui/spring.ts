/**
 * A damped spring for a control's moving parts (a segmented thumb, a switch
 * knob). It runs on animation frames, so a change mid-flight keeps the
 * current velocity instead of restarting. Stiffness and damping are per unit
 * mass; settled means within half a pixel and nearly still.
 */
export type SpringTuning = { stiffness: number; damping: number };

/** The edge that leads a move: quick, with a small overshoot. */
export const LEAD: SpringTuning = { stiffness: 700, damping: 34 };
/** The edge that follows: softer, so the shape stretches on the way and settles back. */
export const TRAIL: SpringTuning = { stiffness: 380, damping: 30 };

export type SpringState = { x: number; v: number };

export function stepSpring(state: SpringState, target: number, tuning: SpringTuning, dt: number): SpringState {
  // Semi-implicit Euler in small slices stays stable at 120Hz and on a dropped frame.
  let { x, v } = state;
  const slices = Math.max(1, Math.ceil(dt / (1 / 240)));
  const h = dt / slices;
  for (let i = 0; i < slices; i += 1) {
    v += (-tuning.stiffness * (x - target) - tuning.damping * v) * h;
    x += v * h;
  }
  return { x, v };
}

export function springSettled(state: SpringState, target: number): boolean {
  return Math.abs(state.x - target) < 0.5 && Math.abs(state.v) < 5;
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Drives named values toward targets, one frame at a time, and hands each
 * frame to `paint`. `set` moves a target; `jump` places a value with no motion.
 */
export function createSpringDriver<K extends string>(initial: Record<K, number>, tuningFor: (key: K, from: number, to: number) => SpringTuning, paint: (values: Record<K, number>) => void) {
  const keys = Object.keys(initial) as K[];
  const state = Object.fromEntries(keys.map((key) => [key, { x: initial[key], v: 0 }])) as Record<K, SpringState>;
  const target = { ...initial };
  const tuning = Object.fromEntries(keys.map((key) => [key, LEAD])) as Record<K, SpringTuning>;
  let frame: number | null = null;
  let last = 0;
  const values = () => Object.fromEntries(keys.map((key) => [key, state[key].x])) as Record<K, number>;
  const tick = (now: number) => {
    const dt = Math.min(0.05, last ? (now - last) / 1000 : 1 / 60);
    last = now;
    let moving = false;
    for (const key of keys) {
      state[key] = stepSpring(state[key], target[key], tuning[key], dt);
      if (springSettled(state[key], target[key])) state[key] = { x: target[key], v: 0 };
      else moving = true;
    }
    paint(values());
    frame = moving ? requestAnimationFrame(tick) : null;
    if (!moving) last = 0;
  };
  return {
    set(next: Partial<Record<K, number>>) {
      for (const key of keys) {
        const to = next[key];
        if (to === undefined || to === target[key]) continue;
        tuning[key] = tuningFor(key, state[key].x, to);
        target[key] = to;
      }
      if (prefersReducedMotion() || typeof requestAnimationFrame === "undefined") {
        this.jump(target);
        return;
      }
      if (frame === null) frame = requestAnimationFrame(tick);
    },
    jump(next: Partial<Record<K, number>>) {
      for (const key of keys) {
        const to = next[key];
        if (to === undefined) continue;
        target[key] = to;
        state[key] = { x: to, v: 0 };
      }
      if (frame !== null && typeof cancelAnimationFrame !== "undefined") cancelAnimationFrame(frame);
      frame = null;
      last = 0;
      paint(values());
    },
    stop() {
      if (frame !== null && typeof cancelAnimationFrame !== "undefined") cancelAnimationFrame(frame);
      frame = null;
    },
  };
}
