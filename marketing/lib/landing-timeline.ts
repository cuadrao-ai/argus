import { clamp, smooth } from "./scene-timeline";

// Where each step of "Cómo funciona" sits along the scroll track.
const STEP_ENDS = [0.42, 0.62, 0.82];
export const STEP_JUMPS = [0.02, 0.44, 0.64, 0.84];

// The chat plays while the first step is on screen.
export const CHAT_SHARE = STEP_ENDS[0];

const CHAT_STAGES = [0.06, 0.2, 0.3, 0.36, 0.62];

export type ChatState = {
  photo: boolean;
  delivered: boolean;
  read: boolean;
  typing: boolean;
  reply: boolean;
};

export const CHAT_DONE = CHAT_STAGES.length;

export function activeStep(share: number): number {
  const next = STEP_ENDS.findIndex((end) => share < end);
  return next === -1 ? STEP_ENDS.length : next;
}

export function chatStage(q: number): number {
  return CHAT_STAGES.filter((at) => q > at).length;
}

export function chatAt(stage: number): ChatState {
  return {
    photo: stage >= 1,
    delivered: stage >= 2,
    read: stage >= 3,
    typing: stage === 4,
    reply: stage >= 5,
  };
}

export function cardsVars(progress: number, width: number, height: number): Record<string, string> {
  const eased = smooth(clamp((progress - 0.1) / 0.62));
  const swap = clamp(1 - (1 - eased) * 5);
  return {
    "--p": String(eased),
    "--spread": String(Math.min(1, (width - 600) / 720)),
    "--spread-y": String(Math.min(1, (height - 420) / 480)),
    "--title-out": String(clamp(swap * 2)),
    "--title-in": String(clamp(swap * 2 - 1)),
  };
}
