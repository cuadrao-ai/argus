import { describe, expect, test } from "bun:test";

import {
  businessShellEntry,
  postAuthPath,
  resolveSignedInHome,
  signedInHomeClosed,
  signedInHomePath,
} from "../lib/landing-intent";

const chatPath = "/chat?utm_campaign=x";

describe("signed-in home", () => {
  test("keeps chat when both switches are off", () => {
    expect(
      resolveSignedInHome({ pilot: false, businessOnly: false, chatPath }),
    ).toEqual({ href: chatPath });
  });

  test("opens the business workspace when the pilot is on and business-only is off", () => {
    expect(
      resolveSignedInHome({ pilot: true, businessOnly: false, chatPath }),
    ).toEqual({ href: "/biz" });
  });

  test("opens the business workspace when both switches are on", () => {
    expect(
      resolveSignedInHome({ pilot: true, businessOnly: true, chatPath }),
    ).toEqual({ href: "/biz" });
  });

  test("stays closed when business-only is on and the pilot is off", () => {
    expect(
      resolveSignedInHome({
        pilot: false,
        businessOnly: true,
        chatPath: "/chat",
      }),
    ).toEqual({ closed: true });
  });

  test("a closed sign-in stays on the sign-in screen and ignores a business return", () => {
    (globalThis as { window?: { location: { search: string } } }).window = {
      location: { search: "?return_to=%2Fbiz%3Freceipt%3Dr1&auth=login" },
    };
    expect(postAuthPath(false, true)).toBe("/?auth=login");
    expect(signedInHomePath(false, true)).toBe("/?auth=login");
    expect(signedInHomeClosed(false, true)).toBe(true);
    expect(signedInHomeClosed(true, true)).toBe(false);
    expect(signedInHomeClosed(false, false)).toBe(false);
    delete (globalThis as { window?: unknown }).window;
  });

  test("four flag combinations never name chat when business-only is on", () => {
    const chatPath = "/chat";
    const cases = [
      { pilot: false, businessOnly: false, expected: { href: chatPath } },
      { pilot: true, businessOnly: false, expected: { href: "/biz" } },
      { pilot: true, businessOnly: true, expected: { href: "/biz" } },
      { pilot: false, businessOnly: true, expected: { closed: true } },
    ] as const;
    for (const row of cases) {
      const target = resolveSignedInHome({
        pilot: row.pilot,
        businessOnly: row.businessOnly,
        chatPath,
      });
      expect(target).toEqual(row.expected);
      if (row.businessOnly) {
        const href = "href" in target ? target.href : "/?auth=login";
        expect(href.startsWith("/chat")).toBe(false);
      }
    }
    expect(businessShellEntry({ pilot: false, businessOnly: true })).toEqual({ closed: true });
    expect(businessShellEntry({ pilot: true, businessOnly: true })).toEqual({ href: "/biz" });
    expect(businessShellEntry({ pilot: true, businessOnly: false })).toEqual({ href: "/biz" });
    expect(businessShellEntry({ pilot: false, businessOnly: false })).toEqual({ missing: true });
  });
});
