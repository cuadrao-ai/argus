import { describe, expect, test } from "bun:test";

import { CHAT_DONE, STEP_JUMPS, activeStep, cardsVars, chatAt, chatStage } from "../lib/landing-timeline";

const FRAME = { width: 1440, height: 900 };

describe("steps", () => {
  test.each([
    [0, 0],
    [0.41, 0],
    [0.42, 1],
    [0.62, 2],
    [0.82, 3],
    [1, 3],
  ])("at %d of the track step %d is active", (share, step) => {
    expect(activeStep(share)).toBe(step);
  });

  test("every jump lands on its own step", () => {
    expect(STEP_JUMPS.map(activeStep)).toEqual([0, 1, 2, 3]);
  });
});

describe("chat", () => {
  test("starts empty", () => {
    expect(chatAt(chatStage(0))).toEqual({
      photo: false,
      delivered: false,
      read: false,
      typing: false,
      reply: false,
    });
  });

  test("plays photo, delivered, read, typing, then the reply", () => {
    const seen = [0.1, 0.25, 0.32, 0.5, 0.9].map((q) => chatAt(chatStage(q)));
    expect(seen.map((state) => state.photo)).toEqual([true, true, true, true, true]);
    expect(seen.map((state) => state.delivered)).toEqual([false, true, true, true, true]);
    expect(seen.map((state) => state.read)).toEqual([false, false, true, true, true]);
    expect(seen.map((state) => state.typing)).toEqual([false, false, false, true, false]);
    expect(seen.map((state) => state.reply)).toEqual([false, false, false, false, true]);
  });

  test("the finished chat is what a still page shows", () => {
    expect(chatStage(1)).toBe(CHAT_DONE);
  });
});

describe("cards", () => {
  const vars = (progress: number) => cardsVars(progress, FRAME.width, FRAME.height);

  test("start scattered with the first title", () => {
    expect(vars(0)).toMatchObject({ "--p": "0", "--title-out": "0", "--title-in": "0" });
  });

  test("the two titles never show at once", () => {
    for (let step = 0; step <= 500; step += 1) {
      const state = vars(step / 500);
      expect(Number(state["--title-out"]) < 1 && Number(state["--title-in"]) > 0).toBe(false);
    }
  });

  test("end lined up with the second title", () => {
    expect(vars(1)).toMatchObject({ "--p": "1", "--title-out": "1", "--title-in": "1" });
  });

  test("the scatter tightens on narrow and short screens", () => {
    expect(Number(cardsVars(0, 960, 600)["--spread"])).toBe(0.5);
    expect(Number(cardsVars(0, 960, 600)["--spread-y"])).toBe(0.375);
  });
});
