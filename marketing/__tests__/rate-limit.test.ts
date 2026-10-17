import { describe, expect, test } from "bun:test";
import { WindowLimiter } from "../lib/forms/rate-limit";

describe("window limiter", () => {
  test("allows up to the limit, then reports the seconds until the oldest hit expires", () => {
    let now = 0;
    const limiter = new WindowLimiter(2, 10_000, () => now);
    expect(limiter.check("a")).toBeNull();
    now = 1_000;
    expect(limiter.check("a")).toBeNull();
    now = 2_000;
    expect(limiter.check("a")).toBe(8);
  });

  test("forgets hits once the window has passed", () => {
    let now = 0;
    const limiter = new WindowLimiter(1, 10_000, () => now);
    limiter.check("a");
    now = 10_000;
    expect(limiter.check("a")).toBeNull();
  });

  test("keeps keys independent", () => {
    const limiter = new WindowLimiter(1, 10_000, () => 0);
    limiter.check("a");
    expect(limiter.check("b")).toBeNull();
    expect(limiter.check("a")).not.toBeNull();
  });

  test("a refused attempt does not extend the wait", () => {
    let now = 0;
    const limiter = new WindowLimiter(1, 10_000, () => now);
    limiter.check("a");
    now = 5_000;
    expect(limiter.check("a")).toBe(5);
    now = 9_000;
    expect(limiter.check("a")).toBe(1);
  });

  test("a timer drops a key's stored value after its window, with no further submission", async () => {
    const limiter = new WindowLimiter(5, 20);
    limiter.check("visitor@example.invalid");
    expect(limiter.tracked).toBe(1);
    await new Promise((resolve) => setTimeout(resolve, 120));
    expect(limiter.tracked).toBe(0);
  });
});
