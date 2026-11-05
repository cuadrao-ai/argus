import { afterEach, describe, expect, test } from "bun:test";

import {
  createConversation,
  listConversations,
  listHistory,
  searchGlobal,
} from "@/lib/argus-api";
import { listComputedAnswers } from "@/lib/computations-api";
import {
  ConversationOnOtherSurfaceError,
  conversationShellHref,
  registerConversationShell,
  requireConversationInShell,
} from "@/lib/conversation-surface-guard";

type Call = { path: string; method: string; body: unknown };

function record(): Call[] {
  const calls: Call[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    calls.push({
      path: `${url.pathname.replace(/^.*\/api\/v1/, "")}${url.search}`,
      method: init?.method ?? "GET",
      body: init?.body ? JSON.parse(String(init.body)) : null,
    });
    return new Response(
      JSON.stringify({ items: [], next_cursor: null, conversation: {}, success: true, deleted_count: 0 }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }) as typeof fetch;
  return calls;
}

async function everyCall(surface?: "personal" | "business") {
  const calls = record();
  await createConversation("en", {}, surface);
  await listConversations({ limit: 30, surface });
  await listHistory({ limit: 50, surface });
  await searchGlobal({ q: "renta", limit: 30, includeLedgerGroups: true, surface });
  await listComputedAnswers("price_multiple", "m-1", surface);
  return calls;
}

describe("the chat surface a request names", () => {
  const originalFetch = globalThis.fetch;
  const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  });

  test("/chat sends exactly the requests it sent before Business existed", async () => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    const expected = [
      { path: "/conversations", method: "POST", body: { title: null, language: "en" } },
      { path: "/conversations?limit=30", method: "GET", body: null },
      { path: "/history?limit=50", method: "GET", body: null },
      { path: "/search?q=renta&limit=30&include_ledger_groups=true", method: "GET", body: null },
      { path: "/computations/answers?kind=price_multiple&exclude_message_id=m-1", method: "GET", body: null },
    ];
    expect(await everyCall()).toEqual(expected);
    expect(await everyCall("personal")).toEqual(expected);
  });

  test("/biz names the Business surface and never a space", async () => {
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    expect(await everyCall("business")).toEqual([
      {
        path: "/conversations",
        method: "POST",
        body: { title: null, language: "en", surface: "business" },
      },
      { path: "/conversations?limit=30&surface=business", method: "GET", body: null },
      { path: "/history?limit=50&surface=business", method: "GET", body: null },
      {
        path: "/search?q=renta&limit=30&include_ledger_groups=true&surface=business",
        method: "GET",
        body: null,
      },
      {
        path: "/computations/answers?kind=price_multiple&exclude_message_id=m-1&surface=business",
        method: "GET",
        body: null,
      },
    ]);
  });
});

describe("a conversation opened in the wrong shell", () => {
  test("is sent to its own shell and never returned to the caller", () => {
    const opened: string[] = [];
    const unregister = registerConversationShell({
      surface: "personal",
      open: (id, surface) => opened.push(`${surface}:${id}`),
    });
    try {
      expect(() => requireConversationInShell("c-1", "personal")).not.toThrow();
      expect(() => requireConversationInShell("c-1", undefined)).not.toThrow();
      expect(() => requireConversationInShell("c-2", "business")).toThrow(ConversationOnOtherSurfaceError);
      expect(opened).toEqual(["business:c-2"]);
    } finally {
      unregister();
    }
    expect(() => requireConversationInShell("c-3", "business")).not.toThrow();
  });

  test("keeps the conversation id and its linked message", () => {
    expect(conversationShellHref("http://x/chat?conversation=c-2&message=m-9", "c-2", "business")).toBe(
      "/biz?conversation=c-2&message=m-9",
    );
    expect(conversationShellHref("http://x/biz?conversation=other&message=m-9", "c-2", "personal")).toBe(
      "/chat?conversation=c-2",
    );
  });
});
