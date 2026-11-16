import { describe, expect, test } from "bun:test";
import { postAuthPath, resolveSignedInHome, signedInHomePath } from "../lib/landing-intent";

describe("signed-in home without a pilot switch", () => {
  test("opens Business without a switch or routing inputs", () => {
    expect(resolveSignedInHome()).toEqual({ href: "/biz" });
    expect(signedInHomePath()).toBe("/biz");
  });

  test("sign-in keeps an allowed Business return path", () => {
    const previous = globalThis.window;
    try {
      globalThis.window = { location: { search: "?auth=login&return_to=%2Fbiz%3Freceipt%3Dr1" } } as Window & typeof globalThis;
      expect(postAuthPath()).toBe("/biz?receipt=r1");
      globalThis.window.location.search = "?auth=login&return_to=https%3A%2F%2Finvalid.example";
      expect(postAuthPath()).toBe("/biz");
    } finally {
      if (previous) globalThis.window = previous;
      else delete (globalThis as { window?: unknown }).window;
    }
  });
});
