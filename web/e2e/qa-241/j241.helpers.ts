import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { BrowserContext, Page } from "@playwright/test";
import { expect } from "@playwright/test";

export const ROOT = path.resolve(__dirname, "../../..");
export const EVIDENCE_DIR = path.join(ROOT, "temp", "qa-241");
export const SHOTS_DIR = path.join(EVIDENCE_DIR, "shots");
export const ARGUS_API = process.env.QA_ARGUS_API ?? "http://localhost:8000/api/v1";

async function supabaseAccessToken(context: BrowserContext): Promise<string | null> {
  const cookies = await context.cookies("http://localhost:3000");
  const chunks = cookies
    .filter((cookie) => /^sb-.*-auth-token(\.\d+)?$/.test(cookie.name))
    .sort((a, b) => {
      const index = (name: string) => Number(/\.(\d+)$/.exec(name)?.[1] ?? 0);
      return index(a.name) - index(b.name);
    })
    .map((cookie) => cookie.value)
    .join("");
  if (!chunks) return null;
  try {
    const raw = chunks.startsWith("base64-")
      ? Buffer.from(chunks.slice("base64-".length), "base64").toString("utf8")
      : decodeURIComponent(chunks);
    return (JSON.parse(raw) as { access_token?: string }).access_token ?? null;
  } catch {
    return null;
  }
}

export async function apiGet(
  context: BrowserContext,
  pathname: string,
): Promise<{ status: number; body: unknown }> {
  const token = await supabaseAccessToken(context);
  const res = await context.request.get(`${ARGUS_API}${pathname}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  return { status: res.status(), body };
}

export async function meProbe(context: BrowserContext): Promise<{
  status: number;
  isAdmin: boolean | null;
  language: string | null;
}> {
  const { status, body } = await apiGet(context, "/me");
  const user = (body as { user?: { is_admin?: boolean; language?: string } })?.user;
  return {
    status,
    isAdmin: typeof user?.is_admin === "boolean" ? user.is_admin : null,
    language: user?.language ?? null,
  };
}

export function saveEvidence(name: string, payload: unknown) {
  mkdirSync(EVIDENCE_DIR, { recursive: true });
  writeFileSync(
    path.join(EVIDENCE_DIR, `${name}.json`),
    JSON.stringify(payload, null, 2),
  );
}

export async function shot(page: Page, name: string) {
  mkdirSync(SHOTS_DIR, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS_DIR, `${name}.png`), fullPage: false });
}

export async function latestConversationId(
  context: BrowserContext,
): Promise<string | null> {
  const { body } = await apiGet(context, "/conversations?limit=1");
  const items = (body as { items?: Array<{ id?: string }> })?.items;
  return items?.[0]?.id ?? null;
}

export async function conversationMessages(
  context: BrowserContext,
  conversationId: string,
): Promise<{ status: number; items: Array<Record<string, unknown>> }> {
  const { status, body } = await apiGet(
    context,
    `/conversations/${conversationId}/messages?limit=50`,
  );
  const items =
    ((body as { items?: Array<Record<string, unknown>> })?.items ?? []) as Array<
      Record<string, unknown>
    >;
  return { status, items };
}

function assistantTerminalCount(items: Array<Record<string, unknown>>): number {
  return items.filter((item) => {
    if (item.role !== "assistant") return false;
    const metadata = item.metadata as Record<string, unknown> | undefined;
    const turn = metadata?.agent_runtime_turn as Record<string, unknown> | undefined;
    if (turn?.terminal === true) return true;
    // Backtest-action turns and older writers may omit the lifecycle projection;
    // any persisted assistant message is still a durable response.
    return true;
  }).length;
}

export async function startNewChat(page: Page) {
  await page.goto("/chat");
  const newChat = page.getByRole("button", { name: /new chat|nueva conversaci/i });
  if (await newChat.count()) {
    await newChat.first().click();
  }
  await expect(page.locator('[data-testid="chat-input"]')).toBeVisible({
    timeout: 15_000,
  });
}

export async function reopenConversation(page: Page, conversationId: string) {
  const row = page.locator(`[data-conversation-id="${conversationId}"]`);
  if (!(await row.first().isVisible().catch(() => false))) {
    const expand = page.getByRole("button", { name: /expand sidebar/i });
    if (await expand.count()) {
      await expand.first().click();
      await page.waitForTimeout(500);
    }
    // Conversation rows render inside the Recents panel after a fresh load.
    const recents = page.getByRole("button", { name: /recents|recientes/i });
    if (
      !(await row.first().isVisible().catch(() => false)) &&
      (await recents.count())
    ) {
      await recents.first().click();
      await page.waitForTimeout(1_000);
    }
  }
  await expect(row.first()).toBeVisible({ timeout: 15_000 });
  await row.first().click();
  await expect(page.locator('[data-testid="chat-input"]')).toBeVisible({
    timeout: 15_000,
  });
  await page.waitForTimeout(1_000);
}

export async function sendTurn(
  page: Page,
  context: BrowserContext,
  text: string,
  options: { conversationId: string | null; timeoutMs?: number },
): Promise<{ conversationId: string }> {
  const timeoutMs = options.timeoutMs ?? 180_000;
  let baseline = 0;
  let conversationId = options.conversationId;
  if (conversationId) {
    baseline = assistantTerminalCount(
      (await conversationMessages(context, conversationId)).items,
    );
  }
  const input = page.locator('[data-testid="chat-input"]');
  await expect(input).toBeVisible({ timeout: 15_000 });
  await input.click();
  await input.fill(text);
  await page.locator('[data-testid="chat-send"]').click();

  const deadline = Date.now() + timeoutMs;
  for (;;) {
    if (Date.now() > deadline) {
      throw new Error(`turn did not reach a durable assistant response: ${text}`);
    }
    await page.waitForTimeout(2_000);
    if (!conversationId) {
      conversationId = await latestConversationId(context);
      if (!conversationId) continue;
    }
    const { items } = await conversationMessages(context, conversationId);
    const userArrived = items.some(
      (item) => item.role === "user" && String(item.content ?? "").includes(text.slice(0, 40)),
    );
    if (!userArrived) continue;
    if (assistantTerminalCount(items) > baseline) break;
  }
  await page.waitForTimeout(1_500);
  return { conversationId: conversationId as string };
}

export function messageDigest(items: Array<Record<string, unknown>>) {
  return items.map((item) => {
    const metadata = (item.metadata ?? {}) as Record<string, unknown>;
    return {
      id: item.id,
      role: item.role,
      created_at: item.created_at,
      content: item.content,
      metadata_keys: Object.keys(metadata).sort(),
      metadata,
    };
  });
}

export async function historySnapshot(context: BrowserContext) {
  const { status, body } = await apiGet(context, "/history?limit=20");
  return { status, body };
}
