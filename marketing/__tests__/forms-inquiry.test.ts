import { describe, expect, test } from "bun:test";
import { handleInquiry } from "../lib/forms/inquiry";
import {
  CONFIG,
  SUBMISSION_ID,
  captureLogs,
  counters,
  inquiryBody,
  jsonRequest,
  recordingFetch,
} from "./forms-support";

const accepted = () => Response.json({ id: "email-id" });

function deps(respond = accepted, config = CONFIG) {
  const provider = recordingFetch(respond);
  return { provider, deps: { config, fetch: provider.fetch, ...counters() } };
}

describe("inquiry delivery", () => {
  test("accepts after the provider accepts and sends one message to the configured mailbox", async () => {
    const { provider, deps: d } = deps();
    const response = await handleInquiry(jsonRequest("/api/inquiries", inquiryBody()), d);
    expect(response.status).toBe(202);
    expect(await response.json()).toEqual({ status: "accepted" });
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(provider.calls).toHaveLength(1);
    const [call] = provider.calls;
    expect(call.url).toBe("https://resend.test/emails");
    const headers = call.init.headers as Record<string, string>;
    expect(headers["Idempotency-Key"]).toBe(`inquiry-${SUBMISSION_ID}`);
    expect(headers.Authorization).toBe("Bearer re_test_key");
    const sent = JSON.parse(String(call.init.body));
    expect(sent.to).toEqual(["inbox@example.test"]);
    expect(sent.from).toBe("Cuadrao <website@notify.example.test>");
    expect(sent.reply_to).toBe("marisol@example.invalid");
    expect(sent.text).toContain("Nombre: Marisol Peña");
    expect(sent.text).toContain("Llevo las cuentas de una ferretería.");
  });

  test("a retry of the same submission carries the same idempotency key", async () => {
    const { provider, deps: d } = deps();
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const response = await handleInquiry(jsonRequest("/api/inquiries", inquiryBody()), d);
      expect(response.status).toBe(202);
    }
    const keys = provider.calls.map(
      (call) => (call.init.headers as Record<string, string>)["Idempotency-Key"],
    );
    expect(new Set(keys).size).toBe(1);
  });

  test("a provider rejection is reported as unavailable, never as accepted", async () => {
    const { deps: d } = deps(() => new Response("nope", { status: 403 }));
    const response = await handleInquiry(jsonRequest("/api/inquiries", inquiryBody()), d);
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ error: "unavailable" });
  });

  test("a provider timeout is reported as unavailable", async () => {
    const { deps: d } = deps(() => {
      throw new DOMException("timed out", "TimeoutError");
    });
    const response = await handleInquiry(jsonRequest("/api/inquiries", inquiryBody()), d);
    expect(response.status).toBe(503);
  });

  test.each([null])("with no recipient configured the form is unavailable and sends nothing", async (inquiryTo) => {
    const { provider, deps: d } = deps(accepted, { ...CONFIG, inquiryTo });
    const response = await handleInquiry(jsonRequest("/api/inquiries", inquiryBody()), d);
    expect(response.status).toBe(503);
    expect(provider.calls).toHaveLength(0);
  });

  test("missing provider configuration is unavailable and calls nothing", async () => {
    const { provider, deps: d } = deps(accepted, { ...CONFIG, resendApiKey: null });
    const response = await handleInquiry(jsonRequest("/api/inquiries", inquiryBody()), d);
    expect(response.status).toBe(503);
    expect(provider.calls).toHaveLength(0);
  });
});

describe("inquiry input handling", () => {
  test("invalid fields return 400 with field names only and call nothing", async () => {
    const { provider, deps: d } = deps();
    const response = await handleInquiry(
      jsonRequest("/api/inquiries", inquiryBody({ email: "nope" })),
      d,
    );
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "invalid", fields: ["email"] });
    expect(provider.calls).toHaveLength(0);
  });

  test("a filled honeypot looks accepted but sends nothing", async () => {
    const { provider, deps: d } = deps();
    const response = await handleInquiry(
      jsonRequest("/api/inquiries", inquiryBody({ website: "https://spam.invalid" })),
      d,
    );
    expect(response.status).toBe(202);
    expect(provider.calls).toHaveLength(0);
  });

  test("rejects a body that is not JSON", async () => {
    const { deps: d } = deps();
    const response = await handleInquiry(
      jsonRequest("/api/inquiries", "x", { "Content-Type": "text/plain" }),
      d,
    );
    expect(response.status).toBe(415);
  });

  test("rejects malformed JSON", async () => {
    const { deps: d } = deps();
    const response = await handleInquiry(jsonRequest("/api/inquiries", "{oops"), d);
    expect(response.status).toBe(400);
  });

  test("rejects an oversized body without reading it all", async () => {
    const { provider, deps: d } = deps();
    const response = await handleInquiry(
      jsonRequest("/api/inquiries", inquiryBody({ description: "x".repeat(20_000) })),
      d,
    );
    expect(response.status).toBe(413);
    expect(provider.calls).toHaveLength(0);
  });

  test("rejects a request from another origin", async () => {
    const { provider, deps: d } = deps();
    const response = await handleInquiry(
      jsonRequest("/api/inquiries", inquiryBody(), { origin: "https://evil.example.invalid" }),
      d,
    );
    expect(response.status).toBe(403);
    expect(provider.calls).toHaveLength(0);
  });

  test("accepts the page's own origin", async () => {
    const { deps: d } = deps();
    const response = await handleInquiry(
      jsonRequest("/api/inquiries", inquiryBody(), { origin: "https://cuadrao.test" }),
      d,
    );
    expect(response.status).toBe(202);
  });
});

describe("inquiry limits", () => {
  test("a client is limited after five attempts and told when to retry", async () => {
    const { deps: d } = deps();
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const ok = await handleInquiry(
        jsonRequest("/api/inquiries", inquiryBody({ email: `person${attempt}@example.invalid` })),
        d,
      );
      expect(ok.status).toBe(202);
    }
    const limited = await handleInquiry(jsonRequest("/api/inquiries", inquiryBody()), d);
    expect(limited.status).toBe(429);
    expect(Number(limited.headers.get("Retry-After"))).toBeGreaterThan(0);
  });

  test("one address is limited to three messages an hour across clients", async () => {
    const { deps: d } = deps();
    const statuses: number[] = [];
    for (let attempt = 0; attempt < 4; attempt += 1) {
      const response = await handleInquiry(
        jsonRequest("/api/inquiries", inquiryBody({ submissionId: crypto.randomUUID() }), {
          "x-forwarded-for": `198.51.100.${attempt}`,
        }),
        d,
      );
      statuses.push(response.status);
    }
    expect(statuses).toEqual([202, 202, 202, 429]);
  });
});

describe("inquiry client identity", () => {
  test("a spoofed leftmost X-Forwarded-For does not get a fresh allowance", async () => {
    const { deps: d } = deps();
    const statuses: number[] = [];
    for (let attempt = 0; attempt < 6; attempt += 1) {
      const response = await handleInquiry(
        jsonRequest("/api/inquiries", inquiryBody({ email: `p${attempt}@example.invalid` }), {
          "x-forwarded-for": `198.51.100.${attempt}, 203.0.113.7`,
        }),
        d,
      );
      statuses.push(response.status);
    }
    expect(statuses).toEqual([202, 202, 202, 202, 202, 429]);
  });

  test("a configured trusted header names the client instead", async () => {
    const { deps: d } = deps(accepted, { ...CONFIG, trustedClientIpHeader: "CF-Connecting-IP" });
    const statuses: number[] = [];
    for (let attempt = 0; attempt < 6; attempt += 1) {
      const response = await handleInquiry(
        jsonRequest("/api/inquiries", inquiryBody({ email: `q${attempt}@example.invalid` }), {
          "x-forwarded-for": `198.51.100.${attempt}`,
          "cf-connecting-ip": "192.0.2.9",
        }),
        d,
      );
      statuses.push(response.status);
    }
    expect(statuses).toEqual([202, 202, 202, 202, 202, 429]);
  });
});

describe("inquiry logging", () => {
  test("never writes the visitor's name, address or message", async () => {
    const logs = captureLogs();
    try {
      const { deps: d } = deps();
      await handleInquiry(jsonRequest("/api/inquiries", inquiryBody()), d);
      const failing = deps(() => new Response("", { status: 500 })).deps;
      await handleInquiry(jsonRequest("/api/inquiries", inquiryBody({ submissionId: crypto.randomUUID() })), failing);
    } finally {
      logs.restore();
    }
    const written = logs.lines.join("\n");
    expect(written).toContain("inquiry_accepted");
    expect(written).toContain("inquiry_provider_rejected");
    for (const private_ of ["Marisol", "example.invalid", "ferretería", SUBMISSION_ID]) {
      expect(written).not.toContain(private_);
    }
  });
});
