import { describe, expect, test } from "bun:test";

import { beatAt, beatPoint, sceneVars, scrollProgress } from "../lib/scene-timeline";

const DESKTOP = { width: 1440, height: 900 };

describe("scene beats", () => {
  test("the page renders again at every text change and at no other point", () => {
    for (let step = 0; step <= 2000; step += 1) {
      const p = step / 2000;
      expect(beatAt(beatPoint(p))).toEqual(beatAt(p));
    }
  });

  test.each([
    [0, { island: "waiting", arrived: false, dock: 0 }],
    [0.3, { island: "incoming", arrived: false, dock: 0 }],
    [0.42, { island: "reading", arrived: false, dock: 1 }],
    [0.5, { island: "reading", arrived: true, invoice: "reading" }],
    [0.6, { island: "ready", invoice: "ready" }],
    [0.7, { island: "approved", invoice: "approved", checks: 0 }],
    [0.8, { island: "accountant", checks: 2, dock: 2 }],
    [0.9, { checks: 4, exported: false }],
    [1, { island: "accountant", checks: 4, exported: true, dock: 2 }],
  ])("at %d the scene tells the right part of the story", (p, expected) => {
    expect(beatAt(p)).toMatchObject(expected);
  });
});

describe("scroll progress", () => {
  test("runs from the top of the scene to the end of its travel", () => {
    expect(scrollProgress(0, 4000, 1000)).toBe(0);
    expect(scrollProgress(-1500, 4000, 1000)).toBe(0.5);
    expect(scrollProgress(-3000, 4000, 1000)).toBe(1);
  });

  test("stays inside the scene while the page scrolls past it", () => {
    expect(scrollProgress(200, 4000, 1000)).toBe(0);
    expect(scrollProgress(-9000, 4000, 1000)).toBe(1);
  });

  test("shows the finished scene when there is nothing to scroll", () => {
    expect(scrollProgress(0, 800, 900)).toBe(1);
  });
});

describe("scene frame", () => {
  test("grows from the page width to almost the full screen", () => {
    expect(sceneVars(0, DESKTOP.width, DESKTOP.height)["--fw"]).toBe("1160px");
    expect(sceneVars(1, DESKTOP.width, DESKTOP.height)["--fw"]).toBe("1412px");
  });

  test.each([
    [1440, 900],
    [1280, 640],
    [2560, 1080],
  ])("the board fits inside the frame at %dx%d", (width, height) => {
    for (const p of [0, 0.5, 1]) {
      const vars = sceneVars(p, width, height);
      expect(Number(vars["--k"]) * 760).toBeLessThanOrEqual(parseFloat(vars["--fh"]) + 0.001);
      expect(Number(vars["--k"]) * 1290).toBeLessThanOrEqual(parseFloat(vars["--fw"]) + 0.001);
    }
  });

  test("a phone sets only the board scale and leaves the frame to CSS", () => {
    const vars = sceneVars(1, 390, 844);
    expect(Number(vars["--k"])).toBeCloseTo(366 / 1290);
    expect(vars["--fw"]).toBeUndefined();
  });
});
