import { describe, expect, test } from "bun:test";

import { landingPreviewAllowed } from "../lib/landing-preview";

describe("landing preview", () => {
  test.each([
    ["cuadrao-marketing-staging.onrender.com", "private"],
    ["127.0.0.1:3461", undefined],
  ])("opens on %s", (host, indexing) => {
    expect(landingPreviewAllowed(host, indexing)).toBe(true);
  });

  test.each([
    ["cuadrao.ai", "private"],
    ["cuadrao.ai", undefined],
    ["CUADRAO.AI:443", undefined],
    ["www.cuadrao.ai", undefined],
    ["cuadrao-marketing-staging.onrender.com", "public"],
    [null, undefined],
  ])("stays closed on %s with indexing %s", (host, indexing) => {
    expect(landingPreviewAllowed(host, indexing)).toBe(false);
  });
});
