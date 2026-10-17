import type { FormsConfig } from "../lib/forms/config";
import { WindowLimiter } from "../lib/forms/rate-limit";

export const CONFIG: FormsConfig = {
  resendApiKey: "re_test_key",
  resendApiUrl: "https://resend.test",
  inquiryFrom: "Cuadrao <website@notify.example.test>",
  inquiryTo: "inbox@example.test",
  supabaseUrl: "https://project.supabase.test",
  supabaseServiceKey: "service-role-test-key",
  trustedClientIpHeader: null,
};

export const SUBMISSION_ID = "6f1c2b9e-8a4d-4c1e-9b7a-3d5e7f9a1b2c";

export type Call = { url: string; init: RequestInit };

export function recordingFetch(
  respond: (call: Call) => Response | Promise<Response>,
): { fetch: typeof fetch; calls: Call[] } {
  const calls: Call[] = [];
  const fake = async (input: RequestInfo | URL, init?: RequestInit) => {
    const call = { url: String(input), init: init ?? {} };
    calls.push(call);
    return respond(call);
  };
  return { fetch: fake as typeof fetch, calls };
}

export function counters() {
  const now = () => 1_000_000;
  return {
    perClient: new WindowLimiter(5, 600_000, now),
    perEmail: new WindowLimiter(3, 3_600_000, now),
    overall: new WindowLimiter(60, 3_600_000, now),
  };
}

export function jsonRequest(
  path: string,
  body: unknown,
  headers: Record<string, string> = {},
): Request {
  return new Request(`https://cuadrao.test${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      host: "cuadrao.test",
      "x-forwarded-for": "203.0.113.7",
      ...headers,
    },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

export function inquiryBody(overrides: Record<string, unknown> = {}) {
  return {
    name: "Marisol Peña",
    email: "Marisol@Example.INVALID ",
    description: "Llevo las cuentas de una ferretería.",
    locale: "es",
    submissionId: SUBMISSION_ID,
    website: "",
    ...overrides,
  };
}

export function captureLogs(): { lines: string[]; restore: () => void } {
  const original = console.log;
  const lines: string[] = [];
  console.log = (...args: unknown[]) => {
    lines.push(args.map(String).join(" "));
  };
  return { lines, restore: () => (console.log = original) };
}
