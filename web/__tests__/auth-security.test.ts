import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import {
  handleRecoveryRequest,
  RecoveryCaptchaRejectedError,
  RecoveryAttemptLimiter,
  recoveryRedirectTarget,
} from "../lib/recovery-request";

describe("recovery request safety", () => {
  test("production recovery uses one configured origin and rejects another", () => {
    expect(
      recoveryRedirectTarget({
        requestUrl: "https://app.argus.example/api/auth/recovery",
        requestOrigin: "https://app.argus.example",
        configuredAppOrigin: "https://app.argus.example",
        environment: "production",
      }),
    ).toBe("https://app.argus.example/auth/recovery");
    expect(
      recoveryRedirectTarget({
        requestUrl: "https://app.argus.example/api/auth/recovery",
        requestOrigin: "https://attacker.example",
        configuredAppOrigin: "https://app.argus.example",
        environment: "production",
      }),
    ).toBeNull();
    expect(
      recoveryRedirectTarget({
        requestUrl: "http://app.argus.example/api/auth/recovery",
        requestOrigin: "http://app.argus.example",
        configuredAppOrigin: "http://app.argus.example",
        environment: "production",
      }),
    ).toBeNull();
  });

  test("production recovery reports missing origin configuration as unavailable", async () => {
    const response = await handleRecoveryRequest(
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
        },
        body: JSON.stringify({ email: "person@example.com" }),
      }),
      {
        configuredAppOrigin: undefined,
        environment: "production",
        limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
        globalLimiter: new RecoveryAttemptLimiter({
          limit: 100,
          windowMs: 60_000,
        }),
        async sendRecovery() {
          throw new Error("must not send without a configured origin");
        },
      },
    );

    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ accepted: false });
  });

  test("local recovery allows only the documented local origins", () => {
    expect(
      recoveryRedirectTarget({
        requestUrl: "http://localhost:3000/api/auth/recovery",
        requestOrigin: "http://localhost:3000",
        configuredAppOrigin: undefined,
        environment: "development",
      }),
    ).toBe("http://localhost:3000/auth/recovery");
    expect(
      recoveryRedirectTarget({
        requestUrl: "http://evil.local:3000/api/auth/recovery",
        requestOrigin: "http://evil.local:3000",
        configuredAppOrigin: undefined,
        environment: "development",
      }),
    ).toBeNull();
  });

  test("rate limiting applies independently to normalized email and address", () => {
    let now = 1_000;
    const limiter = new RecoveryAttemptLimiter({
      limit: 2,
      windowMs: 1_000,
      now: () => now,
    });

    expect(limiter.retryAfterMs(["email:user@example.com", "ip:127.0.0.1"])).toBe(0);
    expect(limiter.retryAfterMs(["email:user@example.com", "ip:127.0.0.2"])).toBe(0);
    expect(limiter.retryAfterMs(["email:user@example.com", "ip:127.0.0.3"])).toBe(1_000);
    now = 2_001;
    expect(limiter.retryAfterMs(["email:user@example.com", "ip:127.0.0.3"])).toBe(0);
  });

  test("rate limiting bounds active unique-key churn", () => {
    const limiter = new RecoveryAttemptLimiter({
      limit: 5,
      windowMs: 60_000,
      now: () => 1_000,
      maxTrackedKeys: 64,
    });

    for (let index = 0; index < 32; index += 1) {
      expect(
        limiter.retryAfterMs([
          `email:person-${index}@example.com`,
          `ip:192.0.2.${index}`,
        ]),
      ).toBe(0);
    }
    expect(
      limiter.retryAfterMs([
        "email:capacity@example.com",
        "ip:198.51.100.1",
      ]),
    ).toBeGreaterThan(0);

    const attempts = (
      limiter as unknown as { attempts: Map<string, number[]> }
    ).attempts;
    expect(attempts.size).toBe(64);
  });

  test("key churn never evicts an actively blocked recovery victim", () => {
    const limiter = new RecoveryAttemptLimiter({
      limit: 2,
      windowMs: 60_000,
      now: () => 1_000,
      maxTrackedKeys: 4,
    });
    const victimKeys = ["email:victim@example.com", "ip:192.0.2.1"];

    expect(limiter.retryAfterMs(victimKeys)).toBe(0);
    expect(limiter.retryAfterMs(victimKeys)).toBe(0);
    expect(
      limiter.retryAfterMs(["email:filler@example.com", "ip:192.0.2.2"]),
    ).toBe(0);
    expect(
      limiter.retryAfterMs(["email:churn@example.com", "ip:192.0.2.3"]),
    ).toBeGreaterThan(0);
    expect(limiter.retryAfterMs(victimKeys)).toBeGreaterThan(0);
  });

  test("rate limiting globally removes expired one-off keys", () => {
    let now = 1_000;
    const limiter = new RecoveryAttemptLimiter({
      limit: 5,
      windowMs: 1_000,
      now: () => now,
    });

    for (let index = 0; index < 100; index += 1) {
      limiter.retryAfterMs([
        `email:person-${index}@example.com`,
        `ip:198.51.100.${index}`,
      ]);
    }
    now = 2_001;
    limiter.retryAfterMs(["email:current@example.com", "ip:203.0.113.1"]);

    const attempts = (
      limiter as unknown as { attempts: Map<string, number[]> }
    ).attempts;
    expect(attempts.size).toBe(2);
  });

  test("account-dependent provider rejection matches the accepted response", async () => {
    const request = () =>
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
        },
        body: JSON.stringify({
          email: "person@example.com",
          captcha_token: "captcha-proof",
        }),
      });
    const dependencies = (
      sendRecovery: (
        email: string,
        redirectTo: string,
        captchaToken: string,
      ) => Promise<void>,
    ) => ({
      configuredAppOrigin: "https://app.argus.example",
      environment: "production",
      limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
      globalLimiter: new RecoveryAttemptLimiter({
        limit: 100,
        windowMs: 60_000,
      }),
      sendRecovery,
    });

    const accepted = await handleRecoveryRequest(
      request(),
      dependencies(async () => undefined),
    );
    const rejected = await handleRecoveryRequest(
      request(),
      dependencies(async () => {
        throw new Error("account missing");
      }),
    );

    expect(accepted.status).toBe(202);
    expect(await accepted.json()).toEqual({ accepted: true });
    expect(rejected.status).toBe(accepted.status);
    expect(await rejected.json()).toEqual({ accepted: true });
  });

  test("classified CAPTCHA rejection is surfaced without provider detail", async () => {
    const response = await handleRecoveryRequest(
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
        },
        body: JSON.stringify({
          email: "person@example.com",
          captcha_token: "captcha-proof",
        }),
      }),
      {
        configuredAppOrigin: "https://app.argus.example",
        environment: "production",
        limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
        globalLimiter: new RecoveryAttemptLimiter({
          limit: 100,
          windowMs: 60_000,
        }),
        async sendRecovery() {
          throw new RecoveryCaptchaRejectedError();
        },
      },
    );

    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({ accepted: false });
  });

  test("recovery forwards one bounded CAPTCHA token to the provider", async () => {
    let providerToken = "";
    const response = await handleRecoveryRequest(
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
        },
        body: JSON.stringify({
          email: "person@example.com",
          captcha_token: "captcha-proof",
        }),
      }),
      {
        configuredAppOrigin: "https://app.argus.example",
        environment: "production",
        limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
        globalLimiter: new RecoveryAttemptLimiter({
          limit: 100,
          windowMs: 60_000,
        }),
        async sendRecovery(_email, _redirectTo, captchaToken) {
          providerToken = captchaToken;
        },
      },
    );
    const routeSource = readFileSync(
      join(import.meta.dir, "../app/api/auth/recovery/route.ts"),
      "utf-8",
    );

    expect(response.status).toBe(202);
    expect(providerToken).toBe("captcha-proof");
    expect(routeSource).toContain("captchaToken");
    expect(routeSource).toContain("captchaToken,");
  });

  test("recovery rejects missing or invalid CAPTCHA tokens before provider work", async () => {
    const captchaValues: unknown[] = [undefined, null, 42, "", "   ", "x".repeat(4_097)];

    for (const captchaToken of captchaValues) {
      let providerCalls = 0;
      const body: Record<string, unknown> = { email: "person@example.com" };
      if (captchaToken !== undefined) body.captcha_token = captchaToken;
      const response = await handleRecoveryRequest(
        new Request("https://app.argus.example/api/auth/recovery", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Origin: "https://app.argus.example",
          },
          body: JSON.stringify(body),
        }),
        {
          configuredAppOrigin: "https://app.argus.example",
          environment: "production",
          limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
          globalLimiter: new RecoveryAttemptLimiter({
            limit: 100,
            windowMs: 60_000,
          }),
          async sendRecovery() {
            providerCalls += 1;
          },
        },
      );

      expect(response.status).toBe(400);
      expect(providerCalls).toBe(0);
    }
  });

  test("recovery ignores a body-supplied redirect", async () => {
    let destination = "";
    const response = await handleRecoveryRequest(
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
        },
        body: JSON.stringify({
          email: "person@example.com",
          captcha_token: "captcha-proof",
          redirectTo: "https://attacker.example/steal",
        }),
      }),
      {
        configuredAppOrigin: "https://app.argus.example",
        environment: "production",
        limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
        globalLimiter: new RecoveryAttemptLimiter({
          limit: 100,
          windowMs: 60_000,
        }),
        async sendRecovery(_email, redirectTo) {
          destination = redirectTo;
        },
      },
    );

    expect(response.status).toBe(202);
    expect(destination).toBe("https://app.argus.example/auth/recovery");
  });

  test("recovery rejects null and malformed origins before provider work", async () => {
    for (const origin of ["null", "not-an-origin"]) {
      let providerCalls = 0;
      const response = await handleRecoveryRequest(
        new Request("https://app.argus.example/api/auth/recovery", {
          method: "POST",
          headers: { "Content-Type": "application/json", Origin: origin },
          body: JSON.stringify({ email: "person@example.com" }),
        }),
        {
          configuredAppOrigin: "https://app.argus.example",
          environment: "production",
          limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
          globalLimiter: new RecoveryAttemptLimiter({ limit: 100, windowMs: 60_000 }),
          async sendRecovery() {
            providerCalls += 1;
          },
        },
      );

      expect(response.status).toBe(403);
      expect(providerCalls).toBe(0);
    }
  });

  test("recovery rejects non-json and oversized bodies before provider work", async () => {
    const cases: Array<{ request: Request; status: number }> = [
      {
        request: new Request("https://app.argus.example/api/auth/recovery", {
          method: "POST",
          headers: {
            "Content-Type": "text/plain",
            Origin: "https://app.argus.example",
          },
          body: JSON.stringify({ email: "person@example.com" }),
        }),
        status: 415,
      },
      {
        request: new Request("https://app.argus.example/api/auth/recovery", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Origin: "https://app.argus.example",
          },
          body: JSON.stringify({ padding: "x".repeat(9_000) }),
        }),
        status: 413,
      },
    ];
    for (const { request, status } of cases) {
      let providerCalls = 0;
      const response = await handleRecoveryRequest(request, {
        configuredAppOrigin: "https://app.argus.example",
        environment: "production",
        limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
        globalLimiter: new RecoveryAttemptLimiter({ limit: 100, windowMs: 60_000 }),
        async sendRecovery() {
          providerCalls += 1;
        },
      });

      expect(response.status).toBe(status);
      expect(providerCalls).toBe(0);
    }
  });

  test("recovery rejects non-object JSON before provider work", async () => {
    let providerCalls = 0;
    const response = await handleRecoveryRequest(
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
        },
        body: "null",
      }),
      {
        configuredAppOrigin: "https://app.argus.example",
        environment: "production",
        limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
        globalLimiter: new RecoveryAttemptLimiter({ limit: 100, windowMs: 60_000 }),
        async sendRecovery() {
          providerCalls += 1;
        },
      },
    );

    expect(response.status).toBe(400);
    expect(providerCalls).toBe(0);
  });

  test("recovery bounds email and client-address inputs before provider work", async () => {
    const cases: Array<{ request: Request; status: number }> = [
      {
        request: new Request("https://app.argus.example/api/auth/recovery", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Origin: "https://app.argus.example",
          },
          body: JSON.stringify({ email: `${"x".repeat(243)}@example.com` }),
        }),
        status: 202,
      },
      {
        request: new Request("https://app.argus.example/api/auth/recovery", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Origin: "https://app.argus.example",
            "CF-Connecting-IP": "not-an-ip-address",
          },
          body: JSON.stringify({ email: "person@example.com" }),
        }),
        status: 400,
      },
    ];
    for (const { request, status } of cases) {
      let providerCalls = 0;
      const response = await handleRecoveryRequest(request, {
        configuredAppOrigin: "https://app.argus.example",
        environment: "production",
        limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
        globalLimiter: new RecoveryAttemptLimiter({ limit: 100, windowMs: 60_000 }),
        async sendRecovery() {
          providerCalls += 1;
        },
      });

      expect(response.status).toBe(status);
      expect(providerCalls).toBe(0);
    }
  });

  test("recovery global abuse budget fails closed with retry guidance", async () => {
    let providerCalls = 0;
    const globalLimiter = new RecoveryAttemptLimiter({
      limit: 1,
      windowMs: 60_000,
      now: () => 1_000,
    });
    const dependencies = {
      configuredAppOrigin: "https://app.argus.example",
      environment: "production",
      limiter: new RecoveryAttemptLimiter({
        limit: 5,
        windowMs: 60_000,
        now: () => 1_000,
      }),
      globalLimiter,
      async sendRecovery() {
        providerCalls += 1;
      },
    };
    const request = (email: string) =>
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
        },
        body: JSON.stringify({ email, captcha_token: "captcha-proof" }),
      });

    expect((await handleRecoveryRequest(request("one@example.com"), dependencies)).status).toBe(202);
    const blocked = await handleRecoveryRequest(
      request("two@example.com"),
      dependencies,
    );

    expect(blocked.status).toBe(429);
    expect(blocked.headers.get("Retry-After")).toBe("60");
    expect(await blocked.json()).toEqual({ accepted: false });
    expect(providerCalls).toBe(1);
  });

  test("invalid recovery emails do not consume the provider-wide budget", async () => {
    let providerCalls = 0;
    const dependencies = {
      configuredAppOrigin: "https://app.argus.example",
      environment: "production",
      limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
      globalLimiter: new RecoveryAttemptLimiter({ limit: 1, windowMs: 60_000 }),
      async sendRecovery() {
        providerCalls += 1;
      },
    };
    const request = (email: string, address: string) =>
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
          "CF-Connecting-IP": address,
        },
        body: JSON.stringify({
          email,
          ...(email.includes("@") ? { captcha_token: "captcha-proof" } : {}),
        }),
      });

    expect(
      (await handleRecoveryRequest(request("not-an-email", "192.0.2.10"), dependencies))
        .status,
    ).toBe(202);
    expect(
      (await handleRecoveryRequest(request("valid@example.com", "192.0.2.11"), dependencies))
        .status,
    ).toBe(202);
    expect(providerCalls).toBe(1);
  });

  test("locally blocked recovery attempts do not consume the provider-wide budget", async () => {
    let providerCalls = 0;
    const dependencies = {
      configuredAppOrigin: "https://app.argus.example",
      environment: "production",
      limiter: new RecoveryAttemptLimiter({ limit: 1, windowMs: 60_000 }),
      globalLimiter: new RecoveryAttemptLimiter({ limit: 2, windowMs: 60_000 }),
      async sendRecovery() {
        providerCalls += 1;
      },
    };
    const request = (email: string, address: string) =>
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
          "CF-Connecting-IP": address,
        },
        body: JSON.stringify({ email, captcha_token: "captcha-proof" }),
      });

    expect(
      (await handleRecoveryRequest(request("one@example.com", "192.0.2.20"), dependencies))
        .status,
    ).toBe(202);
    expect(
      (await handleRecoveryRequest(request("one@example.com", "192.0.2.20"), dependencies))
        .status,
    ).toBe(429);
    expect(
      (await handleRecoveryRequest(request("two@example.com", "192.0.2.21"), dependencies))
        .status,
    ).toBe(202);
    expect(providerCalls).toBe(2);
  });

  test("account security confirmation labels are localized in English and Spanish", () => {
    const en = JSON.parse(
      readFileSync(join(import.meta.dir, "../public/locales/en/common.json"), "utf-8"),
    );
    const es = JSON.parse(
      readFileSync(join(import.meta.dir, "../public/locales/es-419/common.json"), "utf-8"),
    );

    expect(en.common.confirm).toBe("Confirm");
    expect(es.common.confirm).toBe("Confirmar");
  });
});
