import { afterEach, describe, expect, mock, test } from "bun:test";

const sent: string[] = [];
mock.module("../lib/supabase-server", () => ({
  createClient: async () => ({
    auth: {
      resetPasswordForEmail: async (_email: string, options: { redirectTo: string }) => {
        sent.push(options.redirectTo);
        return { error: null };
      },
    },
  }),
}));
mock.module("next/headers", () => ({ headers: async () => new Headers() }));
mock.module("../lib/private-alpha-flags", () => ({ evidenceReceiptSharingEnabled: true }));
mock.module("../lib/public-receipt-contract", () => ({
  readPublicReceipt: async () => ({ kind: "revoked" }),
}));

const { POST } = await import("../app/api/auth/recovery/route");
const { generateMetadata } = await import("../app/r/[receiptId]/page");
const { authEmailHookConfig } = await import("../server/emails/auth-hook");
const original = {
  CUADRAO_APP_ORIGIN: process.env.CUADRAO_APP_ORIGIN,
  ARGUS_APP_ORIGIN: process.env.ARGUS_APP_ORIGIN,
  ARGUS_TRUSTED_CLIENT_IP_HEADER: process.env.ARGUS_TRUSTED_CLIENT_IP_HEADER,
  NODE_ENV: process.env.NODE_ENV,
};
afterEach(() => {
  for (const [key, value] of Object.entries(original)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
  sent.length = 0;
});

describe("server app origin at each read site", () => {
  for (const preferred of ["https://app.example.test", undefined]) {
    const legacy = "https://legacy.example.test";
    const expected = preferred ?? legacy;

    test(`uses ${preferred ? "the preferred name when both are set" : "the legacy fallback"}`, async () => {
      if (preferred === undefined) delete process.env.CUADRAO_APP_ORIGIN;
      else process.env.CUADRAO_APP_ORIGIN = preferred;
      process.env.ARGUS_APP_ORIGIN = legacy;
      process.env.ARGUS_TRUSTED_CLIENT_IP_HEADER = "x-test-client-ip";

      const response = await POST(new Request(`${expected}/api/auth/recovery`, {
        method: "POST",
        headers: { "content-type": "application/json", origin: expected, "x-test-client-ip": "192.0.2.1" },
        body: JSON.stringify({ email: "owner@example.test", captcha_token: "synthetic-token" }),
      }));
      expect(response.status).toBe(202);
      expect(sent).toEqual([`${expected}/auth/recovery`]);
      const metadata = await generateMetadata({ params: Promise.resolve({ receiptId: "receipt-test" }) });
      expect(metadata.metadataBase?.origin).toBe(expected);
      expect(authEmailHookConfig(process.env).appOrigin).toBe(expected);
    });
  }

  test("an explicitly empty preferred name does not revive the legacy origin", async () => {
    Object.assign(process.env, { NODE_ENV: "production" });
    process.env.CUADRAO_APP_ORIGIN = "";
    process.env.ARGUS_APP_ORIGIN = "https://legacy.example.test";
    const metadata = await generateMetadata({ params: Promise.resolve({ receiptId: "receipt-test" }) });
    expect(metadata.metadataBase).toBeUndefined();
    expect(authEmailHookConfig(process.env).appOrigin).toBe("");
    const response = await POST(new Request("https://legacy.example.test/api/auth/recovery", {
      method: "POST",
      headers: { "content-type": "application/json", origin: "https://legacy.example.test" },
      body: JSON.stringify({ email: "owner@example.test", captcha_token: "synthetic-token" }),
    }));
    expect(response.status).toBe(503);
    expect(sent).toEqual([]);
  });
});
