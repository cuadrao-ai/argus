import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { NextRequest } from "next/server";

import { proxy } from "../proxy";

describe("auth link proxy", () => {
  test("redirects an expired recovery query before the recovery page", () => {
    const response = proxy(
      new NextRequest(
        "https://app.example.test/auth/recovery?error=access_denied&error_code=otp_expired",
      ),
    );
    expect(response.status).toBe(307);
    const location = new URL(response.headers.get("location") ?? "");
    expect(location.pathname).toBe("/auth/link-error");
    expect(location.searchParams.get("error")).toBe("access_denied");
    expect(location.searchParams.get("error_code")).toBe("otp_expired");
    expect(location.searchParams.get("type")).toBe("recovery");
  });

  test("leaves a recovery code on the recovery page", () => {
    const response = proxy(new NextRequest("https://app.example.test/auth/recovery?code=abc"));
    expect(response.headers.get("location")).toBeNull();
  });

  test("matches auth routes", () => {
    const source = readFileSync(join(import.meta.dir, "../proxy.ts"), "utf-8");
    expect(source).toContain("authLinkErrorRedirect");
    expect(source).toContain("decideBusinessOnlyWeb");
  });
});
