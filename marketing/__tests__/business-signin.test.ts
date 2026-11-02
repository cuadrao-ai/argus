import { describe, expect, test } from "bun:test";
import { businessSignInHref } from "../lib/business-signin";

describe("Business staging sign-in destination", () => {
  test("only the exact staging hostname receives the approved destination", () => {
    expect(businessSignInHref("cuadrao-marketing-staging.onrender.com"))
      .toBe("https://cuadrao-web-staging.onrender.com/?auth=login");
  });

  test.each([
    "cuadrao.ai",
    "www.cuadrao.ai",
    "cuadrao-marketing.onrender.com",
    "cuadrao-marketing-staging.onrender.com.example.test",
    "preview-cuadrao-marketing-staging.onrender.com",
    "cuadrao-marketing-staging.onrender.com@evil.example.test",
    "localhost",
    "127.0.0.1",
    "",
  ])("does not expose a staging destination on %s", (hostname) => {
    expect(businessSignInHref(hostname)).toBeNull();
  });
});
