import { describe, expect, test } from "bun:test";

import { resolveSignedInHome } from "../lib/landing-intent";

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
});
