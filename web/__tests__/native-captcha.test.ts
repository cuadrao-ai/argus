import { describe, expect, test } from "bun:test";

import { beginNativeCaptcha, type NativeCaptchaMessage } from "../lib/native-captcha";

describe("native CAPTCHA delivery", () => {
  test("returns the acquired token only through the native handler", async () => {
    const messages: NativeCaptchaMessage[] = [];
    const token = crypto.randomUUID();
    beginNativeCaptcha((message) => messages.push(message), async () => token);
    await Promise.resolve();
    expect(messages).toEqual([{ type: "token", token }]);
  });

  test("reports acquisition failure without passing error details", async () => {
    const messages: NativeCaptchaMessage[] = [];
    beginNativeCaptcha((message) => messages.push(message), async () => {
      throw new Error("private provider details");
    });
    await Promise.resolve();
    expect(messages).toEqual([{ type: "error" }]);
  });

  test.each(["resolve", "reject"] as const)("cancellation suppresses a late %s", async (outcome) => {
    const messages: NativeCaptchaMessage[] = [];
    let signal: AbortSignal | undefined;
    let resolve!: (token: string) => void;
    let reject!: (error: Error) => void;
    const cancel = beginNativeCaptcha((message) => messages.push(message), (receivedSignal) => {
      signal = receivedSignal;
      return new Promise<string>((accept, fail) => { resolve = accept; reject = fail; });
    });
    cancel();
    if (outcome === "resolve") resolve(crypto.randomUUID());
    else reject(new Error("cancelled"));
    await Promise.resolve();
    expect(signal?.aborted).toBe(true);
    expect(messages).toEqual([]);
  });
});
