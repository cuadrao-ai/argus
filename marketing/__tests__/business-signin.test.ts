import { describe, expect, test } from "bun:test";
import { businessSignInHref } from "../lib/business-signin";

describe("Business sign-in destination", () => {
  test.each([
    ["cuadrao.ai", "https://cuadrao-app-y7m5.onrender.com/?auth=login"],
    ["www.cuadrao.ai", "https://cuadrao-app-y7m5.onrender.com/?auth=login"],
    ["cuadrao-marketing-staging.onrender.com", "https://cuadrao-web-staging.onrender.com/?auth=login"],
  ])("%s signs in to its own app", (hostname, href) => {
    expect(businessSignInHref(hostname)).toBe(href);
  });

  test.each([
    "cuadrao-marketing.onrender.com",
    "cuadrao-marketing-staging.onrender.com.example.test",
    "preview-cuadrao-marketing-staging.onrender.com",
    "cuadrao-marketing-staging.onrender.com@evil.example.test",
    "cuadrao.ai.example.test",
    "localhost",
    "127.0.0.1",
    "",
    "__proto__",
  ])("shows no sign-in on %s", (hostname) => {
    expect(businessSignInHref(hostname)).toBeNull();
  });
});
