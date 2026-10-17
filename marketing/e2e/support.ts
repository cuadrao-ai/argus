import {
  expect,
  type APIRequestContext,
  type BrowserContext,
  type TestInfo,
} from "@playwright/test";

import { MOCK_URL } from "./ports";
export { PUBLIC_URL } from "./ports";

export type MockState = {
  emails: {
    from: string;
    to: string[];
    reply_to: string;
    subject: string;
    text: string;
    idempotencyKey: string;
  }[];
  signups: {
    email: string | null;
    language: string;
    consent_version: string;
  }[];
};

export async function resetMock(request: APIRequestContext): Promise<void> {
  await request.post(`${MOCK_URL}/__reset`);
}

export async function setMode(
  request: APIRequestContext,
  mode: Partial<{
    resend: "up" | "down";
    supabase: "up" | "down";
    resendDelayMs: number;
  }>,
): Promise<void> {
  await request.post(`${MOCK_URL}/__mode`, { data: mode });
}

export async function mockState(
  request: APIRequestContext,
): Promise<MockState> {
  return (await request.get(`${MOCK_URL}/__state`)).json();
}

// Each test appears as its own client so the per-address limits of one test
// cannot spend another's allowance.
let clientCounter = 0;
export async function asNewClient(
  context: BrowserContext,
  info: TestInfo,
): Promise<string> {
  clientCounter += 1;
  const ip = `10.${info.project.name === "mobile" ? 2 : 1}.${Math.floor(clientCounter / 250)}.${(clientCounter % 250) + 1}`;
  await context.setExtraHTTPHeaders({ "x-forwarded-for": ip });
  return ip;
}

let addressCounter = 0;
export function uniqueAddress(info: TestInfo): string {
  addressCounter += 1;
  return `visitor-${info.project.name}-${Date.now()}-${addressCounter}@example.invalid`;
}

export async function expectNothingStoredInBrowser(
  page: import("@playwright/test").Page,
): Promise<void> {
  const stored = await page.evaluate(() => ({
    cookie: document.cookie,
    local: window.localStorage.length,
    session: window.sessionStorage.length,
  }));
  expect(stored).toEqual({ cookie: "", local: 0, session: 0 });
  expect(await page.context().cookies()).toEqual([]);
}
