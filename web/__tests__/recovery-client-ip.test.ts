import { test } from "bun:test";
import assert from "node:assert/strict";
import { handleRecoveryRequest, RecoveryAttemptLimiter } from "../lib/recovery-request";

const attemptLimit = 5;
const globalLimit = 100;
const windowMs = 600_000;
const origin = "https://example.test";

function fixture(trustedClientIpHeader?: string) {
  let sends = 0;
  const dependencies = {
    configuredAppOrigin: origin, environment: "production", trustedClientIpHeader,
    limiter: new RecoveryAttemptLimiter({ limit: attemptLimit, windowMs }),
    globalLimiter: new RecoveryAttemptLimiter({ limit: globalLimit, windowMs }),
    async sendRecovery() { sends += 1; },
  };
  return {
    get sends() { return sends; },
    async request(index: number, headers: Record<string, string>, email = `synthetic${index}@example.test`) {
      return handleRecoveryRequest(new Request(`${origin}/api/auth/recovery`, {
        method: "POST", headers: { "Content-Type": "application/json", Origin: origin, ...headers },
        body: JSON.stringify({ email, captcha_token: "synthetic-captcha" }),
      }), dependencies);
    },
  };
}

for (const setting of [undefined, "", "   ", " X-Verified-Client-IP "]) {
  test(`trusted address survives rotated forwarding headers: ${JSON.stringify(setting)}`, async () => {
    const f = fixture(setting);
    for (let i = 0; i <= attemptLimit; i += 1) {
      const response = await f.request(i, {
        "CF-Connecting-IP": `192.0.2.${i + 1}`,
        "X-Forwarded-For": `198.51.100.${i + 1}, 192.0.2.1`,
        "X-Real-IP": `198.51.100.${i + 1}`,
        [setting?.trim() || "CF-Connecting-IP"]: "203.0.113.55",
      });
      assert.equal(response.status, i < attemptLimit ? 202 : 429);
      if (i === attemptLimit) assert.ok(Number(response.headers.get("Retry-After")) > 0);
    }
    assert.equal(f.sends, attemptLimit);
  });
}

for (const setting of [undefined, "X-Verified-Client-IP"]) {
  test(`missing selected header shares the unknown bucket: ${setting}`, async () => {
    const f = fixture(setting);
    for (let i = 0; i <= attemptLimit; i += 1) {
      const response = await f.request(i, {
        "X-Forwarded-For": `198.51.100.${i + 1}`, "X-Real-IP": `192.0.2.${i + 1}`,
        ...(setting ? { "CF-Connecting-IP": `203.0.113.${i + 1}` } : {}),
      });
      assert.equal(response.status, i < attemptLimit ? 202 : 429);
    }
    assert.equal(f.sends, attemptLimit);
  });
}

for (const address of ["not-an-ip", "1".repeat(46), "203.0.113.55, 198.51.100.1"]) {
  test(`invalid trusted address rejects before sending: ${address}`, async () => {
    const f = fixture();
    const response = await f.request(0, { "CF-Connecting-IP": address, "X-Forwarded-For": "192.0.2.1" });
    assert.equal(response.status, 400);
    assert.equal(f.sends, 0);
  });
}

test("same email remains bounded across trusted addresses", async () => {
  const f = fixture();
  for (let i = 0; i <= attemptLimit; i += 1) {
    const response = await f.request(i, { "CF-Connecting-IP": `203.0.113.${i + 1}` }, "same@example.test");
    assert.equal(response.status, i < attemptLimit ? 202 : 429);
  }
  assert.equal(f.sends, attemptLimit);
});

test("global budget bounds distinct trusted addresses and emails", async () => {
  const f = fixture();
  for (let i = 0; i <= globalLimit; i += 1) {
    const response = await f.request(i, { "CF-Connecting-IP": `203.0.113.${i + 1}` });
    assert.equal(response.status, i < globalLimit ? 202 : 429);
  }
  assert.equal(f.sends, globalLimit);
});

for (const trusted of [undefined, "   ", "203.0.113.55"]) {
  test(`malformed untrusted headers cannot reject recovery: ${trusted}`, async () => {
    const f = fixture();
    const response = await f.request(0, {
      "X-Forwarded-For": "not-an-ip",
      "X-Real-IP": "also-not-an-ip",
      ...(trusted === undefined ? {} : { "CF-Connecting-IP": trusted }),
    });
    assert.equal(response.status, 202);
    assert.equal(f.sends, 1);
  });
}
